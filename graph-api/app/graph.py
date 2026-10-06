"""Graph read API over the nbgraph.* projection."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from . import db

router = APIRouter(prefix='/api/graph', tags=['graph'])

KINDS_SQL = 'SELECT kind, title, layer, api_path, ui_path FROM nbgraph.kind ORDER BY kind'
VERTEX_COLS = 'id, kind, nb_id, label, subtype, status, layer, kind_title, props, api_path, ui_path'


@lru_cache
def lens_labels() -> dict[str, list[str]]:
    rows = db.query('SELECT label, lens FROM nbgraph.edge_label')
    out: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for lens in r['lens']:
            out[lens].append(r['label'])
    return dict(out)


def resolve_labels(lens: str | None, labels: str | None) -> list[str] | None:
    if labels:
        return [s.strip().upper() for s in labels.split(',') if s.strip()]
    if not lens or lens == 'all':
        return None
    lens_map = lens_labels()
    if lens not in lens_map:
        raise HTTPException(400, f'unknown lens "{lens}" (choose {", ".join(sorted(lens_map))} or all)')
    return lens_map[lens]


def parse_id(node_id: str) -> tuple[str, int]:
    try:
        kind, nb_id = node_id.split(':', 1)
        return kind, int(nb_id)
    except ValueError as exc:
        raise HTTPException(400, f'bad node id "{node_id}", expected kind:id') from exc


def fetch_vertices(ids: list[str], labels: list[str] | None = None, with_degree: bool = True) -> list[dict]:
    """Load vertices grouped by kind, so each query prunes down to a single UNION ALL branch."""
    by_kind: dict[str, list[int]] = defaultdict(list)
    for i in dict.fromkeys(ids):
        k, n = parse_id(i)
        by_kind[k].append(n)
    out: list[dict] = []
    for kind, nb_ids in by_kind.items():
        rows = db.query(f'SELECT {VERTEX_COLS} FROM nbgraph.vertices WHERE kind = %s AND nb_id = ANY(%s)',
                        (kind, nb_ids))
        if with_degree:
            deg = {r['nb_id']: r['degree'] for r in
                   db.query('SELECT * FROM nbgraph.out_degree(%s, %s, %s)', (kind, nb_ids, labels))}
            for r in rows:
                r['degree'] = deg.get(r['nb_id'], 0)
        out.extend(rows)
    return out


def edge_rows_to_graph(rows: list[dict], labels: list[str] | None, seed: list[str] | None = None) -> dict:
    edges = {}
    node_ids = list(seed or [])
    for r in rows:
        src = f"{r['src_kind']}:{r['src_id']}"
        dst = f"{r['dst_kind']}:{r['dst_id']}"
        eid = f"{r['label']}:{src}>{dst}"
        edges[eid] = {'id': eid, 'source': src, 'target': dst, 'label': r['label'], 'props': r.get('props'),
                      **({'depth': r['depth']} if 'depth' in r else {})}
        node_ids += [src, dst]
    return {'nodes': fetch_vertices(node_ids, labels), 'edges': list(edges.values())}


# ------------------------------------------------------------------------------------------------ routes
@router.get('/meta')
def meta():
    return {
        'kinds': db.query(KINDS_SQL),
        'edge_labels': db.query('SELECT label, description, lens FROM nbgraph.edge_label ORDER BY label'),
        'lenses': {k: sorted(v) for k, v in lens_labels().items()},
    }


@router.get('/roots')
def roots(lens: str = 'service'):
    """Entry points: top-level regions, plus any site without a region."""
    labels = resolve_labels(lens, None)
    ids = [r['id'] for r in db.query(
        "SELECT id FROM nbgraph.vertices WHERE kind = 'region' AND (props->>'parent_id') IS NULL "
        "UNION ALL SELECT 'site:' || s.id FROM public.dcim_site s WHERE s.region_id IS NULL")]
    return {'nodes': fetch_vertices(ids, labels), 'edges': []}


@router.get('/node/{node_id}')
def node(node_id: str, lens: str = 'service'):
    res = fetch_vertices([node_id], resolve_labels(lens, None))
    if not res:
        raise HTTPException(404, f'{node_id} not found')
    return res[0]


@router.get('/expand/{node_id}')
def expand(node_id: str, dir: str = Query('out', pattern='^(out|in|both)$'), lens: str = 'service',
           labels: str | None = None, limit: int = Query(500, le=5000)):
    kind, nb_id = parse_id(node_id)
    lbls = resolve_labels(lens, labels)
    rows = db.query('SELECT * FROM nbgraph.neighbors(%s, %s, %s, %s) LIMIT %s', (kind, nb_id, dir, lbls, limit))
    g = edge_rows_to_graph(rows, lbls, seed=[node_id])
    g['truncated'] = len(rows) >= limit
    return g


@router.get('/traverse/{node_id}')
def traverse(node_id: str, depth: int = Query(2, ge=1, le=10), dir: str = Query('out', pattern='^(out|in|both)$'),
             lens: str = 'service', labels: str | None = None, limit: int = Query(1500, le=5000)):
    kind, nb_id = parse_id(node_id)
    lbls = resolve_labels(lens, labels)
    rows = db.query('SELECT * FROM nbgraph.traverse(%s, %s, %s, %s, %s, %s)', (kind, nb_id, depth, lbls, dir, limit))
    g = edge_rows_to_graph(rows, lbls, seed=[node_id])
    g['truncated'] = len(rows) >= limit
    return g


@router.get('/path')
def path(src: str = Query(..., alias='from'), dst: str = Query(..., alias='to'), lens: str = 'all',
         labels: str | None = None, max_depth: int = Query(12, le=20)):
    """Undirected shortest path. Use labels=HAS_INTERFACE,HAS_PORT,MAPS,CABLED,PART_OF for a pure cable trace."""
    a_kind, a_id = parse_id(src)
    b_kind, b_id = parse_id(dst)
    lbls = resolve_labels(lens, labels)
    hops = db.query('SELECT * FROM nbgraph.shortest_path(%s, %s, %s, %s, %s, %s)',
                    (a_kind, a_id, b_kind, b_id, max_depth, lbls))
    if not hops:
        raise HTTPException(404, f'no path between {src} and {dst} within {max_depth} hops')
    edges = []
    for prev, cur in zip(hops, hops[1:]):
        s, t = (prev['node'], cur['node']) if cur['via_dir'] == 'out' else (cur['node'], prev['node'])
        edges.append({'id': f"{cur['via_label']}:{s}>{t}", 'source': s, 'target': t, 'label': cur['via_label']})
    return {'nodes': fetch_vertices([h['node'] for h in hops], lbls), 'edges': edges,
            'hops': [h['node'] for h in hops]}


@router.get('/search')
def search(q: str = Query(..., min_length=1), kinds: str | None = None, limit: int = Query(25, le=200)):
    kind_list = [k.strip() for k in kinds.split(',')] if kinds else None
    rows = db.query(
        f'SELECT {VERTEX_COLS} FROM nbgraph.vertices '
        'WHERE (label ILIKE %(p)s OR props::text ILIKE %(p)s) AND (%(k)s::text[] IS NULL OR kind = ANY(%(k)s)) '
        'ORDER BY (label ILIKE %(s)s) DESC, length(label), label LIMIT %(n)s',
        {'p': f'%{q}%', 's': f'{q}%', 'k': kind_list, 'n': limit})
    return {'results': rows}


@router.get('/stats')
def stats():
    rows = db.query('SELECT element, name, total FROM nbgraph.stats ORDER BY element, name')
    return {
        'vertices': {r['name']: r['total'] for r in rows if r['element'] == 'vertex'},
        'edges': {r['name']: r['total'] for r in rows if r['element'] == 'edge'},
        'postgres': db.server_version(),
    }


@router.get('/subgraph')
def subgraph(ids: str = Query(..., description='comma separated node ids'), lens: str = 'service'):
    """Reload a set of nodes plus the edges between them (used by the UI after live events)."""
    lbls = resolve_labels(lens, None)
    id_list = [i for i in ids.split(',') if i]
    nodes = fetch_vertices(id_list, lbls)
    present = {n['id'] for n in nodes}
    by_kind: dict[str, list[int]] = defaultdict(list)
    for i in present:
        k, n = parse_id(i)
        by_kind[k].append(n)
    edges = []
    for kind, nb_ids in by_kind.items():
        for r in db.query('SELECT e.* FROM nbgraph.edges_fn() e WHERE e.src_kind = %s AND e.src_id = ANY(%s) '
                          'AND (%s::text[] IS NULL OR e.label = ANY(%s))', (kind, nb_ids, lbls, lbls)):
            s, t = f"{r['src_kind']}:{r['src_id']}", f"{r['dst_kind']}:{r['dst_id']}"
            if t in present:
                edges.append({'id': f"{r['label']}:{s}>{t}", 'source': s, 'target': t, 'label': r['label'],
                              'props': r['props']})
    return {'nodes': nodes, 'edges': edges, 'missing': sorted(set(id_list) - present)}
