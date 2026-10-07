# nb-graph Helm chart

Deploys the same stack as `docker-compose.yml` on Kubernetes: PostgreSQL 19, two Valkeys, NetBox 4.7 (+ worker,
with the `netbox_numbers` plugin), graph-api, the UI and the demo seed job. It also shows up as an app in
**Rancher Apps & Marketplace** (`questions.yaml` drives the install form).

## Rancher Desktop (k3s, dockerd engine)

```bash
docker compose build                      # builds nb_graph/netbox, nb_graph/graph-api, nb_graph/ui
helm install nb-graph charts/nb-graph -n nb-graph --create-namespace
kubectl -n nb-graph logs -f job/nb-graph-seed        # wait for "seed complete"
```

Rancher Desktop's k3s shares Docker's image store when the engine is **dockerd (moby)**, so the locally built
images are used as they are (`pullPolicy: IfNotPresent`). Open http://nb-graph.localhost (UI) and
http://netbox.nb-graph.localhost (NetBox) through Traefik. The admin password is printed by `helm install`.

Or in the Rancher UI: **Apps → Repositories → Create**, pointing at this git repo (branch `main`). Then
**Apps → Charts → nb_graph → Install**.

## Other clusters

Push the three `nb_graph/*` images to a registry and set `image.registry` (for example `ghcr.io/you`). Set
`ingress.uiHost` / `ingress.netboxHost` (+ `ingress.tls`), or `service.type=LoadBalancer`.

## Values worth knowing

| Value | Default | |
|---|---|---|
| `image.registry` | `""` | prefix for every image (nb_graph/* and upstream) |
| `secrets.*` / `secrets.existingSecret` | generated | generated once, kept across upgrades (and on uninstall, `helm.sh/resource-policy: keep`) |
| `ingress.*` | Traefik, `*.localhost` hosts | |
| `seed.enabled` / `seed.demoData` | `true` / `true` | post-install/upgrade hook. `demoData=false` only creates the webhook and OIDC role groups |
| `auth.mode`, `auth.oidc.*` | `none` | per-user OIDC sign-in. See [docs/auth.md](../../docs/auth.md) |
| `netbox.ipv4Only` | `false` | for nodes with IPv6 disabled entirely |
| `*.persistence.*`, `netbox.media.*` | on | PVCs for PostgreSQL, the Valkey task queue and NetBox media |

graph-api runs as a single replica: the live-event hub and bulk jobs live in its process.

## Verification status

`helm lint` is clean, and the rendered manifests (defaults, OIDC + LoadBalancer + registry, no persistence +
TLS) pass `kubectl apply --dry-run=server` against a Kubernetes 1.33 (k3s) API server. A real
`helm install` / `upgrade` confirmed that generated secrets stay stable and pinned values win. The pods have
**not** been run on a cluster yet: the build sandbox can't start pod sandboxes. The containers and their
configuration are the same ones verified under docker compose.
