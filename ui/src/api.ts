// Typed client for the nb_graph API (graph-api service). All calls are same-origin: /api/...

export type Lens = 'service' | 'physical' | 'inventory' | 'all'

export interface GNode {
  id: string
  kind: string
  nb_id: number
  label: string
  subtype: string
  status: string
  layer: string
  kind_title: string
  props: Record<string, unknown>
  api_path: string
  ui_path: string
  degree?: number
}

export interface GEdge {
  id: string
  source: string
  target: string
  label: string
  props?: Record<string, unknown> | null
  depth?: number
}

export interface Graph {
  nodes: GNode[]
  edges: GEdge[]
  truncated?: boolean
  hops?: string[]
  missing?: string[]
}

export interface FieldSpec {
  name: string
  label: string
  type: 'string' | 'integer' | 'number' | 'boolean' | 'choice' | 'fk'
  required: boolean
  read_only: boolean
  help?: string
  endpoint?: string
  choices?: { value: string | number; label: string }[]
  slug_from?: string
}

export interface CreateRule {
  kind: string
  title: string
  prefill: Record<string, string | number>
}

export interface Schema {
  kind: string
  api_path: string
  fields: FieldSpec[]
  create: CreateRule[]
}

export interface ServiceInfo {
  interface: { id: number; name: string; type: string; device: string }
  eligible: string[]
  services: {
    interface: { id: number; name: string }
    virtual_circuit: { id: number; cid: string; type: string; status: string; tenant?: string }
    vlan?: { id: number; vid: number; name: string } | null
    ip_addresses: { id: number; address: string }[]
    numbers: { id: number; number: string }[]
  }[]
}

export interface MapSite {
  id: number
  node_id: string
  name: string
  slug: string
  status: string
  facility: string | null
  region_id: number | null
  region: string | null
  latitude: number | null
  longitude: number | null
  devices: number
  roles: Record<string, number>
  services: number
}

export interface MapLink {
  id: number
  cid: string
  status: string
  provider: string
  a_site_id: number
  z_site_id: number
}

export interface SiteMap {
  sites: MapSite[]
  links: MapLink[]
  unplaced: number
}

export interface Health {
  graph_schema: string
  netbox_public_url: string
  postgres: string
  netbox: string
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super(ApiError.describe(body) || `HTTP ${status}`)
    this.status = status
    this.body = body
  }
  static describe(body: unknown): string {
    if (!body || typeof body !== 'object') return String(body ?? '')
    const b = body as Record<string, unknown>
    const nb = b.netbox
    if (nb && typeof nb === 'object') {
      const parts = Object.entries(nb as Record<string, unknown>).map(
        ([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : typeof v === 'object' ? JSON.stringify(v) : v}`,
      )
      return `${b.detail ?? 'NetBox error'} - ${parts.join('; ')}`
    }
    return String(b.detail ?? JSON.stringify(b))
  }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

const q = (params: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && s.set(k, String(v)))
  const str = s.toString()
  return str ? `?${str}` : ''
}

export const api = {
  health: () => call<Health>('GET', '/api/health'),
  meta: () =>
    call<{ kinds: { kind: string; title: string; layer: string }[]; edge_labels: { label: string; description: string; lens: string[] }[]; lenses: Record<string, string[]> }>(
      'GET',
      '/api/graph/meta',
    ),
  roots: (lens: Lens) => call<Graph>('GET', `/api/graph/roots${q({ lens })}`),
  node: (id: string, lens: Lens) => call<GNode>('GET', `/api/graph/node/${id}${q({ lens })}`),
  expand: (id: string, lens: Lens, dir: 'out' | 'in' | 'both' = 'out', labels?: string) =>
    call<Graph>('GET', `/api/graph/expand/${id}${q({ lens, dir, labels })}`),
  traverse: (id: string, lens: Lens, depth: number, labels?: string) =>
    call<Graph>('GET', `/api/graph/traverse/${id}${q({ lens, depth, labels })}`),
  path: (from: string, to: string, opts: { lens?: Lens; labels?: string }) =>
    call<Graph>('GET', `/api/graph/path${q({ from, to, lens: opts.lens ?? 'all', labels: opts.labels })}`),
  subgraph: (ids: string[], lens: Lens) => call<Graph>('GET', `/api/graph/subgraph${q({ ids: ids.join(','), lens })}`),
  search: (text: string, kinds?: string) =>
    call<{ results: GNode[] }>('GET', `/api/graph/search${q({ q: text, kinds, limit: 30 })}`),
  map: () => call<SiteMap>('GET', '/api/graph/map'),
  stats: () => call<{ vertices: Record<string, number>; edges: Record<string, number>; postgres: string }>('GET', '/api/graph/stats'),

  schema: (kind: string) => call<Schema>('GET', `/api/schema/${kind}`),
  object: (kind: string, id: number) => call<Record<string, unknown>>('GET', `/api/object/${kind}/${id}`),
  create: (kind: string, body: Record<string, unknown>) => call<Record<string, unknown>>('POST', `/api/object/${kind}`, body),
  update: (kind: string, id: number, body: Record<string, unknown>) =>
    call<Record<string, unknown>>('PATCH', `/api/object/${kind}/${id}`, body),
  remove: (kind: string, id: number) => call<{ deleted: string }>('DELETE', `/api/object/${kind}/${id}`),
  lookup: (endpoint: string, text: string, extra?: Record<string, string | number>) =>
    call<{ results: { id: number; display: string }[] }>('GET', `/api/nb/${endpoint}${q({ q: text, brief: 1, limit: 25, ...extra })}`),

  services: (interfaceId: number) => call<ServiceInfo>('GET', `/api/provision/interface/${interfaceId}`),
  provision: (body: { interface_id: number; service: string; tenant_id?: number; tenant_name?: string; description?: string }) =>
    call<ProvisionResult>('POST', '/api/provision/service', body),
  deprovision: (interfaceId: number, vcId?: number) =>
    call<ProvisionResult>('DELETE', `/api/provision/service/${interfaceId}${q({ vc_id: vcId })}`),
  addOnt: (body: { pon_interface_id: number; name?: string; serial?: string }) =>
    call<{ status: string; device: { id: number; name: string }; splitter_port: string; steps: Step[] }>('POST', '/api/provision/ont', body),
}

export interface Step {
  action: string
  kind: string
  id?: number
  display?: string | null
}

export interface ProvisionResult {
  status: string
  service?: string
  interface_id: number
  virtual_circuit?: { id: number; cid: string }
  vlan?: { id: number; vid: number }
  ip_address?: { id: number; address: string } | null
  number?: { id: number; number: string } | null
  tenant?: { id: number; name: string }
  steps: Step[]
}
