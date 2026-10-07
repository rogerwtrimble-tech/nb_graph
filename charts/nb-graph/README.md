# nb-graph Helm chart

Deploys the same stack as `docker-compose.yml` on Kubernetes: PostgreSQL 19, two Valkeys, NetBox 4.7 (+ worker,
with the `netbox_numbers` plugin), graph-api, the UI and the demo seed job. It also shows up as an app in
**Rancher Apps & Marketplace** (`questions.yaml` drives the install form).

## Install (any cluster, including Rancher Desktop)

```bash
helm install nb-graph charts/nb-graph -n nb-graph --create-namespace
kubectl -n nb-graph logs -f job/nb-graph-seed        # wait for "seed complete"
```

The nb_graph images come from GHCR (`ghcr.io/rogerwtrimble-tech/nb_graph/{netbox,graph-api,ui}`), published by
`.github/workflows/images.yml` for amd64 and arm64. `image.tag` picks the build: `main` (default), `sha-<commit>`
or a release such as `0.2.0` (push a `v0.2.0` git tag to publish one). Pin a sha or release for anything you
care about.

With ingress on (default), open http://nb-graph.localhost (UI) and http://netbox.nb-graph.localhost (NetBox).
Elsewhere set `ingress.uiHost` / `ingress.netboxHost` (+ `ingress.tls`), or `service.type=LoadBalancer`. The
admin password is printed by `helm install`.

Rancher UI: **Apps → Repositories → Create**, pointing at this git repo (branch `main`). Then
**Apps → Charts → nb_graph → Install**.

### Locally built images (Rancher Desktop, dockerd engine)

```bash
docker compose build
helm install nb-graph charts/nb-graph -f charts/nb-graph/values-local.yaml -n nb-graph --create-namespace
```

Rancher Desktop's k3s shares Docker's image store when the engine is **dockerd (moby)**, so no registry is needed.

## Values worth knowing

| Value | Default | |
|---|---|---|
| `image.registry` / `image.tag` | `ghcr.io/rogerwtrimble-tech` / `main` | where the nb_graph/* images come from |
| `image.mirror` | `""` | registry prefix for upstream images (postgres, valkey), e.g. a pull-through cache |
| `secrets.*` / `secrets.existingSecret` | generated | generated once, kept across upgrades (and on uninstall, `helm.sh/resource-policy: keep`) |
| `ingress.*` | Traefik, `*.localhost` hosts | |
| `seed.enabled` / `seed.demoData` | `true` / `true` | post-install/upgrade hook. `demoData=false` only creates the webhook and OIDC role groups |
| `auth.mode`, `auth.oidc.*` | `none` | per-user OIDC sign-in. See [docs/auth.md](../../docs/auth.md) |
| `netbox.sso.*` | off | single sign-on to NetBox's own UI through the same IdP |
| `netbox.ipv4Only` | `false` | for nodes with IPv6 disabled entirely |
| `*.persistence.*`, `netbox.media.*` | on | PVCs for PostgreSQL, the Valkey task queue and NetBox media |

graph-api runs as a single replica: the live-event hub and bulk jobs live in its process.

## Verification status

`helm lint` is clean, and the rendered manifests (defaults, OIDC + LoadBalancer + registry, no persistence +
TLS) pass `kubectl apply --dry-run=server` against a Kubernetes 1.33 (k3s) API server. A real
`helm install` / `upgrade` confirmed that generated secrets stay stable and pinned values win. The pods have
**not** been run on a cluster yet: the build sandbox can't start pod sandboxes. The containers and their
configuration are the same ones verified under docker compose.
