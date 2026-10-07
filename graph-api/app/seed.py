"""
Demo data for nb_graph: a small fibre-to-the-home (FTTH) access network.

    Region (North America > US Midwest > Illinois ...)
      └─ Site (central office)
           ├─ OLT ── PON port ══ 1x16 splitter ══ ONT ── eth1-4 / voip1-2 / wan0
           │    └─ uplink ══ BNG (hub site), or a metro backhaul circuit ══ BNG
           ├─ Prefixes  (Management, Subscriber WAN, VOIP)
           ├─ VLAN groups (S-VLANs per PON, service C-VLANs)
           └─ Telephone numbers (DID pool)

Safe to run more than once: every object is looked up before it is created. Run with:
    python -m app.seed            (inside the graph-api container: `docker compose run --rm seed`)
"""
from __future__ import annotations

import logging
import os
import sys
import time

from .netbox import NetBox, NetBoxError
from .provision import ProvisionError, add_ont, provision_service

log = logging.getLogger('nbgraph.seed')

REGIONS = {
    'North America': {
        'US Midwest': {'Illinois': {}, 'Wisconsin': {}},
        'US South': {'Texas': {}},
    }
}

SITES = [
    # slug, name, region, idx, area code, OLT count, ONTs per splitter, hub
    ('chi-co-01', 'Chicago Central Office', 'Illinois', 1, '312', 2, 4, True),
    ('npv-co-01', 'Naperville CO', 'Illinois', 2, '630', 1, 3, False),
    ('mke-co-01', 'Milwaukee CO', 'Wisconsin', 3, '414', 1, 3, False),
    ('aus-co-01', 'Austin CO', 'Texas', 4, '512', 1, 3, False),
]
# Map view positions (WGS84); applied on create, and back-filled on re-seed if a site has none yet.
SITE_COORDS = {
    'chi-co-01': (41.878100, -87.629800),
    'npv-co-01': (41.750800, -88.153500),
    'mke-co-01': (43.038900, -87.906500),
    'aus-co-01': (30.267200, -97.743100),
}
PONS_USED = 2  # PON ports per OLT that get a splitter


def slugify(s: str) -> str:
    return ''.join(c if c.isalnum() else '-' for c in s.lower()).strip('-').replace('--', '-')


class Seeder:
    def __init__(self, nb: NetBox):
        self.nb = nb
        self.ids: dict[str, int] = {}

    # ---------------------------------------------------------------- small helpers
    def goc(self, path, lookup, body=None, key=None):
        obj = self.nb.get_or_create(path, lookup, body)
        if key:
            self.ids[key] = obj['id']
        return obj

    # ---------------------------------------------------------------- organisation
    def regions(self):
        def walk(tree, parent=None):
            for name, children in tree.items():
                body = {'name': name, 'slug': slugify(name)}
                if parent:
                    body['parent'] = parent
                r = self.goc('dcim/regions/', {'slug': slugify(name)}, body, f'region:{name}')
                walk(children, r['id'])
        walk(REGIONS)

    def catalog(self):
        nb = self.nb
        self.goc('tenancy/tenant-groups/', {'slug': 'residential-subscribers'},
                 {'name': 'Residential Subscribers', 'slug': 'residential-subscribers'})
        for name, color in [('OLT', '2196f3'), ('ONT', '4caf50'), ('Splitter', '9e9e9e'), ('BNG', '9c27b0')]:
            self.goc('dcim/device-roles/', {'slug': slugify(name)},
                     {'name': name, 'slug': slugify(name), 'color': color}, f'role:{name.lower()}')
        mfr = self.goc('dcim/manufacturers/', {'slug': 'acme-optical'}, {'name': 'Acme Optical', 'slug': 'acme-optical'})
        gen = self.goc('dcim/manufacturers/', {'slug': 'generic'}, {'name': 'Generic', 'slug': 'generic'})

        def dtype(slug, model, manufacturer, ifaces=(), u_height=1):
            dt = self.goc('dcim/device-types/', {'slug': slug},
                          {'manufacturer': manufacturer['id'], 'model': model, 'slug': slug, 'u_height': u_height},
                          f'dtype:{slug}')
            for name, itype, mgmt in ifaces:
                self.goc('dcim/interface-templates/', {'device_type_id': dt['id'], 'name': name},
                         {'device_type': dt['id'], 'name': name, 'type': itype, 'mgmt_only': mgmt})
            return dt

        dtype('ao-olt-8', 'AO-OLT-8 GPON OLT', mfr,
              [(f'pon{i}', 'gpon', False) for i in range(1, 9)]
              + [(f'uplink{i}', '10gbase-x-sfpp', False) for i in (1, 2)]
              + [('mgmt0', '1000base-t', True)])
        dtype('ao-ont-4v', 'AO-ONT-4V Residential ONT', mfr,
              [('pon0', 'gpon', False)]
              + [(f'eth{i}', '1000base-t', False) for i in range(1, 5)]
              + [('voip1', 'virtual', False), ('voip2', 'virtual', False), ('wan0', 'virtual', False)], u_height=0)
        dtype('gen-bng', 'Generic BNG Router', gen,
              [(f'xe-0/0/{i}', '10gbase-x-sfpp', False) for i in range(8)] + [('lo0', 'virtual', False)], u_height=2)

        # Passive 1x16 splitter: rear port IN (16 positions) -> front ports OUT01..OUT16
        spl = self.goc('dcim/device-types/', {'slug': 'ao-spl-1x16'},
                       {'manufacturer': mfr['id'], 'model': 'AO-SPL-1x16 PLC Splitter', 'slug': 'ao-spl-1x16',
                        'u_height': 0}, 'dtype:ao-spl-1x16')
        rp = self.goc('dcim/rear-port-templates/', {'device_type_id': spl['id'], 'name': 'IN'},
                      {'device_type': spl['id'], 'name': 'IN', 'type': 'sc-apc', 'positions': 16})
        for i in range(1, 17):
            self.goc('dcim/front-port-templates/', {'device_type_id': spl['id'], 'name': f'OUT{i:02d}'},
                     {'device_type': spl['id'], 'name': f'OUT{i:02d}', 'type': 'sc-apc',
                      'rear_ports': [{'position': 1, 'rear_port': rp['id'], 'rear_port_position': i}]})

        # IPAM roles, circuits catalogue
        for name in ('Management', 'Subscriber WAN', 'VOIP'):
            self.goc('ipam/roles/', {'slug': slugify(name)}, {'name': name, 'slug': slugify(name)}, f'iprole:{name}')
        mf = self.goc('circuits/providers/', {'slug': 'metro-fiber-co'}, {'name': 'Metro Fiber Co', 'slug': 'metro-fiber-co'})
        self.ids['provider:metro'] = mf['id']
        self.goc('circuits/circuit-types/', {'slug': 'metro-backhaul'},
                 {'name': 'Metro Backhaul', 'slug': 'metro-backhaul'}, 'ctype:backhaul')
        isp = self.goc('circuits/providers/', {'slug': 'nb-graph-access'},
                       {'name': 'nb_graph Access Network', 'slug': 'nb-graph-access'})
        self.goc('circuits/provider-networks/', {'name': 'Residential Access Fabric'},
                 {'provider': isp['id'], 'name': 'Residential Access Fabric'})
        for name in ('HSI', 'VOIP', 'Business Ethernet'):
            self.goc('circuits/virtual-circuit-types/', {'slug': slugify(name)}, {'name': name, 'slug': slugify(name)})

    # ---------------------------------------------------------------- sites
    @staticmethod
    def coords(slug):
        if slug not in SITE_COORDS:
            return {}
        lat, lon = SITE_COORDS[slug]
        return {'latitude': lat, 'longitude': lon}

    def site(self, slug, name, region, idx, area, n_olt, onts_per_spl, hub):
        nb = self.nb
        code = slug.split('-')[0]
        site = self.goc('dcim/sites/', {'slug': slug},
                        {'name': name, 'slug': slug, 'status': 'active', 'region': self.ids[f'region:{region}'],
                         'facility': f'{code.upper()} Central Office', 'time_zone': 'America/Chicago',
                         **self.coords(slug)},
                        f'site:{slug}')
        sid = site['id']
        if site.get('latitude') is None and slug in SITE_COORDS:
            site = nb.patch(f'dcim/sites/{sid}/', self.coords(slug))
        subs = self.goc('dcim/locations/', {'site_id': sid, 'slug': f'{code}-subscribers'},
                        {'site': sid, 'name': 'Subscriber Premises', 'slug': f'{code}-subscribers', 'status': 'active'})
        scope = {'scope_type': 'dcim.site', 'scope_id': sid}

        # prefixes = number inventory (IPs)
        pfx = {}
        # NB: not marked is_pool: NetBox 4.7 refuses to put a network ID on an interface
        for role, cidr in (('Management', f'10.{idx}.0.0/24'),
                           ('Subscriber WAN', f'100.64.{idx}.0/24'),
                           ('VOIP', f'10.{100 + idx}.0.0/24')):
            pfx[role] = self.goc('ipam/prefixes/', {'prefix': cidr},
                                 {'prefix': cidr, 'status': 'active', 'role': self.ids[f'iprole:{role}'],
                                  'description': f'{code.upper()} {role}', **scope})

        # VLAN groups = number inventory (VLAN IDs)
        svg = self.goc('ipam/vlan-groups/', {'slug': f'{code}-svlan'},
                       {'name': f'{code.upper()} S-VLANs', 'slug': f'{code}-svlan', 'vid_ranges': [[1000, 1999]], **scope})
        cvg = self.goc('ipam/vlan-groups/', {'slug': f'{code}-cvlan'},
                       {'name': f'{code.upper()} Service C-VLANs', 'slug': f'{code}-cvlan',
                        'vid_ranges': [[100, 999]], **scope})
        for vid, vname in ((100, 'HSI'), (200, 'VOIP')):
            self.goc('ipam/vlans/', {'group_id': cvg['id'], 'vid': vid},
                     {'group': cvg['id'], 'vid': vid, 'name': f'{code.upper()}-{vname}', 'status': 'active'})

        # telephone numbers = number inventory (DIDs)
        for n in range(24):
            num = f'+1{area}555{100 + n:04d}'
            self.goc('plugins/numbers/telephone-numbers/', {'number': num},
                     {'number': num, 'status': 'available', 'site': sid, 'description': f'{code.upper()} DID pool'})

        # hub site: BNG
        if hub:
            bng = self.goc('dcim/devices/', {'name': f'{code}-bng-01'},
                           {'name': f'{code}-bng-01', 'device_type': self.ids['dtype:gen-bng'],
                            'role': self.ids['role:bng'], 'site': sid, 'status': 'active'})
            self.ids['bng'] = bng['id']
            self.ids['bng_site'] = sid
            self.ids['bng_next_port'] = 0

        # OLTs, splitters, ONTs
        for o in range(1, n_olt + 1):
            olt_name = f'{code}-olt-{o:02d}'
            olt = self.goc('dcim/devices/', {'name': olt_name},
                           {'name': olt_name, 'device_type': self.ids['dtype:ao-olt-8'], 'role': self.ids['role:olt'],
                            'site': sid, 'status': 'active', 'serial': f'AOOLT{idx}{o:03d}'})
            ifs = {i['name']: i for i in nb.list('dcim/interfaces/', device_id=olt['id'])}
            # management IP
            mgmt = ifs['mgmt0']
            if not nb.first('ipam/ip-addresses/', interface_id=mgmt['id']):
                ip = nb.post('ipam/ip-addresses/', {'address': f'10.{idx}.0.{10 + o}/24', 'status': 'active',
                                                    'assigned_object_type': 'dcim.interface',
                                                    'assigned_object_id': mgmt['id'], 'dns_name': f'{olt_name}.mgmt'})
                nb.patch(f'dcim/devices/{olt["id"]}/', {'primary_ip4': ip['id']})
            self.uplink(olt, ifs['uplink1'], site, code)
            for p in range(1, PONS_USED + 1):
                pon = ifs[f'pon{p}']
                svid = 1000 + o * 10 + p
                sv = self.goc('ipam/vlans/', {'group_id': svg['id'], 'vid': svid},
                              {'group': svg['id'], 'vid': svid, 'name': f'{olt_name}-pon{p}', 'status': 'active',
                               'qinq_role': 'svlan'})
                if not pon.get('qinq_svlan'):
                    nb.patch(f'dcim/interfaces/{pon["id"]}/', {'mode': 'q-in-q', 'qinq_svlan': sv['id'],
                                                                'description': f'PON {p} S-VLAN {svid}'})
                spl_name = f'{olt_name}-pon{p}-spl'
                spl = self.goc('dcim/devices/', {'name': spl_name},
                               {'name': spl_name, 'device_type': self.ids['dtype:ao-spl-1x16'],
                                'role': self.ids['role:splitter'], 'site': sid, 'location': subs['id'],
                                'status': 'active'})
                rear = nb.first('dcim/rear-ports/', device_id=spl['id'], name='IN')
                if not pon.get('cable'):
                    nb.post('dcim/cables/', {
                        'a_terminations': [{'object_type': 'dcim.interface', 'object_id': pon['id']}],
                        'b_terminations': [{'object_type': 'dcim.rearport', 'object_id': rear['id']}],
                        'status': 'connected', 'type': 'smf', 'label': f'{olt_name}:pon{p}'})
                have = sum(1 for fp in nb.list('dcim/front-ports/', device_id=spl['id']) if fp.get('cable'))
                for _ in range(onts_per_spl - have):
                    res = add_ont(nb, pon['id'], serial=f'AOON{idx}{o}{p}{_:03d}')
                    log.info('  + %s on %s', res['device']['name'], spl_name)

    def uplink(self, olt, uplink, site, code):
        """OLT uplink -> BNG directly (hub) or through a metro backhaul circuit (remote)."""
        nb = self.nb
        if uplink.get('cable'):
            return
        bng_ports = [i for i in nb.list('dcim/interfaces/', device_id=self.ids['bng'])
                     if i['name'].startswith('xe-') and not i.get('cable')]
        bng_port = sorted(bng_ports, key=lambda i: i['name'])[0]
        if site['id'] == self.ids['bng_site']:
            nb.post('dcim/cables/', {
                'a_terminations': [{'object_type': 'dcim.interface', 'object_id': uplink['id']}],
                'b_terminations': [{'object_type': 'dcim.interface', 'object_id': bng_port['id']}],
                'status': 'connected', 'type': 'smf', 'label': f'{olt["name"]}:uplink1'})
            return
        cid = f'MFC-{code.upper()}-0001'
        circ = self.goc('circuits/circuits/', {'cid': cid},
                        {'cid': cid, 'provider': self.ids['provider:metro'], 'type': self.ids['ctype:backhaul'],
                         'status': 'active', 'commit_rate': 10_000_000,
                         'description': f'{code.upper()} -> CHI backhaul'})
        ends = {}
        for side, sid in (('A', site['id']), ('Z', self.ids['bng_site'])):
            ends[side] = self.goc('circuits/circuit-terminations/', {'circuit_id': circ['id'], 'term_side': side},
                                  {'circuit': circ['id'], 'term_side': side, 'termination_type': 'dcim.site',
                                   'termination_id': sid, 'port_speed': 10_000_000})
        for term, iface, label in ((ends['A'], uplink, f'{olt["name"]}:uplink1'),
                                   (ends['Z'], bng_port, f'{cid}:Z')):
            nb.post('dcim/cables/', {
                'a_terminations': [{'object_type': 'dcim.interface', 'object_id': iface['id']}],
                'b_terminations': [{'object_type': 'circuits.circuittermination', 'object_id': term['id']}],
                'status': 'connected', 'type': 'smf', 'label': label})

    # ---------------------------------------------------------------- sample services
    def services(self):
        """Pre-provision services on some ONTs so the graph opens with real subscribers in it."""
        nb = self.nb
        role = nb.first('dcim/device-roles/', slug='ont')
        onts = sorted(nb.list('dcim/devices/', role_id=role['id']), key=lambda d: d['name'])
        for n, ont in enumerate(onts):
            ifs = {i['name']: i for i in nb.list('dcim/interfaces/', device_id=ont['id'])}
            plan = []
            if n % 3 != 2:
                plan.append(('wan0', 'hsi'))
            if n % 3 == 0:
                plan.append(('voip1', 'voip'))
            if n % 7 == 3:
                plan.append(('eth1', 'ethernet'))
            for iname, svc in plan:
                iface = ifs[iname]
                if svc != 'ethernet' and nb.first('circuits/virtual-circuit-terminations/', interface_id=iface['id']):
                    continue
                if svc == 'ethernet' and nb.first('dcim/interfaces/', parent_id=iface['id']):
                    continue
                try:
                    r = provision_service(nb, iface['id'], svc)
                    log.info('  * %s %s on %s:%s', r['virtual_circuit']['cid'], svc, ont['name'], iname)
                except ProvisionError as exc:
                    log.warning('  ! %s on %s:%s skipped: %s', svc, ont['name'], iname, exc)

    def permissions(self):
        """NetBox groups that OIDC users are mapped into (AUTH_MODE=oidc): editors may change everything nb_graph
        touches, viewers may only read. Re-running refreshes the object type list."""
        nb = self.nb
        types = sorted(f"{t['app_label']}.{t['model']}"
                       for app in ('dcim', 'ipam', 'circuits', 'tenancy', 'netbox_numbers')
                       for t in nb.list('core/object-types/', app_label=app))
        for group, actions in (('nbgraph-editors', ['view', 'add', 'change', 'delete']),
                               ('nbgraph-viewers', ['view'])):
            grp = self.goc('users/groups/', {'name': group}, {'name': group, 'description': 'nb_graph OIDC role'})
            body = {'name': group, 'enabled': True, 'object_types': types, 'actions': actions, 'groups': [grp['id']],
                    'description': f'nb_graph: {"read/write" if len(actions) > 1 else "read-only"} on network objects'}
            perm = nb.first('users/permissions/', name=group)
            if perm:
                nb.patch(f'users/permissions/{perm["id"]}/', body)
            else:
                nb.post('users/permissions/', body)

    def webhook(self, url: str, secret: str):
        """NetBox event rule -> webhook -> nb_graph, so edits made in NetBox's own UI update the graph live."""
        nb = self.nb
        wh = self.goc('extras/webhooks/', {'name': 'nb_graph live events'}, {
            'name': 'nb_graph live events', 'payload_url': url, 'http_method': 'POST',
            'http_content_type': 'application/json', 'additional_headers': f'X-NBGraph-Secret: {secret}',
            'ssl_verification': False})
        types = ['dcim.region', 'dcim.site', 'dcim.location', 'dcim.device', 'dcim.interface', 'dcim.cable',
                 'ipam.ipaddress', 'ipam.prefix', 'ipam.vlan', 'circuits.circuit', 'circuits.virtualcircuit',
                 'tenancy.tenant', 'netbox_numbers.telephonenumber']
        self.goc('extras/event-rules/', {'name': 'nb_graph live events'}, {
            'name': 'nb_graph live events', 'object_types': types, 'enabled': True,
            'event_types': ['object_created', 'object_updated', 'object_deleted'],
            'action_type': 'webhook', 'action_object_type': 'extras.webhook', 'action_object_id': wh['id']})

    def run(self, webhook_url: str | None = None, secret: str = ''):
        t0 = time.time()
        log.info('regions & catalogue')
        self.regions()
        self.catalog()
        for spec in SITES:
            log.info('site %s', spec[1])
            self.site(*spec)
        log.info('sample services')
        self.services()
        log.info('OIDC role groups and permissions')
        self.permissions()
        if webhook_url:
            self.webhook(webhook_url, secret)
        log.info('seed complete in %.1fs', time.time() - t0)


def wait_for_netbox(nb: NetBox, timeout: int = 600):
    deadline = time.time() + timeout
    while True:
        try:
            st = nb.status()
            log.info('NetBox %s is up', st.get('netbox-version'))
            return
        except Exception as exc:  # noqa: BLE001
            if time.time() > deadline:
                raise
            log.info('waiting for NetBox (%s)', exc.__class__.__name__)
            time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    if os.environ.get('SEED_DEMO_DATA', 'true').lower() in ('0', 'false', 'no'):
        log.info('SEED_DEMO_DATA is false, skipping demo data')
        return
    nb = NetBox()
    wait_for_netbox(nb)
    try:
        Seeder(nb).run(webhook_url=os.environ.get('SEED_WEBHOOK_URL'),
                       secret=os.environ.get('WEBHOOK_SECRET', 'nbgraph-demo-webhook'))
    except NetBoxError as exc:
        log.error('seed failed: %s', exc)
        sys.exit(1)


if __name__ == '__main__':
    main()
