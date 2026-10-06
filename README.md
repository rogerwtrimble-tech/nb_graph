# nb_graph (netbox-graph)

A graph view of NetBox, built from NetBox's PostgreSQL database, with a rich UI on top that does full CRUD through the NetBox APIs.

> **Status:** this repository holds the project's decisions and status only. The source code from the original build session (delivered as a zip with git history and `scripts/publish-to-github.sh`) has not been pushed here yet. See [docs/nb_graph-status.md](docs/nb_graph-status.md).

## Architecture

| Component | Tech | Port |
|---|---|---|
| Database | PostgreSQL 19beta4 (needs ICU) | 5432 |
| Source of truth | NetBox 4.7.2 (netbox-docker image v4.7-5.1.1) with the in-repo `netbox_numbers` plugin | 8000 |
| Cache | valkey | – |
| Graph API | FastAPI `graph-api` (OpenAPI at `/docs`) | 8090 |
| UI | React 19, MUI 9 and Cytoscape, served by nginx | 8080 |
| Seed | one-shot data loader | – |

Everything is deployed with **docker compose on Rancher Desktop (dockerd)**. There is no Helm chart yet.

### Graph layer
- A live SQL projection in the `nbgraph` schema: `vertices` and `edges` views, plus BFS `traverse` and `shortest_path` functions.
- SQL/PGQ was reverted from PG19 on 2026-09-07. A PGQ definition (`db/graph/090_pgq_future.sql`) passed checks on PG19beta3 and is waiting for PG20.

### Number inventory
- **Phone numbers (DIDs):** handled by the `netbox_numbers` plugin. phonebox only supports NetBox up to 4.4.
- **IP prefixes and addresses:** native NetBox IPAM.
- **VLANs and service IDs:** S-VLAN/C-VLAN (Q-in-Q) and virtual circuits.

### Features verified in the build session
- Webhook → SSE live updates
- Provisioning saga with rollback
- Add-ONT
- Cable trace through splitter and circuit

## Roadmap
- Per-user auth (OIDC)
- `GRAPH_TABLE` for fixed-depth queries on PG20
- Helm chart for Rancher Apps
- Bulk provisioning
- Map view (site lat/long)
