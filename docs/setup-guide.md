# Setup guide

## Prerequisites

| Need | Version | Notes |
|---|---|---|
| Rancher Desktop | 1.x with **dockerd (moby)** | or Docker Desktop / Docker Engine + Compose v2 |
| RAM for the VM | ≥ 6 GB (8 GB recommended) | NetBox + PG19 + builds |
| git | any | |
| python3 | optional | only for `scripts/gen-env.py`, `make test` |
| Node 22 | optional | only for UI development (`make ui-dev`) |

## First run (10 minutes)

1. **Configure Rancher Desktop** ([docker-setup.md §1](docker-setup.md#1-configure-rancher-desktop)).
2. **Clone and configure**
   ```bash
   git clone https://github.com/rogerwtrimble-tech/nb_graph.git && cd nb_graph
   cp .env.example .env            # demo defaults
   ```
3. **Start**
   ```bash
   docker compose up -d --build
   docker compose logs -f seed     # Ctrl-C after "seed complete"
   ```
4. **Open** the UI at http://localhost:8080 and NetBox at http://localhost:8000 (`admin` / `admin`).

## Verification checklist

Work through these in the UI. Each one exercises a different layer of the stack.

| # | Do this | Expect | Proves |
|---|---|---|---|
| 1 | Open http://localhost:8080 | Left panel: *PostgreSQL 19beta4*, *NetBox 4.7.x*, *graph ready*. Canvas: region tree down to 4 sites. | PG19, NetBox, nbgraph schema |
| 2 | Double-click **Chicago Central Office** | OLTs `chi-olt-01/02`, BNG `chi-bng-01`, location *Subscriber Premises* | `HOSTS` / `CONTAINS` edges |
| 3 | Double-click `chi-olt-01`, then `pon1` | 8 PON ports + uplinks; `pon1` fans out (blue dashed `FEEDS`) to 4 ONTs and its S-VLAN | cable-trace-derived `FEEDS` |
| 4 | Double-click `chi-ont-0001` | `pon0`, `eth1-4`, `voip1-2`, `wan0`, plus the subscriber tenant. Provisioned ports have a green ring. | ONT interfaces |
| 5 | Double-click `wan0` | IP `100.64.1.x/24`, VLAN `100 CHI-HSI`, service `HSI-CHI-…` | number inventory + services |
| 6 | Click `voip2` → **Provision via NetBox API** | Step list (interface, IP, DID, VC), a green toast, and the node gains a ring | provisioning saga through the REST API |
| 7 | Same panel → **Deprovision** | VC/IP removed, DID released to *available* | rollback/teardown |
| 8 | Click `pon1` → *Add* tab → **Add ONT** | New `chi-ont-00xx` appears under `pon1` | topology CRUD + NetBox cable trace |
| 9 | Right-click `mke-ont-0001` (search for it) → **Cable trace to core** | Highlighted path ONT → splitter OUT/IN → OLT → metro circuit A/Z → BNG | physical graph traversal |
| 10 | In NetBox (http://localhost:8000) edit any ONT's description | Within ~1 s a toast says *"NetBox: device … updated"* and the node flashes | webhook → SSE live updates |
| 11 | Switch the lens to **Inventory** and expand a site | Prefixes, VLAN groups, DIDs (pink = assigned, faded = available) | inventory lens |
| 12 | `curl localhost:8090/docs` | Swagger UI | API |

Automated version (with the stack up):

```bash
cd graph-api
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
NBGRAPH_API=http://localhost:8090 pytest -q        # 16 tests: unit + live integration
```

## Day-2 operations

* **Re-seed or top up demo data:** `docker compose run --rm seed` (idempotent: existing objects are kept).
* **Start empty:** set `SEED_DEMO_DATA=false` in `.env`, then `docker compose down -v && docker compose up -d`.
* **Back up:** `docker compose exec postgres pg_dump -U netbox -Fc netbox > nb_graph.dump`
* **Restore:** `docker compose exec -T postgres pg_restore -U netbox -d netbox --clean < nb_graph.dump`
* **Explore the graph in SQL:** `make psql`, then see [graph-model.md](graph-model.md#example-queries).

## Local development without containers

```bash
# 1. start only the backing services + NetBox in compose
docker compose up -d postgres redis redis-cache netbox netbox-worker

# 2. graph-api with reload (port 8090)
cd graph-api && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://netbox:nbgraph-db-pass@localhost:5432/netbox \
       NETBOX_URL=http://localhost:8000 \
       NETBOX_TOKEN=nbt_nbgraphdemo1.0123456789abcdef0123456789abcdef01234567 \
       GRAPH_SQL_DIR=../db/graph
uvicorn app.main:app --reload --port 8090
python -m app.seed                                   # demo data

# 3. UI with hot reload (port 5173, proxies /api to 8090)
cd ui && npm install && npm run dev
```

Webhooks from the dockerised worker can't reach a graph-api running on the host unless you point the webhook at
`http://host.docker.internal:8090/api/events/netbox` (NetBox → *Operations → Webhooks*).

## Hardening (before anything beyond a demo)

| Area | Demo default | Do instead |
|---|---|---|
| Secrets | fixed values in `.env.example` | `make env`, or Docker secrets (netbox-docker reads `/run/secrets/*`) |
| graph-api → NetBox auth | superuser v2 token | A dedicated NetBox user with object permissions limited to the models nb_graph writes. Per-user tokens if the UI needs per-user audit. |
| UI / API auth | none | Put an authenticating proxy (OIDC) in front of `ui`, or add OAuth2 to FastAPI |
| DB access for the graph | `netbox` owner role | a read-only role with `USAGE` on `nbgraph` + `SELECT` on `public` |
| Transport | plain HTTP | TLS at the ingress |
| PostgreSQL | 19 **beta** | PG19 GA once released; for production, stay on a NetBox-supported major (15–18) until NetBox lists PG19 |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| graph-api health shows `graph_schema: pending` for minutes | It waits for NetBox's migrations, which is normal on first start. Check `docker compose logs netbox`. |
| `graph_schema: error: …` | A projection SQL file failed. The message names the statement. Fix it, then `make graph-install`. |
| Provisioning fails with *No available telephone numbers* | The site's DID pool is used up. Add numbers: right-click the site → *Add child → Telephone number*, or use NetBox → Plugins → Numbers. |
| *Splitter is full* when adding an ONT | All 16 splitter outputs are cabled. Use another PON (add a splitter in NetBox and cable it). |
| UI shows nodes but expanding does nothing | The lens hides the edges you want. Switch to **All**. |
| `401`/`403` from NetBox in graph-api logs | The token in `.env` doesn't match the one NetBox created on first start (the superuser is only created once). Fix `.env`, or `docker compose down -v`. |
