# nb_graph: build status and decisions (2026-10-06)

## Decisions (agreed with Roger)
- Graph layer: **PG19 plus a live SQL projection** (`nbgraph` schema: vertices/edges views and BFS traverse/shortest_path). SQL/PGQ was reverted from PG19 on 2026-09-07. A PGQ definition (`db/graph/090_pgq_future.sql`) passed checks on PG19beta3 and is waiting for PG20.
- Deployment: **Rancher Desktop (dockerd) + docker compose** (no Helm).
- Number inventory: **phone numbers (DIDs)** via an in-repo plugin `netbox_numbers` (phonebox only supports NetBox up to 4.4), **IP prefixes/addresses**, **VLANs/service IDs** (S-VLAN/C-VLAN Q-in-Q, virtual circuits).
- Repo: `rogerwtrimble-tech/nb_graph`, published on 2026-10-07 (the zip's history merged with the project-context commit). This is now the single source of truth: Claude cloud sessions work from it directly.

## Stack
PostgreSQL 19beta4 · NetBox 4.7.2 (netbox-docker image v4.7-5.1.1 + plugin) · valkey · FastAPI graph-api · React 19/MUI 9/Cytoscape UI (nginx) · one-shot seed.
Ports: UI 8080, NetBox 8000, API 8090 (/docs), PG 5432.

## Verified in the build session
- NetBox 4.7.2: all 813 migrations ran on PG19beta4 (needs ICU). The plugin's UI and REST work.
- 16 pytest tests (unit + live integration), UI typecheck and build, all 9 mermaid diagrams render, `docker compose config` is valid.
- Webhook → SSE live updates, provisioning saga with rollback, add-ONT, and the cable trace through splitter and circuit all work.
- ~~Not verified: the docker images themselves.~~ Verified on 2026-10-07 (see below).

## Verified in the cloud session (2026-10-07)
- `pytest` in `graph-api/`: 8 unit tests pass and 8 integration tests skip without a running stack. Added `graph-api/pytest.ini` (`pythonpath = .`) so a bare `pytest` (as CI runs it) can import `app`.
- UI `npm ci && npm run build` passes. `docker compose config` is valid.

## Docker stack verified (2026-10-07, cloud session)
- All 3 images build from the repo's Dockerfiles (NetBox + plugin + collectstatic, graph-api, ui). Pulled postgres:19beta4-alpine, valkey 9.1, netbox v4.7-5.1.1.
- `docker compose up`: all 8 services healthy. NetBox migrations clean on PG19beta4. Seed completed in about 153s. `/api/health` reports postgres 19beta4, netbox 4.7.2, graph_schema ready. The graph has 830 vertices and 1220 edges.
- `pytest` against the live stack: **16/16 pass** (including the provisioning roundtrip, cable trace and CRUD). The UI loads with no JS errors.
- Sandbox-only workarounds, not repo changes: (1) the build sandbox's TLS proxy CA was injected into image builds; (2) the sandbox kernel has no IPv6, and netbox-docker's `launch-netbox.sh` binds granian to `::`, so it was overridden to `0.0.0.0`. On a host with IPv6 completely disabled, NetBox fails with `Address family not supported by protocol (os error 97)`. Fix: mount a launch script that binds `0.0.0.0`.

## Roadmap progress
- **Map view: done (2026-10-07).** `db/graph/050_map.sql` adds the `nbgraph.site_map` and `nbgraph.site_links` views. `GET /api/graph/map` serves them. The UI uses Leaflet + OSM with drag/place to set site lat/long via NetBox, and popup → "Show in graph". The seed now sets coordinates for the 4 demo sites (and back-fills them on re-seed). Integration test added (17/17 pass on the live stack). E2E check with Playwright: 4 markers, 3 circuits, Place writes to NetBox, Show in graph works. OSM tiles couldn't be checked in the sandbox (egress blocked).

- **Bulk provisioning: done (2026-10-07).** `graph-api/app/bulk.py`: the SQL planner (region/site/OLT/PON/ONT scope → free eligible ports) plus a background job runner that reuses the per-port saga (each port atomic, continue or stop on error, cancel). Endpoints are under `/api/provision/bulk*`. UI: node menu → "Bulk provision…" dialog with dry run, progress and results. 3 integration tests (site/OLT/PON plans agree, bad scope/service rejected, job roundtrip with cleanup): 20/20 pass and can be rerun. Browser E2E: Austin CO VOIP, 10/10 ports provisioned, then cleaned up.

- **Per-user auth (OIDC): done (2026-10-07).** `AUTH_MODE=oidc` (default `none`). `graph-api/app/auth.py`: pure-ASGI middleware, JWT checked against JWKS, then a per-request NetBox token (contextvar) minted per user with the service token. NetBox users are created, and IdP groups are mirrored to NetBox groups, so NetBox permissions and change-log attribution apply. The bundled Keycloak 26.4 runs as `--profile auth` with realm `auth/realm-nbgraph.json` (alice editor, bob viewer, carol none). The seed creates the `nbgraph-editors`/`nbgraph-viewers` groups and permissions. UI: oidc-client-ts PKCE, silent renew, SSE reconnects on renewal, user chip + sign out. Tests: 14 auth unit tests (local RSA key) plus 3 OIDC integration tests. The full suite passes in both modes (oidc 37/37 as alice; none 34 + 3 skipped). Browser E2E: alice/bob sign in and out through Keycloak. Not yet done: NetBox's own UI SSO; read filtering by NetBox permissions. See docs/auth.md.

## Next ideas
GRAPH_TABLE for fixed-depth queries on PG20 (blocked until PG20) · Helm chart for Rancher Apps · NetBox UI SSO with the same IdP.
