// GraphController owns the Cytoscape instance plus the expand/collapse bookkeeping.
// React components call into it; it never re-renders React.
import cytoscape, { type Core, type ElementDefinition, type NodeSingular } from 'cytoscape'
import dagre from 'cytoscape-dagre'
import fcose from 'cytoscape-fcose'
import { api, type GEdge, type GNode, type Graph, type Lens } from '../api'
import { stylesheet, toElementData } from './style'

cytoscape.use(dagre)
cytoscape.use(fcose)

export type LayoutName = 'dagre' | 'fcose' | 'concentric' | 'breadthfirst'

export class GraphController {
  cy: Core
  lens: Lens = 'service'
  layoutName: LayoutName = 'dagre'
  /** child id -> ids of the nodes whose expansion revealed it */
  private revealedBy = new Map<string, Set<string>>()
  private expanded = new Set<string>()
  private pinned = new Set<string>()
  private running: cytoscape.Layouts | null = null

  constructor(container: HTMLElement, dark: boolean) {
    this.cy = cytoscape({
      container,
      style: stylesheet(dark),
      minZoom: 0.08,
      maxZoom: 3,
      boxSelectionEnabled: true,
    })
  }

  setDark(dark: boolean) {
    this.cy.style(stylesheet(dark))
  }

  destroy() {
    this.cy.destroy()
  }

  has(id: string) {
    return this.cy.getElementById(id).nonempty()
  }

  node(id: string): GNode | null {
    const n = this.cy.getElementById(id)
    return n.nonempty() ? (n.data() as GNode) : null
  }

  isExpanded(id: string) {
    return this.expanded.has(id)
  }

  ids(): string[] {
    return this.cy.nodes().map((n) => n.id())
  }

  // ------------------------------------------------------------------------------------- merging
  merge(g: Graph, revealer?: string): string[] {
    const added: string[] = []
    if (this.cy.destroyed()) return added
    const origin = revealer ? this.cy.getElementById(revealer) : null
    const base = origin?.nonempty() ? origin.position() : { x: 0, y: 0 }
    const toAdd: ElementDefinition[] = []
    g.nodes.forEach((n, i) => {
      const el = this.cy.getElementById(n.id)
      const data = toElementData(n, this.expanded.has(n.id))
      if (el.nonempty()) {
        el.data(data)
      } else {
        const angle = (i / Math.max(g.nodes.length, 1)) * Math.PI * 2
        toAdd.push({ group: 'nodes', data, position: { x: base.x + Math.cos(angle) * 80, y: base.y + 60 + Math.sin(angle) * 40 } })
        added.push(n.id)
      }
    })
    this.cy.add(toAdd)
    this.mergeEdges(g.edges)
    if (revealer) {
      for (const e of g.edges) {
        const other: string | null = e.source === revealer ? e.target : e.target === revealer ? e.source : null
        if (other && other !== revealer) {
          if (!this.revealedBy.has(other)) this.revealedBy.set(other, new Set())
          // only count nodes that this expansion actually introduced (or that were already children)
          if (added.includes(other) || this.revealedBy.get(other)!.size > 0) this.revealedBy.get(other)!.add(revealer)
        }
      }
    } else {
      added.forEach((id) => this.pinned.add(id))
    }
    return added
  }

  private mergeEdges(edges: GEdge[]) {
    const toAdd: ElementDefinition[] = []
    for (const e of edges) {
      if (this.cy.getElementById(e.id).nonempty()) continue
      if (!this.has(e.source) || !this.has(e.target)) continue
      toAdd.push({ group: 'edges', data: { ...e } })
    }
    this.cy.add(toAdd)
  }

  private markExpanded(id: string, on: boolean) {
    if (on) this.expanded.add(id)
    else this.expanded.delete(id)
    const el = this.cy.getElementById(id)
    if (el.nonempty()) el.data(toElementData(el.data() as GNode, on))
  }

  // ------------------------------------------------------------------------------------- actions
  async loadRoots(autoDepth = 3) {
    this.clear()
    const roots = await api.roots(this.lens)
    this.merge(roots)
    // open the containment tree (Region > Region > Site) so the canvas starts useful
    for (const r of roots.nodes) {
      const g = await api.traverse(r.id, this.lens, autoDepth, 'CONTAINS')
      this.merge(g)
      g.nodes.forEach((n) => {
        if (g.edges.some((e) => e.source === n.id)) this.markExpanded(n.id, true)
      })
      g.edges.forEach((e) => {
        if (!this.revealedBy.has(e.target)) this.revealedBy.set(e.target, new Set())
        this.revealedBy.get(e.target)!.add(e.source)
        this.pinned.delete(e.target)
      })
    }
    await this.refreshDegrees()
    this.layout(true, () => this.fit())
  }

  async expand(id: string, dir: 'out' | 'in' | 'both' = 'out', depth = 1): Promise<number> {
    const g = depth > 1 ? await api.traverse(id, this.lens, depth) : await api.expand(id, this.lens, dir)
    let added: string[]
    if (depth > 1) {
      added = this.merge({ nodes: g.nodes, edges: [] })
      // register revealers level by level from the traversal edges
      for (const e of g.edges) {
        if (!this.revealedBy.has(e.target)) this.revealedBy.set(e.target, new Set())
        if (added.includes(e.target) || this.revealedBy.get(e.target)!.size) this.revealedBy.get(e.target)!.add(e.source)
        this.markExpanded(e.source, true)
      }
      this.mergeEdges(g.edges)
      added.forEach((a) => this.pinned.delete(a))
    } else {
      added = this.merge(g, id)
    }
    if (dir === 'out') this.markExpanded(id, true)
    this.layout(true, () => this.reveal(id))
    return added.length
  }

  /** After a layout: keep the expanded node and its neighbours in view (fit all for small graphs). */
  private reveal(id: string) {
    if (this.cy.destroyed()) return
    if (this.cy.nodes().length < 45) {
      this.cy.animate({ fit: { eles: this.cy.elements(), padding: 40 }, duration: 350 })
      return
    }
    const hood = this.cy.getElementById(id).closedNeighborhood()
    if (hood.empty()) return
    const ext = this.cy.extent()
    const bb = hood.boundingBox({})
    const inside = bb.x1 >= ext.x1 && bb.x2 <= ext.x2 && bb.y1 >= ext.y1 && bb.y2 <= ext.y2
    if (!inside) this.cy.animate({ fit: { eles: hood, padding: 80 }, duration: 400 })
  }

  collapse(id: string) {
    const removeIds = new Set<string>()
    const visit = (nid: string) => {
      for (const [child, parents] of this.revealedBy) {
        if (parents.has(nid)) {
          parents.delete(nid)
          if (parents.size === 0 && !this.pinned.has(child) && !removeIds.has(child)) {
            removeIds.add(child)
            visit(child)
          }
        }
      }
    }
    visit(id)
    removeIds.forEach((c) => {
      this.revealedBy.delete(c)
      this.expanded.delete(c)
    })
    let gone = this.cy.collection()
    removeIds.forEach((r) => { gone = gone.union(this.cy.getElementById(r)) })
    this.cy.remove(gone)
    this.markExpanded(id, false)
    this.layout(true)
    return removeIds.size
  }

  async toggle(id: string) {
    if (this.expanded.has(id)) return -this.collapse(id)
    return this.expand(id)
  }

  hide(id: string) {
    this.revealedBy.delete(id)
    this.pinned.delete(id)
    this.expanded.delete(id)
    this.cy.getElementById(id).remove()
  }

  focus(id: string) {
    const keep = this.cy.getElementById(id).closedNeighborhood()
    this.cy.elements().not(keep).addClass('dim')
    setTimeout(() => this.cy.elements().removeClass('dim'), 4000)
    this.cy.animate({ fit: { eles: keep, padding: 80 }, duration: 400 })
  }

  async addAndShow(g: Graph, highlight = true) {
    this.merge(g)
    g.nodes.forEach((n) => {
      // nodes added by search/path stay until explicitly hidden
      if (!this.revealedBy.get(n.id)?.size) this.pinned.add(n.id)
    })
    this.mergeEdges(g.edges)
    await this.refreshDegrees(g.nodes.map((n) => n.id))
    this.layout(true, () => {
      if (highlight) this.highlight(g.nodes.map((n) => n.id), g.edges.map((e) => e.id))
      else this.fit()
    })
  }

  highlight(nodeIds: string[], edgeIds: string[] = []) {
    this.cy.elements().removeClass('path')
    let els = this.cy.collection()
    ;[...nodeIds, ...edgeIds].forEach((i) => { els = els.union(this.cy.getElementById(i)) })
    els.addClass('path')
    if (els.nonempty()) this.cy.animate({ fit: { eles: els, padding: 90 }, duration: 500 })
  }

  clearHighlight() {
    this.cy.elements().removeClass('path')
  }

  flash(id: string) {
    const el = this.cy.getElementById(id)
    if (el.empty()) return
    el.addClass('flash')
    setTimeout(() => el.removeClass('flash'), 1600)
  }

  center(id: string) {
    const el = this.cy.getElementById(id)
    if (el.empty()) return
    this.cy.$(':selected').unselect()
    el.select()
    this.cy.animate({ center: { eles: el }, zoom: Math.max(this.cy.zoom(), 1), duration: 400 })
  }

  /** Reload the given nodes (or everything) from the API: data, degrees and edges between them. */
  async refresh(ids?: string[]) {
    const target = ids ?? this.ids()
    if (!target.length) return
    const g = await api.subgraph(target, this.lens)
    for (const m of g.missing ?? []) this.hide(m)
    this.merge({ nodes: g.nodes, edges: [] })
    // drop edges among refreshed nodes that no longer exist, then re-add current ones
    const keep = new Set(g.edges.map((e) => e.id))
    const set = new Set(target)
    this.cy.edges().forEach((e) => {
      if (set.has(e.source().id()) && set.has(e.target().id()) && !keep.has(e.id())) e.remove()
    })
    this.mergeEdges(g.edges)
  }

  private async refreshDegrees(ids?: string[]) {
    const target = ids ?? this.ids()
    if (!target.length) return
    const g = await api.subgraph(target, this.lens)
    this.merge({ nodes: g.nodes, edges: [] })
  }

  async setLens(lens: Lens) {
    this.lens = lens
    const all = this.ids()
    this.cy.edges().remove()
    await this.refresh(all)
    this.layout(true)
  }

  clear() {
    this.cy.elements().remove()
    this.revealedBy.clear()
    this.expanded.clear()
    this.pinned.clear()
  }

  fit() {
    this.cy.animate({ fit: { eles: this.cy.elements(), padding: 40 }, duration: 350 })
  }

  layout(animate = true, onDone?: () => void) {
    if (this.cy.destroyed()) return
    this.running?.stop()
    const common = { animate, animationDuration: 450, fit: !onDone && this.cy.nodes().length < 40, padding: 40 }
    let opts: cytoscape.LayoutOptions
    switch (this.layoutName) {
      case 'fcose':
        opts = { name: 'fcose', quality: 'default', randomize: false, nodeRepulsion: 9000, idealEdgeLength: 95,
                 nodeSeparation: 90, packComponents: true, ...common } as unknown as cytoscape.LayoutOptions
        break
      case 'concentric':
        opts = { name: 'concentric', minNodeSpacing: 30, levelWidth: () => 2,
                 concentric: (n: NodeSingular) => 20 - (LEVEL[n.data('kind') as string] ?? 10), ...common } as cytoscape.LayoutOptions
        break
      case 'breadthfirst':
        opts = { name: 'breadthfirst', directed: true, spacingFactor: 1.1, ...common } as cytoscape.LayoutOptions
        break
      default:
        opts = { name: 'dagre', rankDir: 'TB', nodeSep: 45, rankSep: 85, edgeSep: 10, ranker: 'network-simplex',
                 ...common } as unknown as cytoscape.LayoutOptions
    }
    this.running = this.cy.layout(opts)
    if (onDone) this.running.one('layoutstop', () => onDone())
    this.running.run()
  }

  exportPng(dark: boolean): string {
    return this.cy.png({ full: true, scale: 2, bg: dark ? '#0b1118' : '#ffffff' })
  }
}

const LEVEL: Record<string, number> = {
  region: 0, site: 1, location: 2, device: 3, interface: 4, frontport: 5, rearport: 5, vlan: 5,
  ipaddress: 5, number: 5, virtualcircuit: 5, prefix: 4, vlangroup: 4, tenant: 6, circuit: 5,
  circuittermination: 5, provider: 6,
}
