"""
Service provisioning engine.

Each operation is a short saga of NetBox REST calls. Every object created is put on an undo stack,
so a failure part way through rolls back cleanly and NetBox never keeps a half-provisioned service.
All writes go through NetBox, so validation, change logging, webhooks and permissions apply as usual.

Services (on an ONT):
  hsi       High-Speed Internet  -> wan* virtual interface: C-VLAN 100, IP from the site's Subscriber WAN pool, VC
  voip      Voice                -> voip* virtual interface: C-VLAN 200, IP from the VOIP pool, a DID, VC
  ethernet  Business Ethernet    -> eth* physical port: new sub-interface eth*.<vid>, per-customer C-VLAN
                                    allocated from the site's C-VLAN group and Q-in-Q'd under the PON's S-VLAN, VC
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .netbox import NetBox, NetBoxError

log = logging.getLogger('nbgraph.provision')

SERVICES = {
    'hsi': {'label': 'High-Speed Internet', 'vc_type': 'hsi', 'vid': 100, 'prefix_role': 'subscriber-wan'},
    'voip': {'label': 'Voice (VOIP)', 'vc_type': 'voip', 'vid': 200, 'prefix_role': 'voip'},
    'ethernet': {'label': 'Business Ethernet', 'vc_type': 'business-ethernet', 'vid': None, 'prefix_role': None},
}
PROVIDER_NETWORK = 'Residential Access Fabric'


class ProvisionError(Exception):
    def __init__(self, message: str, status: int = 400, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


@dataclass
class Saga:
    nb: NetBox
    undo: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)

    def created(self, kind: str, obj: dict, path: str):
        self.log.append({'action': 'created', 'kind': kind, 'id': obj['id'], 'display': obj.get('display')})
        self.undo.append((f'delete {kind} {obj["id"]}', lambda: self.nb.delete(f'{path}{obj["id"]}/')))

    def updated(self, kind: str, obj_id: int, path: str, before: dict, after_display: str = ''):
        self.log.append({'action': 'updated', 'kind': kind, 'id': obj_id, 'display': after_display})
        self.undo.append((f'restore {kind} {obj_id}', lambda: self.nb.patch(f'{path}{obj_id}/', before)))

    def rollback(self):
        for desc, fn in reversed(self.undo):
            try:
                fn()
                log.info('rollback: %s', desc)
            except Exception as exc:  # keep rolling back
                log.warning('rollback step failed (%s): %s', desc, exc)


# --------------------------------------------------------------------------------------------------
# lookups
# --------------------------------------------------------------------------------------------------
def _site_code(site: dict) -> str:
    return site['slug'].split('-')[0].upper()


def _vlan_group(nb: NetBox, site_id: int, kind: str) -> dict:
    # NB: vlan-groups ignores ?site_id=; scope_type/scope_id is the filter that works for site-scoped groups
    grp = nb.first('ipam/vlan-groups/', scope_type='dcim.site', scope_id=site_id, slug__ic=f'-{kind}')
    if not grp:
        raise ProvisionError(f'No {kind.upper()} VLAN group found for site {site_id}', 409)
    return grp


def _service_vlan(nb: NetBox, site_id: int, vid: int) -> dict:
    grp = _vlan_group(nb, site_id, 'cvlan')
    vlan = nb.first('ipam/vlans/', group_id=grp['id'], vid=vid)
    if not vlan:
        raise ProvisionError(f'Service VLAN {vid} missing in group {grp["name"]}', 409)
    return vlan


def _pool(nb: NetBox, site_id: int, role: str) -> dict:
    pfx = nb.first('ipam/prefixes/', site_id=site_id, role=role)
    if not pfx:
        raise ProvisionError(f'No prefix with role "{role}" at site {site_id}', 409)
    return pfx


def _serving_pon(nb: NetBox, ont_id: int) -> dict | None:
    """The OLT PON interface feeding an ONT, found by following NetBox's own cable trace from ONT pon0."""
    pon = nb.first('dcim/interfaces/', device_id=ont_id, type='gpon')
    if not pon or not pon.get('connected_endpoints'):
        return None
    ep = pon['connected_endpoints'][0]
    return nb.get(f'dcim/interfaces/{ep["id"]}/')


def interface_services(nb: NetBox, interface_id: int) -> dict:
    """Describe what is provisioned on an interface (and its sub-interfaces) and which services fit it."""
    iface = nb.get(f'dcim/interfaces/{interface_id}/')
    targets = [iface] + nb.list('dcim/interfaces/', parent_id=interface_id)
    services = []
    for t in targets:
        term = nb.first('circuits/virtual-circuit-terminations/', interface_id=t['id'])
        if not term:
            continue
        vc = nb.get(f'circuits/virtual-circuits/{term["virtual_circuit"]["id"]}/')
        ips = nb.list('ipam/ip-addresses/', interface_id=t['id'])
        nums = nb.list('plugins/numbers/telephone-numbers/', interface_id=t['id'])
        services.append({
            'interface': {'id': t['id'], 'name': t['name']},
            'virtual_circuit': {'id': vc['id'], 'cid': vc['cid'], 'type': vc['type']['slug'],
                                'status': vc['status']['value'],
                                'tenant': (vc.get('tenant') or {}).get('display')},
            'vlan': t.get('untagged_vlan') and {'id': t['untagged_vlan']['id'], 'vid': t['untagged_vlan']['vid'],
                                                'name': t['untagged_vlan']['name']},
            'ip_addresses': [{'id': i['id'], 'address': i['address']} for i in ips],
            'numbers': [{'id': n['id'], 'number': n['number']} for n in nums],
        })
    return {'interface': {'id': iface['id'], 'name': iface['name'], 'type': iface['type']['value'],
                          'device': iface['device']['name']},
            'eligible': eligible_services(iface), 'services': services}


def eligible_services(iface: dict) -> list[str]:
    name = iface['name'].lower()
    itype = iface['type']['value']
    if iface.get('parent'):
        return []
    if name.startswith('wan') and itype == 'virtual':
        return ['hsi']
    if name.startswith('voip') and itype == 'virtual':
        return ['voip']
    if name.startswith('eth') and itype != 'virtual':
        return ['ethernet']
    return []


# --------------------------------------------------------------------------------------------------
# provision
# --------------------------------------------------------------------------------------------------
def provision_service(nb: NetBox, interface_id: int, service: str, tenant_id: int | None = None,
                      tenant_name: str | None = None, description: str = '') -> dict:
    if service not in SERVICES:
        raise ProvisionError(f'Unknown service "{service}". Choose one of {list(SERVICES)}')
    spec = SERVICES[service]
    iface = nb.get(f'dcim/interfaces/{interface_id}/')
    if service not in eligible_services(iface):
        raise ProvisionError(f'Service "{service}" cannot be provisioned on interface {iface["name"]} '
                             f'(eligible: {eligible_services(iface) or "none"})')
    device = nb.get(f'dcim/devices/{iface["device"]["id"]}/')
    if device['role']['slug'] != 'ont':
        raise ProvisionError('Services can only be provisioned on ONT interfaces')
    existing = interface_services(nb, interface_id)['services']
    if service != 'ethernet' and existing:
        raise ProvisionError(f'{iface["name"]} already carries {existing[0]["virtual_circuit"]["cid"]}', 409)

    site = nb.get(f'dcim/sites/{device["site"]["id"]}/')
    code = _site_code(site)
    saga = Saga(nb)
    try:
        # 1. tenant (subscriber)
        if tenant_id:
            tenant = nb.get(f'tenancy/tenants/{tenant_id}/')
        elif device.get('tenant'):
            tenant = nb.get(f'tenancy/tenants/{device["tenant"]["id"]}/')
        else:
            name = tenant_name or f'Subscriber {device["name"].upper()}'
            slug = ''.join(c if c.isalnum() else '-' for c in name.lower()).strip('-')
            tenant = nb.first('tenancy/tenants/', slug=slug)
            if not tenant:
                grp = nb.first('tenancy/tenant-groups/', slug='residential-subscribers')
                tenant = nb.post('tenancy/tenants/', {'name': name, 'slug': slug,
                                                      'group': grp['id'] if grp else None})
                saga.created('tenant', tenant, 'tenancy/tenants/')
        if not device.get('tenant'):
            nb.patch(f'dcim/devices/{device["id"]}/', {'tenant': tenant['id']})
            saga.updated('device', device['id'], 'dcim/devices/', {'tenant': None}, device['name'])

        # 2. VLAN + target interface
        desc = description or f'{spec["label"]} for {tenant["name"]}'
        if service == 'ethernet':
            pon = _serving_pon(nb, device['id'])
            svlan = (pon or {}).get('qinq_svlan')
            grp = _vlan_group(nb, site['id'], 'cvlan')
            vlan_body = {'name': f'{device["name"]}-{iface["name"]}', 'status': 'active',
                         'tenant': tenant['id'], 'description': desc}
            if svlan:
                vlan_body.update({'qinq_role': 'cvlan', 'qinq_svlan': svlan['id']})
            created = nb.post(f'ipam/vlan-groups/{grp["id"]}/available-vlans/', vlan_body)
            vlan = created[0] if isinstance(created, list) else created
            saga.created('vlan', vlan, 'ipam/vlans/')
            target = nb.post('dcim/interfaces/', {
                'device': device['id'], 'name': f'{iface["name"]}.{vlan["vid"]}', 'type': 'virtual',
                'parent': iface['id'], 'mode': 'access', 'untagged_vlan': vlan['id'], 'enabled': True,
                'description': desc,
            })
            saga.created('interface', target, 'dcim/interfaces/')
            if not iface['enabled']:
                nb.patch(f'dcim/interfaces/{iface["id"]}/', {'enabled': True})
                saga.updated('interface', iface['id'], 'dcim/interfaces/', {'enabled': False}, iface['name'])
        else:
            vlan = _service_vlan(nb, site['id'], spec['vid'])
            before = {'mode': (iface.get('mode') or {}).get('value') or None,
                      'untagged_vlan': (iface.get('untagged_vlan') or {}).get('id'),
                      'enabled': iface['enabled'], 'description': iface['description']}
            target = nb.patch(f'dcim/interfaces/{iface["id"]}/', {
                'mode': 'access', 'untagged_vlan': vlan['id'], 'enabled': True, 'description': desc,
            })
            saga.updated('interface', iface['id'], 'dcim/interfaces/', before, iface['name'])

        # 3. IP address from the site pool
        ip = None
        if spec['prefix_role']:
            pool = _pool(nb, site['id'], spec['prefix_role'])
            ips = nb.post(f'ipam/prefixes/{pool["id"]}/available-ips/', {
                'assigned_object_type': 'dcim.interface', 'assigned_object_id': target['id'],
                'status': 'active', 'tenant': tenant['id'], 'description': desc,
            })
            ip = ips[0] if isinstance(ips, list) else ips
            saga.created('ip-address', ip, 'ipam/ip-addresses/')

        # 4. telephone number (DID)
        number = None
        if service == 'voip':
            number = nb.first('plugins/numbers/telephone-numbers/', site_id=site['id'], status='available',
                              ordering='number')
            if not number:
                raise ProvisionError(f'No available telephone numbers at {site["name"]}', 409)
            nb.patch(f'plugins/numbers/telephone-numbers/{number["id"]}/', {
                'interface': target['id'], 'status': 'assigned', 'tenant': tenant['id'],
                'sip_username': number['number'].lstrip('+'),
            })
            saga.updated('telephone-number', number['id'], 'plugins/numbers/telephone-numbers/',
                         {'interface': None, 'status': 'available', 'tenant': None, 'sip_username': ''},
                         number['number'])

        # 5. virtual circuit (service instance) + termination
        pn = nb.first('circuits/provider-networks/', name=PROVIDER_NETWORK)
        vct = nb.first('circuits/virtual-circuit-types/', slug=spec['vc_type'])
        if not pn or not vct:
            raise ProvisionError('Seed data missing: provider network / virtual circuit types', 409)
        vc = nb.post('circuits/virtual-circuits/', {
            'cid': f'{spec["vc_type"].upper().replace("-", "")[:4]}-{code}-{target["id"]:06d}',
            'provider_network': pn['id'], 'type': vct['id'], 'status': 'active',
            'tenant': tenant['id'], 'description': desc,
        })
        saga.created('virtual-circuit', vc, 'circuits/virtual-circuits/')
        term = nb.post('circuits/virtual-circuit-terminations/', {
            'virtual_circuit': vc['id'], 'interface': target['id'], 'role': 'spoke',
        })
        saga.log.append({'action': 'created', 'kind': 'vc-termination', 'id': term['id'], 'display': term['display']})

        return {
            'status': 'provisioned', 'service': service, 'interface_id': target['id'],
            'virtual_circuit': {'id': vc['id'], 'cid': vc['cid']},
            'vlan': {'id': vlan['id'], 'vid': vlan['vid']},
            'ip_address': ip and {'id': ip['id'], 'address': ip['address']},
            'number': number and {'id': number['id'], 'number': number['number']},
            'tenant': {'id': tenant['id'], 'name': tenant['name']},
            'steps': saga.log,
        }
    except NetBoxError as exc:
        saga.rollback()
        raise ProvisionError(f'NetBox rejected a step, rolled back: {exc}', 502, exc.detail) from exc
    except ProvisionError:
        saga.rollback()
        raise
    except Exception:
        saga.rollback()
        raise


def deprovision_service(nb: NetBox, interface_id: int, vc_id: int | None = None) -> dict:
    """Remove the service(s) on an interface: VC, IPs, DID release, VLAN/sub-interface cleanup."""
    info = interface_services(nb, interface_id)
    services = [s for s in info['services'] if vc_id is None or s['virtual_circuit']['id'] == vc_id]
    if not services:
        raise ProvisionError('Nothing provisioned on this interface', 404)
    steps = []
    for svc in services:
        t_id = svc['interface']['id']
        nb.delete(f'circuits/virtual-circuits/{svc["virtual_circuit"]["id"]}/')
        steps.append({'action': 'deleted', 'kind': 'virtual-circuit', 'display': svc['virtual_circuit']['cid']})
        for ip in svc['ip_addresses']:
            nb.delete(f'ipam/ip-addresses/{ip["id"]}/')
            steps.append({'action': 'deleted', 'kind': 'ip-address', 'display': ip['address']})
        for num in svc['numbers']:
            nb.patch(f'plugins/numbers/telephone-numbers/{num["id"]}/',
                     {'interface': None, 'status': 'available', 'tenant': None, 'sip_username': ''})
            steps.append({'action': 'released', 'kind': 'telephone-number', 'display': num['number']})
        if t_id != interface_id:  # sub-interface created for a business ethernet service
            nb.delete(f'dcim/interfaces/{t_id}/')
            steps.append({'action': 'deleted', 'kind': 'interface', 'display': svc['interface']['name']})
            if svc['vlan']:
                vlan = nb.get(f'ipam/vlans/{svc["vlan"]["id"]}/')
                if (vlan.get('qinq_role') or {}).get('value') == 'cvlan' or vlan['vid'] not in (100, 200):
                    nb.delete(f'ipam/vlans/{vlan["id"]}/')
                    steps.append({'action': 'deleted', 'kind': 'vlan', 'display': f'{vlan["vid"]} {vlan["name"]}'})
        else:
            nb.patch(f'dcim/interfaces/{t_id}/', {'mode': None, 'untagged_vlan': None, 'description': ''})
            steps.append({'action': 'updated', 'kind': 'interface', 'display': svc['interface']['name']})
    return {'status': 'deprovisioned', 'interface_id': interface_id, 'steps': steps}


# --------------------------------------------------------------------------------------------------
# topology helpers: add an ONT under a PON port (through its splitter)
# --------------------------------------------------------------------------------------------------
def add_ont(nb: NetBox, pon_interface_id: int, name: str | None = None, serial: str = '',
            device_type_slug: str = 'ao-ont-4v') -> dict:
    pon = nb.get(f'dcim/interfaces/{pon_interface_id}/')
    if pon['type']['value'] not in ('gpon', 'xgs-pon'):
        raise ProvisionError('Pick an OLT PON port')
    olt = nb.get(f'dcim/devices/{pon["device"]["id"]}/')
    # splitter = the device on the far side of the PON cable (its IN rear-port)
    peers = pon.get('link_peers') or []
    if not peers or pon.get('link_peers_type') != 'dcim.rearport':
        raise ProvisionError('This PON port has no splitter cabled to it', 409)
    rear = nb.get(f'dcim/rear-ports/{peers[0]["id"]}/')
    splitter_id = rear['device']['id']
    free = [fp for fp in nb.list('dcim/front-ports/', device_id=splitter_id) if not fp.get('cable')]
    if not free:
        raise ProvisionError('Splitter is full: every OUT port is cabled', 409)
    fp = sorted(free, key=lambda f: f['name'])[0]
    site_id = olt['site']['id']
    loc = nb.first('dcim/locations/', site_id=site_id, slug__ic='subscribers')
    role = nb.first('dcim/device-roles/', slug='ont')
    dtype = nb.first('dcim/device-types/', slug=device_type_slug)
    if not name:
        prefix = olt['name'].split('-')[0]
        n = nb.get('dcim/devices/', role_id=role['id'], site_id=site_id, limit=1)['count'] + 1
        name = f'{prefix}-ont-{n:04d}'
        while nb.first('dcim/devices/', name=name):
            n += 1
            name = f'{prefix}-ont-{n:04d}'
    saga = Saga(nb)
    try:
        ont = nb.post('dcim/devices/', {
            'name': name, 'device_type': dtype['id'], 'role': role['id'], 'site': site_id,
            'location': loc['id'] if loc else None, 'status': 'active', 'serial': serial,
        })
        saga.created('device', ont, 'dcim/devices/')
        ont_pon = nb.first('dcim/interfaces/', device_id=ont['id'], type='gpon')
        cable = nb.post('dcim/cables/', {
            'a_terminations': [{'object_type': 'dcim.frontport', 'object_id': fp['id']}],
            'b_terminations': [{'object_type': 'dcim.interface', 'object_id': ont_pon['id']}],
            'status': 'connected', 'type': 'smf', 'label': f'{fp["device"]["name"]}:{fp["name"]}',
        })
        saga.created('cable', cable, 'dcim/cables/')
        return {'status': 'created', 'device': {'id': ont['id'], 'name': ont['name']},
                'splitter_port': fp['name'], 'cable': cable['id'], 'steps': saga.log}
    except NetBoxError as exc:
        saga.rollback()
        raise ProvisionError(f'NetBox rejected a step, rolled back: {exc}', 502, exc.detail) from exc
