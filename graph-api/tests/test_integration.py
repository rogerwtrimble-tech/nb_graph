"""
Integration tests against a running stack (seeded demo data).
    NBGRAPH_API=http://localhost:8090 python -m pytest -q
Skipped automatically when the API is not reachable.
"""
import os

import httpx
import pytest

API = os.environ.get('NBGRAPH_API', 'http://localhost:8090')


def _up():
    try:
        return httpx.get(f'{API}/api/health', timeout=2).json().get('graph_schema') == 'ready'
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _up(), reason=f'nb_graph API not reachable at {API}')
c = httpx.Client(base_url=API, timeout=60)


def test_health_reports_pg19_and_netbox():
    h = c.get('/api/health').json()
    assert h['postgres'].startswith('19')
    assert h['netbox'].startswith('4.7')


def test_roots_and_region_to_site_traverse():
    roots = c.get('/api/graph/roots').json()['nodes']
    assert roots and roots[0]['kind'] == 'region'
    g = c.get(f"/api/graph/traverse/{roots[0]['id']}", params={'depth': 4, 'labels': 'CONTAINS'}).json()
    assert any(n['kind'] == 'site' for n in g['nodes'])


def test_site_olt_pon_ont_interface_chain():
    site = c.get('/api/graph/search', params={'q': 'Chicago Central', 'kinds': 'site'}).json()['results'][0]
    olts = [n for n in c.get(f"/api/graph/expand/{site['id']}").json()['nodes'] if n['subtype'] == 'olt']
    assert olts
    pons = [n for n in c.get(f"/api/graph/expand/{olts[0]['id']}").json()['nodes']
            if n['props'].get('service_class') == 'pon' and n['degree'] > 0]
    assert pons
    feeds = c.get(f"/api/graph/expand/{pons[0]['id']}").json()
    onts = [n for n in feeds['nodes'] if n['subtype'] == 'ont']
    assert onts and any(e['label'] == 'FEEDS' for e in feeds['edges'])
    ports = {n['label'] for n in c.get(f"/api/graph/expand/{onts[0]['id']}").json()['nodes']}
    assert {'eth1', 'voip1', 'wan0', 'pon0'} <= ports


def test_cable_trace_ont_to_bng():
    ont = c.get('/api/graph/search', params={'q': 'mke-ont-0001'}).json()['results'][0]
    bng = c.get('/api/graph/search', params={'q': 'bng', 'kinds': 'device'}).json()['results'][0]
    p = c.get('/api/graph/path', params={'from': ont['id'], 'to': bng['id'],
                                         'labels': 'HAS_INTERFACE,HAS_PORT,MAPS,CABLED,PART_OF'}).json()
    kinds = [h.split(':')[0] for h in p['hops']]
    assert 'frontport' in kinds and 'rearport' in kinds and 'circuit' in kinds


def test_provision_and_deprovision_ethernet_roundtrip():
    ont = c.get('/api/graph/search', params={'q': 'npv-ont-0002'}).json()['results'][0]
    eth4 = [n for n in c.get(f"/api/graph/expand/{ont['id']}").json()['nodes'] if n['label'] == 'eth4'][0]
    r = c.post('/api/provision/service', json={'interface_id': eth4['nb_id'], 'service': 'ethernet'})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['virtual_circuit']['cid'].startswith('BUSI-NPV-')
    info = c.get(f"/api/provision/interface/{eth4['nb_id']}").json()
    assert len(info['services']) >= 1
    d = c.delete(f"/api/provision/service/{eth4['nb_id']}", params={'vc_id': body['virtual_circuit']['id']})
    assert d.status_code == 200 and d.json()['status'] == 'deprovisioned'


def test_wrong_service_is_rejected():
    ont = c.get('/api/graph/search', params={'q': 'aus-ont-0003'}).json()['results'][0]
    eth1 = [n for n in c.get(f"/api/graph/expand/{ont['id']}").json()['nodes'] if n['label'] == 'eth1'][0]
    r = c.post('/api/provision/service', json={'interface_id': eth1['nb_id'], 'service': 'voip'})
    assert r.status_code == 400


def test_crud_roundtrip_region():
    r = c.post('/api/object/region', json={'name': 'pytest region', 'slug': 'pytest-region'})
    assert r.status_code == 200, r.text
    rid = r.json()['id']
    assert c.patch(f'/api/object/region/{rid}', json={'description': 'x'}).json()['description'] == 'x'
    assert c.get(f'/api/graph/node/region:{rid}').json()['label'] == 'pytest region'
    assert c.delete(f'/api/object/region/{rid}').status_code == 200


def test_validation_errors_surface_netbox_detail():
    r = c.post('/api/object/site', json={'name': 'no slug'})
    assert r.status_code == 400
    assert 'slug' in r.json()['netbox']


def test_map_places_seeded_sites_and_backhaul_links():
    m = c.get('/api/graph/map').json()
    sites = {s['slug']: s for s in m['sites']}
    chi = sites['chi-co-01']
    assert chi['latitude'] == pytest.approx(41.8781) and chi['longitude'] == pytest.approx(-87.6298)
    assert chi['roles'].get('bng') == 1 and chi['devices'] > 0 and chi['node_id'] == f"site:{chi['id']}"
    # every non-hub site has a metro backhaul circuit to the hub
    hub_links = {l['a_site_id'] for l in m['links'] if l['z_site_id'] == chi['id']}
    assert {sites[s]['id'] for s in ('npv-co-01', 'mke-co-01', 'aus-co-01')} <= hub_links
    assert m['unplaced'] == sum(1 for s in m['sites'] if s['latitude'] is None)


def _plan(scope, service):
    r = c.post('/api/provision/bulk/plan', json={'scope': scope, 'service': service})
    assert r.status_code == 200, r.text
    return r.json()


def test_bulk_plan_scopes_agree():
    site = c.get('/api/graph/search', params={'q': 'Milwaukee CO', 'kinds': 'site'}).json()['results'][0]
    olt = next(n for n in c.get(f"/api/graph/expand/{site['id']}").json()['nodes'] if n['subtype'] == 'olt')
    pons = [n for n in c.get(f"/api/graph/expand/{olt['id']}").json()['nodes']
            if n['props'].get('service_class') == 'pon']
    by_site, by_olt = _plan(site['id'], 'voip'), _plan(olt['id'], 'voip')
    by_pons = [_plan(p['id'], 'voip') for p in pons]
    # Milwaukee has one OLT, so site, OLT and the sum of its PON ports all see the same ONTs and ports
    assert by_site['onts'] == by_olt['onts'] == sum(p['onts'] for p in by_pons) > 0
    assert {t['interface_id'] for t in by_site['targets']} == {t['interface_id'] for t in by_olt['targets']}
    assert all(t['interface'].startswith('voip') for t in by_site['targets'])
    assert by_site['eligible'] == by_site['already_provisioned'] + len(by_site['targets'])


def test_bulk_plan_rejects_bad_scope_and_service():
    assert c.post('/api/provision/bulk/plan', json={'scope': 'tenant:1', 'service': 'hsi'}).status_code == 400
    assert c.post('/api/provision/bulk/plan', json={'scope': 'site:1', 'service': 'iptv'}).status_code == 400


def test_bulk_job_provisions_every_target_then_cleanup():
    import time
    ont = c.get('/api/graph/search', params={'q': 'aus-ont-0002', 'kinds': 'device'}).json()['results'][0]
    plan = _plan(ont['id'], 'hsi')
    if not plan['targets']:  # left over from an aborted run: free the port first
        wan = next(n for n in c.get(f"/api/graph/expand/{ont['id']}").json()['nodes'] if n['label'] == 'wan0')
        c.delete(f"/api/provision/service/{wan['nb_id']}")
        plan = _plan(ont['id'], 'hsi')
    assert len(plan['targets']) == 1
    job = c.post('/api/provision/bulk', json={'scope': ont['id'], 'service': 'hsi'})
    assert job.status_code == 202, job.text
    jid = job.json()['id']
    for _ in range(60):
        j = c.get(f'/api/provision/bulk/{jid}').json()
        if j['status'] != 'running':
            break
        time.sleep(0.5)
    assert j['status'] == 'done' and j['ok'] == 1 and j['failed'] == 0, j
    assert j['results'][0]['cid'].startswith('HSI-AUS-')
    assert _plan(ont['id'], 'hsi')['targets'] == []          # now provisioned, so nothing left to plan
    assert c.post('/api/provision/bulk', json={'scope': ont['id'], 'service': 'hsi'}).status_code == 409
    assert any(x['id'] == jid for x in c.get('/api/provision/bulk').json()['jobs'])
    assert c.delete(f"/api/provision/service/{plan['targets'][0]['interface_id']}").status_code == 200
