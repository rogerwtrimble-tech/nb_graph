# CLAUDE.md

Context for Claude sessions working on this repo. Read this before asking the user anything; they don't want to restate the project.

## Project
nb_graph (Claude Project name: "netbox-graph"): a graph built from NetBox's PostgreSQL database, with a React/Cytoscape UI that does CRUD through the NetBox APIs. The authoritative decisions and status live in `docs/nb_graph-status.md`. Update it whenever a decision or the status changes.

## Fixed decisions (don't re-open without the user)
- PostgreSQL 19beta4 plus a live SQL projection (`nbgraph` schema: vertices/edges views, BFS traverse/shortest_path). There is no SQL/PGQ until PG20; the future definition lives in `db/graph/090_pgq_future.sql`.
- NetBox 4.7.2 (netbox-docker v4.7-5.1.1). DIDs are handled by the in-repo `netbox_numbers` plugin, not phonebox.
- Deployment: Rancher Desktop (dockerd) with docker compose. Helm is a roadmap item only.
- Ports: UI 8080, NetBox 8000, graph-api 8090, PG 5432.

## Working conventions
- Default branch: `main`.
- Tests: pytest (unit plus live integration) for the graph-api and plugin; typecheck and build for the UI; `docker compose config` must validate.
