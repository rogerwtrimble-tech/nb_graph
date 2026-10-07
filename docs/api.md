# graph-api reference

Base URL: `http://localhost:8090` (direct) or `http://localhost:8080` (through the UI's nginx). Interactive
OpenAPI is at **`/docs`**. Node ids are `kind:id`, e.g. `device:42`, `interface:28`, `number:7`.

## Health & admin

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{graph_schema, postgres, netbox, netbox_public_url}` |
| POST | `/api/admin/graph/install` | re-apply `db/graph/0*.sql` |

## Graph (read, SQL)

| Method | Path | Query params | Returns |
|---|---|---|---|
| GET | `/api/graph/meta` | – | kinds, edge labels, lens → labels |
| GET | `/api/graph/roots` | `lens` | top-level regions (+ sites with no region) |
| GET | `/api/graph/node/{id}` | `lens` | one vertex (+ `degree`) |
| GET | `/api/graph/expand/{id}` | `dir=out\|in\|both`, `lens`, `labels=A,B`, `limit` | one-hop subgraph |
| GET | `/api/graph/traverse/{id}` | `depth≤10`, `dir`, `lens`, `labels`, `limit` | BFS subgraph (edges carry `depth`) |
| GET | `/api/graph/path` | `from`, `to`, `lens` or `labels`, `max_depth` | shortest path `{hops[], nodes, edges}` |
| GET | `/api/graph/search` | `q`, `kinds=a,b`, `limit` | vertices whose label/props match |
| GET | `/api/graph/subgraph` | `ids=a,b,c`, `lens` | the vertices + edges among them, `missing[]` |
| GET | `/api/graph/stats` | – | counts per kind/label, PG version |
| GET | `/api/graph/map` | – | `sites[]` (lat/long, device count, `roles{}`, active `services`, `node_id`), `links[]` (circuits whose A and Z ends are on two different placed sites), `unplaced` count |

Graph payload:

```json
{
  "nodes": [{"id": "interface:28", "kind": "interface", "nb_id": 28, "label": "wan0", "subtype": "virtual",
             "status": "provisioned", "layer": "physical", "kind_title": "Interface",
             "props": {"device": "chi-ont-0001", "service_class": "wan", "...": "..."},
             "api_path": "dcim/interfaces/28/", "ui_path": "dcim/interfaces/28/", "degree": 3}],
  "edges": [{"id": "ASSIGNED_IP:interface:28>ipaddress:12", "source": "interface:28",
             "target": "ipaddress:12", "label": "ASSIGNED_IP", "props": null}]
}
```

## CRUD (proxied to the NetBox REST API)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/schema/{kind}` | – | form fields (type, label, required, choices, FK endpoint) + `create` rules |
| GET | `/api/object/{kind}/{id}` | – | full NetBox object |
| POST | `/api/object/{kind}` | NetBox create body | e.g. `{"name":"X","slug":"x","region":3}` |
| PATCH | `/api/object/{kind}/{id}` | partial body | |
| DELETE | `/api/object/{kind}/{id}` | – | |
| GET | `/api/nb/{netbox path}` | – | read-only pass-through for FK pickers (`dcim/`, `ipam/`, `circuits/`, `tenancy/`, `plugins/numbers/`) |

NetBox validation errors come back as `400 {"detail": "NetBox rejected the request", "netbox": {field: [msg]}}`.

## Provisioning

| Method | Path | Body / params |
|---|---|---|
| GET | `/api/provision/interface/{interface_id}` | eligible services + current services |
| POST | `/api/provision/service` | `{interface_id, service: hsi\|voip\|ethernet, tenant_id?, tenant_name?, description?}` |
| DELETE | `/api/provision/service/{interface_id}` | `?vc_id=` (optional: only that service) |
| POST | `/api/provision/ont` | `{pon_interface_id, serial?, name?}` |
| POST | `/api/provision/bulk/plan` | `{scope, service, limit?}`: dry run. `scope` is a node id: `region:`, `site:`, OLT `device:`, OLT PON `interface:` or ONT `device:`. Returns `onts`, `eligible`, `already_provisioned`, `targets[]` |
| POST | `/api/provision/bulk` | `{scope \| interface_ids[], service, tenant_id?, description?, stop_on_error?, limit?}` → **202** job `{id, status, total, done, ok, failed, results[]}`. Returns 409 if nothing is left to provision |
| GET | `/api/provision/bulk` | recent jobs (the last 20, held in memory) |
| GET | `/api/provision/bulk/{job_id}` | job progress and per-port results (`cid` or `error`) |
| POST | `/api/provision/bulk/{job_id}/cancel` | stop after the current port |

## Events

| Method | Path | Notes |
|---|---|---|
| GET | `/api/events/stream` | `text/event-stream`, events named `change`: `{source, event, kind, id, display, user, ts}` |
| GET | `/api/events/recent` | last 50 events |
| POST | `/api/events/netbox` | NetBox webhook target. Header `X-NBGraph-Secret` must equal `WEBHOOK_SECRET`. |

## curl walkthrough

```bash
A=http://localhost:8090/api
curl -s $A/graph/roots | jq '.nodes[].label'
SITE=$(curl -s "$A/graph/search?q=chi-co-01&kinds=site" | jq -r '.results[0].id')
curl -s "$A/graph/expand/$SITE" | jq '.nodes[] | {id,label,subtype}'
ONT=$(curl -s "$A/graph/search?q=chi-ont-0002" | jq -r '.results[0].id')
PORT=$(curl -s "$A/graph/expand/$ONT" | jq -r '.nodes[] | select(.label=="eth2") | .nb_id')
curl -s -X POST $A/provision/service -H 'Content-Type: application/json' \
     -d "{\"interface_id\": $PORT, \"service\": \"ethernet\"}" | jq '{cid: .virtual_circuit.cid, vlan: .vlan.vid}'
curl -s -X DELETE $A/provision/service/$PORT | jq .status
curl -N $A/events/stream            # watch live changes
```
