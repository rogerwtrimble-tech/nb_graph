// Visual language for the graph: one colour + glyph per vertex kind / subtype, one stroke per edge label.
import type { StylesheetJson } from 'cytoscape'
import type { GNode } from '../api'

export interface KindStyle {
  color: string
  glyph: string
  shape: string
  size: number
  title: string
}

const svg = (body: string) =>
  `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`,
  )}`
const txt = (t: string, size = 10) =>
  svg(`<text x="12" y="16" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-weight="700" font-size="${size}" fill="#fff" stroke="none">${t}</text>`)

export const GLYPHS: Record<string, string> = {
  region: svg('<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16"/>'),
  site: svg('<path d="M4 20V8l8-4 8 4v12M9 20v-5h6v5M8 10h2M14 10h2"/>'),
  location: svg('<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11z"/><circle cx="12" cy="10" r="2"/>'),
  olt: svg('<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M6 10h2M10 10h2M14 10h2M6 14h12"/>'),
  ont: svg('<rect x="4" y="9" width="16" height="9" rx="2"/><path d="M8 9 6 4M16 9l2-5M8 14h.01M12 14h.01M16 14h.01"/>'),
  splitter: svg('<path d="M3 12h6M9 12l10-7M9 12h10M9 12l10 7"/>'),
  bng: svg('<circle cx="12" cy="12" r="8"/><path d="M8 12h8M13 9l3 3-3 3M11 9 8 12l3 3"/>'),
  device: svg('<rect x="4" y="6" width="16" height="12" rx="2"/><path d="M8 12h8"/>'),
  interface: svg('<rect x="6" y="7" width="12" height="10" rx="1"/><path d="M9 7v3M12 7v3M15 7v3"/>'),
  pon: svg('<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>'),
  wan: svg('<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c3 3 3 13 0 16"/>'),
  voip: svg('<path d="M6 4h3l2 5-2 1a11 11 0 0 0 5 5l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 6a2 2 0 0 1 2-2z"/>'),
  ethernet: svg('<rect x="5" y="6" width="14" height="12" rx="1"/><path d="M9 18v-4h6v4M9 9h.01M12 9h.01M15 9h.01"/>'),
  uplink: svg('<path d="M12 20V4M6 10l6-6 6 6"/>'),
  mgmt: svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>'),
  frontport: svg('<rect x="7" y="7" width="10" height="10"/>'),
  rearport: svg('<rect x="7" y="7" width="10" height="10"/><path d="M7 12h10"/>'),
  ipaddress: txt('IP'),
  prefix: txt('/n'),
  vlan: txt('V'),
  vlangroup: txt('VG', 8),
  number: svg('<path d="M6 4h3l2 5-2 1a11 11 0 0 0 5 5l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 6a2 2 0 0 1 2-2z"/>'),
  virtualcircuit: svg('<path d="M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1"/>'),
  circuit: svg('<path d="M2 12c3-6 5-6 8 0s5 6 8 0 4-4 4-4"/>'),
  circuittermination: svg('<circle cx="12" cy="12" r="4"/><path d="M2 12h6M16 12h6"/>'),
  provider: svg('<path d="M3 20h18M5 20V10l7-5 7 5v10"/>'),
  tenant: svg('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
}

export const KIND_COLORS: Record<string, string> = {
  region: '#5c6bc0', site: '#26a69a', location: '#78909c', tenant: '#3949ab', provider: '#6d4c41',
  'device:olt': '#1e88e5', 'device:ont': '#43a047', 'device:splitter': '#8d6e63', 'device:bng': '#8e24aa',
  device: '#546e7a',
  'interface:pon': '#0288d1', 'interface:wan': '#f4511e', 'interface:voip': '#ab47bc',
  'interface:ethernet': '#2e7d32', 'interface:uplink': '#f9a825', 'interface:mgmt': '#90a4ae', interface: '#607d8b',
  frontport: '#a1887f', rearport: '#8d6e63',
  ipaddress: '#ffb300', prefix: '#ef6c00', vlan: '#7e57c2', vlangroup: '#512da8', number: '#d81b60',
  virtualcircuit: '#00acc1', circuit: '#e64a19', circuittermination: '#ff8a65',
}

export function styleKey(n: Pick<GNode, 'kind' | 'subtype' | 'props'>): string {
  if (n.kind === 'device') return KIND_COLORS[`device:${n.subtype}`] ? `device:${n.subtype}` : 'device'
  if (n.kind === 'interface') {
    const sc = String(n.props?.service_class ?? 'other')
    return KIND_COLORS[`interface:${sc}`] ? `interface:${sc}` : 'interface'
  }
  return n.kind
}

export function glyphFor(n: Pick<GNode, 'kind' | 'subtype' | 'props'>): string {
  if (n.kind === 'device') return GLYPHS[n.subtype] ?? GLYPHS.device
  if (n.kind === 'interface') return GLYPHS[String(n.props?.service_class ?? '')] ?? GLYPHS.interface
  return GLYPHS[n.kind] ?? GLYPHS.device
}

const SIZE: Record<string, number> = {
  region: 64, site: 58, location: 46, device: 50, interface: 34, frontport: 20, rearport: 24,
  ipaddress: 30, prefix: 38, vlan: 30, vlangroup: 36, number: 30, virtualcircuit: 36, circuit: 40,
  circuittermination: 28, provider: 40, tenant: 34,
}
const SHAPE: Record<string, string> = {
  region: 'round-hexagon', site: 'round-rectangle', location: 'round-tag', device: 'round-rectangle',
  interface: 'ellipse', frontport: 'rectangle', rearport: 'rectangle', ipaddress: 'round-octagon',
  prefix: 'round-octagon', vlan: 'round-diamond', vlangroup: 'round-diamond', number: 'ellipse',
  virtualcircuit: 'round-diamond', circuit: 'round-pentagon', circuittermination: 'ellipse',
  provider: 'round-rectangle', tenant: 'ellipse',
}

export function toElementData(n: GNode, expanded: boolean) {
  const key = styleKey(n)
  const pending = !expanded && (n.degree ?? 0) > 0
  return {
    ...n,
    display: pending ? `${n.label}\n▸ ${n.degree}` : n.label,
    color: KIND_COLORS[key] ?? '#607d8b',
    glyph: glyphFor(n),
    size: n.kind === 'device' && n.subtype === 'ont' ? 42 : SIZE[n.kind] ?? 34,
    shape: SHAPE[n.kind] ?? 'ellipse',
    expanded,
  }
}

export const EDGE_STYLE: Record<string, { color: string; style: string; width: number; arrow: boolean }> = {
  CONTAINS: { color: '#9fa8da', style: 'solid', width: 1.5, arrow: false },
  HOSTS: { color: '#80cbc4', style: 'solid', width: 1.5, arrow: false },
  HAS_INTERFACE: { color: '#b0bec5', style: 'solid', width: 1.2, arrow: false },
  HAS_SUBINTERFACE: { color: '#b0bec5', style: 'dashed', width: 1.2, arrow: false },
  HAS_PORT: { color: '#bcaaa4', style: 'solid', width: 1, arrow: false },
  MAPS: { color: '#bcaaa4', style: 'dotted', width: 1, arrow: false },
  CABLED: { color: '#ffa726', style: 'solid', width: 3, arrow: false },
  FEEDS: { color: '#29b6f6', style: 'dashed', width: 2.5, arrow: true },
  ASSIGNED_IP: { color: '#ffca28', style: 'solid', width: 1.8, arrow: true },
  UNTAGGED_VLAN: { color: '#9575cd', style: 'solid', width: 1.8, arrow: true },
  TAGGED_VLAN: { color: '#9575cd', style: 'dashed', width: 1.5, arrow: true },
  QINQ_SVLAN: { color: '#673ab7', style: 'dashed', width: 2, arrow: true },
  CARRIES: { color: '#673ab7', style: 'dotted', width: 1.5, arrow: true },
  ASSIGNED_NUMBER: { color: '#ec407a', style: 'solid', width: 1.8, arrow: true },
  TERMINATES: { color: '#26c6da', style: 'solid', width: 2.5, arrow: true },
  HAS_PREFIX: { color: '#ffb74d', style: 'dotted', width: 1.2, arrow: false },
  HAS_VLAN_GROUP: { color: '#9575cd', style: 'dotted', width: 1.2, arrow: false },
  HAS_NUMBER: { color: '#f48fb1', style: 'dotted', width: 1, arrow: false },
  CONTAINS_IP: { color: '#ffe082', style: 'dotted', width: 1, arrow: false },
  PART_OF: { color: '#ff8a65', style: 'solid', width: 1.5, arrow: false },
  PROVIDED_BY: { color: '#a1887f', style: 'dotted', width: 1, arrow: false },
  BELONGS_TO: { color: '#7986cb', style: 'dotted', width: 1, arrow: true },
}

export function stylesheet(dark: boolean): StylesheetJson {
  const fg = dark ? '#e3e8ef' : '#1f2933'
  const bgLabel = dark ? '#0d1520' : '#ffffff'
  const edges = Object.entries(EDGE_STYLE).map(([label, s]) => ({
    selector: `edge[label = "${label}"]`,
    style: {
      'line-color': s.color,
      'target-arrow-color': s.color,
      'line-style': s.style as 'solid',
      width: s.width,
      'target-arrow-shape': (s.arrow ? 'triangle' : 'none') as 'triangle',
    },
  }))
  return [
    {
      selector: 'node',
      style: {
        shape: 'data(shape)' as never,
        'background-color': 'data(color)',
        'background-image': 'data(glyph)',
        'background-fit': 'contain',
        'background-clip': 'none',
        'background-width': '62%',
        'background-height': '62%',
        width: 'data(size)',
        height: 'data(size)',
        label: 'data(display)',
        'text-wrap': 'wrap',
        'text-max-width': '140px',
        'text-valign': 'bottom',
        'text-margin-y': 5,
        'font-size': 11,
        'font-family': 'Inter, Roboto, Arial, sans-serif',
        color: fg,
        'text-background-color': bgLabel,
        'text-background-opacity': 0.75,
        'text-background-padding': '2px',
        'text-background-shape': 'roundrectangle',
        'border-width': 2,
        'border-color': dark ? '#0b1118' : '#ffffff',
        'transition-property': 'background-color, border-color, border-width, opacity',
        'transition-duration': 250,
      },
    },
    { selector: 'node[kind = "frontport"], node[kind = "rearport"]', style: { 'font-size': 9 } },
    { selector: 'node[status = "provisioned"]', style: { 'border-color': '#00e676', 'border-width': 4 } },
    { selector: 'node[status = "assigned"]', style: { 'border-color': '#00e676', 'border-width': 3 } },
    { selector: 'node[status = "available"], node[status = "free"]', style: { 'background-opacity': 0.55 } },
    {
      selector: 'node[status = "disabled"], node[status = "offline"], node[status = "decommissioning"], node[status = "deprecated"]',
      style: { opacity: 0.55, 'border-style': 'dashed', 'border-color': '#9e9e9e' },
    },
    { selector: 'node[status = "planned"], node[status = "reserved"]', style: { 'border-style': 'dotted', 'border-color': '#ffd54f', 'border-width': 3 } },
    { selector: 'node:selected', style: { 'border-color': '#ffeb3b', 'border-width': 5, 'overlay-opacity': 0 } },
    { selector: 'node.path, edge.path', style: { 'underlay-color': '#ffeb3b', 'underlay-opacity': 0.45, 'underlay-padding': 6 } },
    { selector: 'node.flash', style: { 'underlay-color': '#00e5ff', 'underlay-opacity': 0.7, 'underlay-padding': 10 } },
    { selector: 'node.dim, edge.dim', style: { opacity: 0.15 } },
    {
      selector: 'edge',
      style: {
        'curve-style': 'bezier',
        width: 1.5,
        'line-color': '#90a4ae',
        'arrow-scale': 0.9,
        label: '',
        'font-size': 9,
        color: fg,
        'text-rotation': 'autorotate',
        'text-background-color': bgLabel,
        'text-background-opacity': 0.8,
      },
    },
    ...edges,
    { selector: 'edge.show-label, edge:selected', style: { label: 'data(label)' } },
    { selector: 'edge:selected', style: { width: 4, 'line-color': '#ffeb3b', 'target-arrow-color': '#ffeb3b' } },
  ] as StylesheetJson
}
