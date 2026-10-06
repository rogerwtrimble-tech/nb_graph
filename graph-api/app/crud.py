"""
CRUD for graph nodes, proxied to the NetBox REST API.

The browser never sees the NetBox token. Every write goes through NetBox, so its validation,
permissions, change log and webhooks all apply. Form schemas combine a curated list of fields per
kind with NetBox's own OPTIONS metadata (labels, types, required, choices).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from . import db
from .events import hub
from .netbox import NetBox, NetBoxError

router = APIRouter(prefix='/api', tags=['crud'])

ALLOWED_PREFIXES = ('dcim/', 'ipam/', 'circuits/', 'tenancy/', 'plugins/numbers/', 'status/')

# Curated editable fields per kind. FK fields name the endpoint the UI should search.
FK = {
    'region': 'dcim/regions/', 'parent:region': 'dcim/regions/', 'site': 'dcim/sites/',
    'location': 'dcim/locations/', 'parent:location': 'dcim/locations/', 'tenant': 'tenancy/tenants/',
    'role:device': 'dcim/device-roles/', 'role:prefix': 'ipam/roles/', 'role:vlan': 'ipam/roles/',
    'device_type': 'dcim/device-types/', 'device': 'dcim/devices/', 'untagged_vlan': 'ipam/vlans/',
    'qinq_svlan': 'ipam/vlans/', 'group:vlan': 'ipam/vlan-groups/', 'group:tenant': 'tenancy/tenant-groups/',
    'provider': 'circuits/providers/', 'type:circuit': 'circuits/circuit-types/',
    'type:virtualcircuit': 'circuits/virtual-circuit-types/', 'provider_network': 'circuits/provider-networks/',
    'interface': 'dcim/interfaces/', 'parent:interface': 'dcim/interfaces/', 'vrf': 'ipam/vrfs/',
    'platform': 'dcim/platforms/', 'rack': 'dcim/racks/', 'circuit': 'circuits/circuits/',
    'primary_ip4': 'ipam/ip-addresses/',
}
FORMS: dict[str, list[str]] = {
    'region': ['name', 'slug', 'parent', 'description'],
    'site': ['name', 'slug', 'status', 'region', 'tenant', 'facility', 'time_zone', 'latitude', 'longitude',
             'description'],
    'location': ['name', 'slug', 'site', 'parent', 'status', 'tenant', 'description'],
    'device': ['name', 'role', 'device_type', 'site', 'location', 'status', 'tenant', 'serial', 'primary_ip4',
               'description'],
    'interface': ['device', 'name', 'type', 'enabled', 'parent', 'mode', 'untagged_vlan', 'qinq_svlan', 'mtu',
                  'mgmt_only', 'description'],
    'ipaddress': ['address', 'status', 'role', 'tenant', 'dns_name', 'assigned_object_type', 'assigned_object_id',
                  'description'],
    'prefix': ['prefix', 'status', 'role', 'scope_type', 'scope_id', 'tenant', 'is_pool', 'description'],
    'vlangroup': ['name', 'slug', 'scope_type', 'scope_id', 'description'],
    'vlan': ['vid', 'name', 'status', 'group', 'tenant', 'qinq_role', 'qinq_svlan', 'description'],
    'number': ['number', 'status', 'site', 'tenant', 'interface', 'sip_username', 'description'],
    'virtualcircuit': ['cid', 'provider_network', 'type', 'status', 'tenant', 'description'],
    'circuit': ['cid', 'provider', 'type', 'status', 'tenant', 'commit_rate', 'description'],
    'tenant': ['name', 'slug', 'group', 'description'],
    'provider': ['name', 'slug', 'description'],
    'frontport': ['device', 'name', 'type', 'description'],
    'rearport': ['device', 'name', 'type', 'positions', 'description'],
    'circuittermination': ['circuit', 'term_side', 'port_speed', 'description'],
}

# Which children can be created from a node in the graph, and which fields to prefill.
CREATE_RULES: dict[str, list[dict]] = {
    'region': [{'kind': 'region', 'title': 'Sub-region', 'prefill': {'parent': '$id'}},
               {'kind': 'site', 'title': 'Site', 'prefill': {'region': '$id', 'status': 'active'}}],
    'site': [{'kind': 'device', 'title': 'Device (OLT, BNG, ...)', 'prefill': {'site': '$id', 'status': 'active'}},
             {'kind': 'location', 'title': 'Location', 'prefill': {'site': '$id', 'status': 'active'}},
             {'kind': 'prefix', 'title': 'Prefix (IP pool)',
              'prefill': {'scope_type': 'dcim.site', 'scope_id': '$id', 'status': 'active'}},
             {'kind': 'vlangroup', 'title': 'VLAN group', 'prefill': {'scope_type': 'dcim.site', 'scope_id': '$id'}},
             {'kind': 'number', 'title': 'Telephone number', 'prefill': {'site': '$id', 'status': 'available'}}],
    'location': [{'kind': 'device', 'title': 'Device', 'prefill': {'location': '$id', 'site': '$props.site_id',
                                                                    'status': 'active'}}],
    'device': [{'kind': 'interface', 'title': 'Interface', 'prefill': {'device': '$id', 'type': 'virtual'}}],
    'interface': [{'kind': 'ipaddress', 'title': 'IP address',
                   'prefill': {'assigned_object_type': 'dcim.interface', 'assigned_object_id': '$id',
                               'status': 'active'}},
                  {'kind': 'interface', 'title': 'Sub-interface',
                   'prefill': {'device': '$props.device_id', 'parent': '$id', 'type': 'virtual'}}],
    'vlangroup': [{'kind': 'vlan', 'title': 'VLAN', 'prefill': {'group': '$id', 'status': 'active'}}],
    'prefix': [{'kind': 'ipaddress', 'title': 'IP address', 'prefill': {'status': 'active'}}],
    'tenant': [],
}


def nb() -> NetBox:
    return NetBox()


def kind_api(kind: str) -> str:
    row = db.query_one('SELECT api_path FROM nbgraph.kind WHERE kind = %s', (kind,))
    if not row:
        raise HTTPException(404, f'unknown kind {kind}')
    return row['api_path']


def _err(exc: NetBoxError) -> JSONResponse:
    return JSONResponse(status_code=exc.status if exc.status < 500 else 502,
                        content={'detail': 'NetBox rejected the request', 'netbox': exc.detail})


@lru_cache(maxsize=64)
def _options(api_path: str) -> dict:
    return NetBox().options(api_path)


@router.get('/schema/{kind}')
def schema(kind: str):
    api_path = kind_api(kind)
    try:
        meta = _options(api_path).get('actions', {}).get('POST', {})
    except NetBoxError as exc:
        return _err(exc)
    fields = []
    for name in FORMS.get(kind, []):
        m = meta.get(name, {})
        ftype = m.get('type', 'string')
        f: dict[str, Any] = {'name': name, 'label': m.get('label', name.replace('_', ' ').title()),
                             'required': bool(m.get('required')), 'help': m.get('help_text', ''),
                             'read_only': bool(m.get('read_only'))}
        endpoint = FK.get(f'{name}:{kind}') or FK.get(name)
        if name in ('scope_type', 'assigned_object_type'):
            f['type'] = 'string'
        elif name in ('scope_id', 'assigned_object_id'):
            f['type'] = 'integer'
        elif endpoint and ftype in ('field', 'nested object', 'related field', 'integer'):
            f.update(type='fk', endpoint=endpoint)
        elif m.get('choices'):
            f.update(type='choice', choices=[{'value': c['value'], 'label': c['display_name']} for c in m['choices']])
        elif ftype == 'boolean':
            f['type'] = 'boolean'
        elif ftype == 'integer':
            f['type'] = 'integer'
        elif ftype in ('decimal', 'float'):
            f['type'] = 'number'
        else:
            f['type'] = 'string'
        if name in ('slug',):
            f['slug_from'] = 'name'
        fields.append(f)
    return {'kind': kind, 'api_path': api_path, 'fields': fields, 'create': CREATE_RULES.get(kind, [])}


@router.get('/object/{kind}/{nb_id}')
def get_object(kind: str, nb_id: int):
    try:
        return nb().get(f'{kind_api(kind)}{nb_id}/')
    except NetBoxError as exc:
        return _err(exc)


@router.post('/object/{kind}')
def create_object(kind: str, body: dict = Body(...)):
    try:
        obj = nb().post(kind_api(kind), body)
    except NetBoxError as exc:
        return _err(exc)
    hub.publish({'source': 'nb_graph', 'event': 'created', 'kind': kind, 'id': f'{kind}:{obj["id"]}',
                 'display': obj.get('display')})
    return obj


@router.patch('/object/{kind}/{nb_id}')
def update_object(kind: str, nb_id: int, body: dict = Body(...)):
    try:
        obj = nb().patch(f'{kind_api(kind)}{nb_id}/', body)
    except NetBoxError as exc:
        return _err(exc)
    hub.publish({'source': 'nb_graph', 'event': 'updated', 'kind': kind, 'id': f'{kind}:{nb_id}',
                 'display': obj.get('display')})
    return obj


@router.delete('/object/{kind}/{nb_id}')
def delete_object(kind: str, nb_id: int):
    try:
        nb().delete(f'{kind_api(kind)}{nb_id}/')
    except NetBoxError as exc:
        return _err(exc)
    hub.publish({'source': 'nb_graph', 'event': 'deleted', 'kind': kind, 'id': f'{kind}:{nb_id}'})
    return {'deleted': f'{kind}:{nb_id}'}


@router.api_route('/nb/{path:path}', methods=['GET', 'OPTIONS'])
async def passthrough(path: str, request: Request):
    """Read-only pass-through used by the UI's search-as-you-type FK pickers."""
    if not path.endswith('/'):
        path += '/'
    if not path.startswith(ALLOWED_PREFIXES):
        raise HTTPException(403, 'path not allowed')
    client = nb()
    try:
        data = client.request(request.method, path, params=dict(request.query_params))
    except NetBoxError as exc:
        return _err(exc)
    finally:
        client.close()
    return data
