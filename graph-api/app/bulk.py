"""
Bulk provisioning.

  plan   Read-only. Turns a scope (region, site, OLT, PON port or ONT) plus a service into the list of ONT
         ports that are eligible for it and still free. Pure SQL on NetBox's tables, so it is instant.
  run    A background job that provisions each planned port in turn through provision_service(). Every
         port is its own saga, so a failure rolls back only that port and the job carries on (unless
         stop_on_error is set). Progress is polled through GET /api/provision/bulk/{job_id}, and every
         port also goes out as a live event, so open graphs update while the job runs.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from typing import Callable

from . import db
from .graph import parse_id
from .netbox import NetBox
from .provision import SERVICES, ProvisionError, eligible_services, provision_service

log = logging.getLogger('nbgraph.bulk')

MAX_TARGETS = 500
KEEP_JOBS = 20

_ONTS_BY_SCOPE = {
    'region': """SELECT d.id AS id FROM public.dcim_device d
                   JOIN public.dcim_devicerole r ON r.id = d.role_id AND r.slug = 'ont'
                   JOIN public.dcim_site s ON s.id = d.site_id
                   JOIN public.dcim_region sr ON sr.id = s.region_id
                   JOIN public.dcim_region top ON top.id = %(id)s AND sr.path <@ top.path""",
    'site': """SELECT d.id AS id FROM public.dcim_device d
                 JOIN public.dcim_devicerole r ON r.id = d.role_id AND r.slug = 'ont'
                WHERE d.site_id = %(id)s""",
    # OLT -> its PON ports -> FEEDS (NetBox's completed cable paths through the splitters) -> ONTs
    'olt': """SELECT f.dst_id AS id FROM public.dcim_interface i,
                     LATERAL nbgraph.neighbors('interface', i.id, 'out', ARRAY['FEEDS']) f
               WHERE i.device_id = %(id)s""",
    'pon': """SELECT f.dst_id AS id FROM nbgraph.neighbors('interface', %(id)s, 'out', ARRAY['FEEDS']) f""",
    'ont': 'SELECT %(id)s::bigint AS id',
}

_CANDIDATES = """
SELECT i.id AS interface_id, i.name::text AS interface, i.type::text AS type, d.id AS device_id,
       d.name::text AS device, s.name::text AS site,
       EXISTS (SELECT 1 FROM public.circuits_virtualcircuittermination t
                 JOIN public.dcim_interface ti ON ti.id = t.interface_id
                WHERE ti.id = i.id OR ti.parent_id = i.id) AS busy
  FROM public.dcim_interface i
  JOIN public.dcim_device d ON d.id = i.device_id
  JOIN public.dcim_site s ON s.id = d.site_id
 WHERE i.device_id = ANY(%(onts)s) AND i.parent_id IS NULL
 ORDER BY d.name, i.name
"""


def _scope_kind(scope: str) -> tuple[str, int]:
    kind, nb_id = parse_id(scope)
    if kind in ('region', 'site'):
        return kind, nb_id
    if kind == 'device':
        row = db.query_one('SELECT r.slug FROM public.dcim_device d JOIN public.dcim_devicerole r '
                           'ON r.id = d.role_id WHERE d.id = %s', (nb_id,))
        if row and row['slug'] in ('olt', 'ont'):
            return row['slug'], nb_id
    if kind == 'interface':
        row = db.query_one("SELECT type FROM public.dcim_interface WHERE id = %s", (nb_id,))
        if row and row['type'] in ('gpon', 'xgs-pon'):
            row = db.query_one('SELECT r.slug FROM public.dcim_interface i JOIN public.dcim_device d '
                               'ON d.id = i.device_id JOIN public.dcim_devicerole r ON r.id = d.role_id '
                               'WHERE i.id = %s', (nb_id,))
            if row and row['slug'] == 'olt':
                return 'pon', nb_id
    raise ProvisionError(f'Bulk scope must be a region, site, OLT, OLT PON port or ONT (got {scope})')


def plan(scope: str, service: str, limit: int = MAX_TARGETS) -> dict:
    if service not in SERVICES:
        raise ProvisionError(f'Unknown service "{service}". Choose one of {list(SERVICES)}')
    kind, nb_id = _scope_kind(scope)
    onts = sorted({r['id'] for r in db.query(_ONTS_BY_SCOPE[kind], {'id': nb_id})})
    rows = db.query(_CANDIDATES, {'onts': onts}) if onts else []
    eligible = [r for r in rows
                if service in eligible_services({'name': r['interface'], 'type': {'value': r['type']}})]
    free = [r for r in eligible if not r['busy']]
    targets = free[:max(0, min(limit, MAX_TARGETS))]
    for t in targets:
        t.pop('busy')
        t['node_id'] = f"interface:{t['interface_id']}"
    return {'scope': scope, 'scope_kind': kind, 'service': service, 'onts': len(onts),
            'eligible': len(eligible), 'already_provisioned': len(eligible) - len(free),
            'truncated': len(free) > len(targets), 'targets': targets}


# ------------------------------------------------------------------------------------------------ jobs
_jobs: OrderedDict[str, dict] = OrderedDict()
_lock = threading.Lock()


def _public(job: dict) -> dict:
    """Snapshot without private keys. Call with _lock held: the runner appends to results."""
    out = {k: v for k, v in job.items() if not k.startswith('_')}
    out['results'] = list(job['results'])
    return out


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return _public(job) if job else None


def list_jobs() -> list[dict]:
    with _lock:
        return [{k: v for k, v in _public(j).items() if k != 'results'} for j in reversed(_jobs.values())]


def cancel(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if job and job['status'] == 'running':
            job['_cancel'] = True
        return _public(job) if job else None


def start(targets: list[dict], service: str, *, scope: str | None = None, tenant_id: int | None = None,
          description: str = '', stop_on_error: bool = False,
          on_item: Callable[[dict], None] | None = None,
          nb_factory: Callable[[], NetBox] = NetBox) -> dict:
    job = {'id': uuid.uuid4().hex[:12], 'service': service, 'scope': scope, 'status': 'running',
           'total': len(targets), 'done': 0, 'ok': 0, 'failed': 0, 'stop_on_error': stop_on_error,
           'started': time.time(), 'finished': None, 'results': [], '_cancel': False}
    with _lock:
        _jobs[job['id']] = job
        while len(_jobs) > KEEP_JOBS:
            _jobs.popitem(last=False)

    def run():
        nb = nb_factory()
        try:
            for t in targets:
                if job['_cancel']:
                    with _lock:
                        job['status'] = 'cancelled'
                    break
                item = {'interface_id': t['interface_id'], 'interface': t.get('interface'),
                        'device': t.get('device')}
                try:
                    res = provision_service(nb, int(t['interface_id']), service, tenant_id, None, description)
                    item.update(status='provisioned', cid=res['virtual_circuit']['cid'],
                                result_interface_id=res['interface_id'])
                    job['ok'] += 1
                except ProvisionError as exc:
                    item.update(status='failed', error=str(exc))
                    job['failed'] += 1
                except Exception as exc:  # noqa: BLE001  keep the job alive, report the port
                    log.exception('bulk item %s failed', t['interface_id'])
                    item.update(status='failed', error=f'{exc.__class__.__name__}: {exc}')
                    job['failed'] += 1
                with _lock:
                    job['results'].append(item)
                    job['done'] += 1
                if on_item:
                    on_item(item)
                if item['status'] == 'failed' and stop_on_error:
                    job['status'] = 'stopped'
                    break
            if job['status'] == 'running':
                job['status'] = 'done'
        finally:
            job['finished'] = time.time()
            nb.close()
            log.info('bulk job %s %s: %d ok, %d failed of %d', job['id'], job['status'], job['ok'],
                     job['failed'], job['total'])

    with _lock:
        snapshot = _public(job)
    threading.Thread(target=run, name=f'bulk-{job["id"]}', daemon=True).start()
    return snapshot
