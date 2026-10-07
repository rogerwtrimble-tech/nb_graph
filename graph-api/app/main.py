"""nb_graph API: a graph view over NetBox + CRUD and provisioning through the NetBox REST API."""
from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import bulk, crud, db, graph
from .events import hub, router as events_router
from .netbox import NetBox, NetBoxError
from .provision import ProvisionError, add_ont, deprovision_service, interface_services, provision_service
from .settings import get_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
log = logging.getLogger('nbgraph')

state = {'graph_schema': 'pending', 'applied': []}


def _install():
    try:
        state['applied'] = db.install_graph_schema()
        state['graph_schema'] = 'ready'
        graph.lens_labels.cache_clear()
    except Exception as exc:  # noqa: BLE001
        state['graph_schema'] = f'error: {exc}'
        log.exception('graph schema install failed')


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.bind(asyncio.get_running_loop())
    if get_settings().graph_auto_install:
        threading.Thread(target=_install, daemon=True).start()
    yield


app = FastAPI(title='nb_graph API', version='0.1.0', lifespan=lifespan,
              description='Graph projection of NetBox (PostgreSQL 19) with CRUD + service provisioning')
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(','),
                   allow_methods=['*'], allow_headers=['*'])
app.include_router(graph.router)
app.include_router(crud.router)
app.include_router(events_router)


@app.exception_handler(ProvisionError)
async def provision_error(_, exc: ProvisionError):
    return JSONResponse(status_code=exc.status, content={'detail': str(exc), 'netbox': exc.detail})


@app.get('/api/health')
def health():
    s = get_settings()
    out = {'graph_schema': state['graph_schema'], 'netbox_public_url': s.netbox_public_url}
    try:
        out['postgres'] = db.server_version()
    except Exception as exc:  # noqa: BLE001
        out['postgres'] = f'error: {exc.__class__.__name__}'
    try:
        out['netbox'] = NetBox().status().get('netbox-version')
    except Exception as exc:  # noqa: BLE001
        out['netbox'] = f'error: {exc.__class__.__name__}'
    return out


@app.post('/api/admin/graph/install')
def reinstall():
    _install()
    return state


# ------------------------------------------------------------------------------------------- provisioning
def _publish_steps(result: dict, device_hint: str | None = None):
    hub.publish({'source': 'nb_graph', 'event': result.get('status'), 'kind': 'interface',
                 'id': f'interface:{result.get("interface_id")}', 'display': device_hint})


@app.get('/api/provision/interface/{interface_id}', tags=['provision'])
def provision_info(interface_id: int):
    try:
        return interface_services(NetBox(), interface_id)
    except NetBoxError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.post('/api/provision/service', tags=['provision'])
def provision(body: dict = Body(..., examples=[{'interface_id': 123, 'service': 'hsi'}])):
    if 'interface_id' not in body or 'service' not in body:
        raise HTTPException(422, 'interface_id and service are required')
    res = provision_service(NetBox(), int(body['interface_id']), body['service'], body.get('tenant_id'),
                            body.get('tenant_name'), body.get('description', ''))
    _publish_steps(res)
    if res['interface_id'] != int(body['interface_id']):
        hub.publish({'source': 'nb_graph', 'event': 'provisioned', 'kind': 'interface',
                     'id': f'interface:{body["interface_id"]}'})
    return res


@app.delete('/api/provision/service/{interface_id}', tags=['provision'])
def deprovision(interface_id: int, vc_id: int | None = None):
    res = deprovision_service(NetBox(), interface_id, vc_id)
    _publish_steps(res)
    return res


@app.post('/api/provision/ont', tags=['provision'])
def provision_ont(body: dict = Body(..., examples=[{'pon_interface_id': 11, 'serial': 'AOON123'}])):
    res = add_ont(NetBox(), int(body['pon_interface_id']), body.get('name'), body.get('serial', ''))
    hub.publish({'source': 'nb_graph', 'event': 'created', 'kind': 'device', 'id': f'device:{res["device"]["id"]}',
                 'display': res['device']['name']})
    hub.publish({'source': 'nb_graph', 'event': 'updated', 'kind': 'interface',
                 'id': f'interface:{body["pon_interface_id"]}'})
    return res


# ------------------------------------------------------------------------------------------- bulk
@app.post('/api/provision/bulk/plan', tags=['provision'])
def bulk_plan(body: dict = Body(..., examples=[{'scope': 'site:1', 'service': 'hsi'}])):
    """Dry run: the free ONT ports under a region / site / OLT / PON port / ONT that fit the service."""
    if 'scope' not in body or 'service' not in body:
        raise HTTPException(422, 'scope and service are required')
    return bulk.plan(body['scope'], body['service'], int(body.get('limit', bulk.MAX_TARGETS)))


@app.post('/api/provision/bulk', status_code=202, tags=['provision'])
def bulk_start(body: dict = Body(..., examples=[{'scope': 'site:1', 'service': 'hsi', 'limit': 10}])):
    """Start a background job. Give either a scope (planned server-side) or explicit interface_ids."""
    service = body.get('service')
    if not service:
        raise HTTPException(422, 'service is required')
    if body.get('interface_ids'):
        targets = [{'interface_id': int(i)} for i in body['interface_ids']][:bulk.MAX_TARGETS]
    elif body.get('scope'):
        targets = bulk.plan(body['scope'], service, int(body.get('limit', bulk.MAX_TARGETS)))['targets']
    else:
        raise HTTPException(422, 'scope or interface_ids is required')
    if not targets:
        raise HTTPException(409, 'nothing to provision: no free eligible ports in that scope')

    def on_item(item: dict):
        hub.publish({'source': 'nb_graph', 'event': item['status'], 'kind': 'interface',
                     'id': f'interface:{item["interface_id"]}', 'display': item.get('device')})

    return bulk.start(targets, service, scope=body.get('scope'), tenant_id=body.get('tenant_id'),
                      description=body.get('description', ''), stop_on_error=bool(body.get('stop_on_error')),
                      on_item=on_item)


@app.get('/api/provision/bulk', tags=['provision'])
def bulk_jobs():
    return {'jobs': bulk.list_jobs()}


@app.get('/api/provision/bulk/{job_id}', tags=['provision'])
def bulk_job(job_id: str):
    job = bulk.get_job(job_id)
    if not job:
        raise HTTPException(404, f'no bulk job {job_id}')
    return job


@app.post('/api/provision/bulk/{job_id}/cancel', tags=['provision'])
def bulk_cancel(job_id: str):
    job = bulk.cancel(job_id)
    if not job:
        raise HTTPException(404, f'no bulk job {job_id}')
    return job
