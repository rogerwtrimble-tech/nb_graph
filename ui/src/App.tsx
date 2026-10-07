import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AppBar, Box, Chip, CssBaseline, Drawer, IconButton, MenuItem, TextField, ThemeProvider, ToggleButton,
  ToggleButtonGroup, Toolbar, Tooltip, Typography, createTheme, useMediaQuery,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import FitScreenIcon from '@mui/icons-material/FitScreen'
import RefreshIcon from '@mui/icons-material/Refresh'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import ImageIcon from '@mui/icons-material/Image'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import PublicIcon from '@mui/icons-material/Public'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSnackbar } from 'notistack'
import { api, ApiError, type GNode, type Lens, type MapSite } from './api'
import { GraphController, type LayoutName } from './graph/controller'
import Inspector from './components/Inspector'
import LeftPanel from './components/LeftPanel'
import MapView from './components/MapView'
import NodeMenu, { type MenuAction } from './components/NodeMenu'
import SearchBox from './components/SearchBox'
import { useLiveEvents, type ChangeEvent } from './useLiveEvents'

const LEFT = 290
const RIGHT = 430
const CABLE_LABELS = 'HAS_INTERFACE,HAS_PORT,MAPS,CABLED,PART_OF'

export default function App() {
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  const [dark, setDark] = useState<boolean>(prefersDark)
  const theme = useMemo(() => createTheme({
    palette: { mode: dark ? 'dark' : 'light', primary: { main: '#1e88e5' }, secondary: { main: '#d81b60' },
      background: dark ? { default: '#0b1118', paper: '#111a24' } : { default: '#f4f6f9', paper: '#ffffff' } },
    shape: { borderRadius: 10 },
    typography: { fontFamily: 'Inter, Roboto, system-ui, sans-serif' },
  }), [dark])

  const { enqueueSnackbar } = useSnackbar()
  const containerRef = useRef<HTMLDivElement>(null)
  const ctl = useRef<GraphController | null>(null)
  const qc = useQueryClient()
  const [view, setView] = useState<'graph' | 'map'>('graph')
  const [lens, setLens] = useState<Lens>('service')
  const [layout, setLayout] = useState<LayoutName>('dagre')
  const [leftOpen, setLeftOpen] = useState(true)
  const [selected, setSelected] = useState<GNode | null>(null)
  const [menu, setMenu] = useState<{ node: GNode; x: number; y: number } | null>(null)
  const [traceFrom, setTraceFrom] = useState<GNode | null>(null)
  const traceRef = useRef<GNode | null>(null)
  traceRef.current = traceFrom
  const [rootId, setRootId] = useState<string | null>(null)
  const [nodeCount, setNodeCount] = useState(0)
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })
  const netboxUrl = (health.data?.netbox_public_url ?? 'http://localhost:8000').replace(/\/$/, '')

  const fail = useCallback((e: unknown) => enqueueSnackbar(e instanceof ApiError ? e.message : String(e), { variant: 'error' }), [enqueueSnackbar])
  const sync = () => setNodeCount(ctl.current?.cy.nodes().length ?? 0)

  // ---------------------------------------------------------------------------------- cytoscape lifecycle
  useEffect(() => {
    const c = new GraphController(containerRef.current!, dark)
    ctl.current = c
    ;(window as unknown as { nbgraph: GraphController }).nbgraph = c // console / e2e access
    const cy = c.cy
    cy.on('tap', 'node', async (ev) => {
      const n = ev.target.data() as GNode
      const from = traceRef.current
      if (from && from.id !== n.id) {
        setTraceFrom(null)
        try {
          const g = await api.path(from.id, n.id, { lens: 'all' })
          await c.addAndShow(g)
          sync()
          enqueueSnackbar(`Path: ${g.hops?.length ?? 0} hops`, { variant: 'info' })
        } catch (e) { fail(e) }
        return
      }
      setSelected(n)
    })
    cy.on('dbltap', 'node', async (ev) => {
      try { await c.toggle(ev.target.id()); sync() } catch (e) { fail(e) }
    })
    cy.on('cxttap', 'node', (ev) => {
      const oe = ev.originalEvent as MouseEvent
      setMenu({ node: ev.target.data() as GNode, x: oe.clientX, y: oe.clientY })
    })
    cy.on('tap', (ev) => { if (ev.target === cy) { setSelected(null); c.clearHighlight() } })
    cy.on('mouseover', 'edge', (ev) => ev.target.addClass('show-label'))
    cy.on('mouseout', 'edge', (ev) => ev.target.removeClass('show-label'))
    c.loadRoots().then(async () => {
      sync()
      const roots = await api.roots('service')
      setRootId(roots.nodes[0]?.id ?? null)
    }).catch((e) => { if (!cy.destroyed()) fail(e) }) // StrictMode mounts twice in dev
    return () => c.destroy()
  }, [])

  useEffect(() => { ctl.current?.setDark(dark) }, [dark])

  // keep the selected node's data fresh after refreshes
  const refreshSelected = useCallback(() => {
    if (!selected) return
    const n = ctl.current?.node(selected.id)
    if (n) setSelected({ ...n })
  }, [selected])

  // ---------------------------------------------------------------------------------- live updates
  const live = useLiveEvents(async (events: ChangeEvent[]) => {
    if (events.some((e) => e.kind === 'site' || e.kind === 'device' || e.kind === 'circuit')) {
      qc.invalidateQueries({ queryKey: ['map'] })
    }
    const c = ctl.current
    if (!c) return
    const visible = new Set(c.ids())
    const touched = events.filter((e) => visible.has(e.id)).map((e) => e.id)
    try {
      await c.refresh() // degrees and edges for everything on canvas (cheap at demo scale)
      touched.forEach((id) => c.flash(id))
      sync()
      refreshSelected()
    } catch { /* graph-api restarting */ }
    const external = events.filter((e) => e.source === 'netbox')
    if (external.length) {
      const e = external[external.length - 1]
      enqueueSnackbar(`NetBox: ${e.kind} ${e.display ?? e.id} ${e.event}${e.user ? ` by ${e.user}` : ''}`
        + (external.length > 1 ? ` (+${external.length - 1} more)` : ''), { variant: 'default' })
    }
  })

  // ---------------------------------------------------------------------------------- actions
  const onPick = async (n: GNode) => {
    const c = ctl.current!
    try {
      if (!c.has(n.id) && rootId) {
        const g = await api.path(n.id, rootId, { lens: 'service', labels: 'CONTAINS,HOSTS,HAS_INTERFACE,HAS_SUBINTERFACE,FEEDS,ASSIGNED_IP,ASSIGNED_NUMBER,UNTAGGED_VLAN,TERMINATES,HAS_PREFIX,HAS_VLAN_GROUP,HAS_NUMBER,CONTAINS_IP,CARRIES,QINQ_SVLAN,BELONGS_TO,PART_OF,CABLED' })
          .catch(() => ({ nodes: [n], edges: [] }))
        await c.addAndShow(g)
      }
      c.center(n.id)
      setSelected(c.node(n.id) ?? n)
      sync()
    } catch (e) { fail(e) }
  }

  const showSiteInGraph = async (s: MapSite) => {
    setView('graph')
    try { await onPick(await api.node(s.node_id, lens)) } catch (e) { fail(e) }
  }

  const onMenu = async (a: MenuAction) => {
    const n = menu?.node
    const c = ctl.current!
    if (!n) return
    try {
      switch (a) {
        case 'expand': await c.expand(n.id); break
        case 'expand3': await c.expand(n.id, 'out', 3); break
        case 'collapse': c.collapse(n.id); break
        case 'parents': await c.expand(n.id, 'in'); break
        case 'provision': case 'edit': case 'add': setSelected(n); break
        case 'hide': c.hide(n.id); if (selected?.id === n.id) setSelected(null); break
        case 'focus': c.focus(n.id); break
        case 'netbox': window.open(`${netboxUrl}/${n.ui_path}`, '_blank'); break
        case 'trace':
          setTraceFrom(n)
          enqueueSnackbar(`Click the target node to trace a path from ${n.label}`, { variant: 'info' })
          break
        case 'path-root': {
          if (!rootId) break
          const g = await api.path(n.id, rootId, { lens: 'service', labels: 'CONTAINS,HOSTS,HAS_INTERFACE,HAS_SUBINTERFACE,FEEDS' })
          await c.addAndShow(g)
          break
        }
        case 'cable-trace': {
          const bng = (await api.search('bng', 'device')).results.find((r) => r.subtype === 'bng')
          if (!bng) throw new Error('No BNG found')
          const g = await api.path(n.id, bng.id, { labels: CABLE_LABELS })
          await c.addAndShow(g)
          enqueueSnackbar(`Cable trace: ${g.hops?.length} hops through splitter / circuit to ${bng.label}`, { variant: 'info' })
          break
        }
      }
    } catch (e) { fail(e) }
    sync()
  }

  const changeLens = async (l: Lens) => {
    setLens(l)
    const c = ctl.current!
    try { await c.setLens(l); sync() } catch (e) { fail(e) }
  }

  const changeLayout = (l: LayoutName) => {
    setLayout(l)
    const c = ctl.current!
    c.layoutName = l
    c.layout(true)
  }

  const exportPng = () => {
    const a = document.createElement('a')
    a.href = ctl.current!.exportPng(dark)
    a.download = 'nb_graph.png'
    a.click()
  }

  const afterChange = async (ids: string[]) => {
    const c = ctl.current!
    try {
      // re-expand the changed nodes so new children (IPs, VLANs, numbers, VCs, sub-interfaces) appear
      for (const id of ids) if (c.has(id) && c.isExpanded(id)) await c.expand(id)
      await c.refresh()
      sync()
      refreshSelected()
    } catch (e) { fail(e) }
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="fixed" elevation={0} color="default" sx={{ zIndex: (t) => t.zIndex.drawer + 1, borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar variant="dense" sx={{ gap: 1.5 }}>
          <IconButton edge="start" onClick={() => setLeftOpen((o) => !o)}><MenuIcon /></IconButton>
          <Box component="img" src="/favicon.svg" sx={{ width: 26, height: 26 }} />
          <Typography variant="h6" sx={{ fontWeight: 700, letterSpacing: -0.3, mr: 1, display: { xs: 'none', sm: 'block' } }}>
            nb_graph
          </Typography>
          <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)}>
            <ToggleButton value="graph"><Tooltip title="Graph"><AccountTreeIcon fontSize="small" /></Tooltip></ToggleButton>
            <ToggleButton value="map"><Tooltip title="Map (site latitude/longitude)"><PublicIcon fontSize="small" /></Tooltip></ToggleButton>
          </ToggleButtonGroup>
          <SearchBox onPick={(n) => { setView('graph'); onPick(n) }} />
          <ToggleButtonGroup size="small" exclusive value={lens} disabled={view === 'map'} onChange={(_, v) => v && changeLens(v)}>
            <ToggleButton value="service">Service</ToggleButton>
            <ToggleButton value="physical">Physical</ToggleButton>
            <ToggleButton value="inventory">Inventory</ToggleButton>
            <ToggleButton value="all">All</ToggleButton>
          </ToggleButtonGroup>
          <TextField select size="small" value={layout} disabled={view === 'map'} onChange={(e) => changeLayout(e.target.value as LayoutName)} sx={{ width: 150 }}>
            <MenuItem value="dagre">Hierarchy</MenuItem>
            <MenuItem value="fcose">Organic</MenuItem>
            <MenuItem value="breadthfirst">Tree</MenuItem>
            <MenuItem value="concentric">Concentric</MenuItem>
          </TextField>
          <Box sx={{ flex: 1 }} />
          {traceFrom && <Chip color="warning" label={`Pick target for path from ${traceFrom.label}`} onDelete={() => setTraceFrom(null)} />}
          <Chip size="small" variant="outlined" label={`${nodeCount} nodes`} />
          <Tooltip title={live ? 'Live: NetBox changes stream in' : 'Live updates disconnected'}>
            <Chip size="small" color={live ? 'success' : 'default'} label={live ? '● live' : '○ offline'} />
          </Tooltip>
          <Tooltip title="Fit"><IconButton onClick={() => ctl.current?.fit()}><FitScreenIcon /></IconButton></Tooltip>
          <Tooltip title="Re-layout"><IconButton onClick={() => ctl.current?.layout(true)}><RefreshIcon /></IconButton></Tooltip>
          <Tooltip title="Reset to regions"><IconButton onClick={() => { setSelected(null); ctl.current?.loadRoots().then(sync).catch(fail) }}><RestartAltIcon /></IconButton></Tooltip>
          <Tooltip title="Export PNG"><IconButton onClick={exportPng}><ImageIcon /></IconButton></Tooltip>
          <Tooltip title="Toggle theme"><IconButton onClick={() => setDark((d) => !d)}>{dark ? <LightModeIcon /> : <DarkModeIcon />}</IconButton></Tooltip>
          <Tooltip title="Open NetBox"><IconButton href={netboxUrl} target="_blank"><OpenInNewIcon /></IconButton></Tooltip>
        </Toolbar>
      </AppBar>

      <Drawer variant="persistent" open={leftOpen}
        sx={{ width: leftOpen ? LEFT : 0, flexShrink: 0, '& .MuiDrawer-paper': { width: LEFT, top: 49, height: 'calc(100% - 49px)' } }}>
        <LeftPanel />
      </Drawer>

      <Box sx={{ position: 'fixed', top: 49, bottom: 0, left: leftOpen ? LEFT : 0, right: selected ? RIGHT : 0,
        transition: 'left .2s, right .2s', bgcolor: 'background.default' }}>
        <Box ref={containerRef} sx={{ position: 'absolute', inset: 0 }} />
        <MapView dark={dark} visible={view === 'map'} onShowInGraph={showSiteInGraph} />
      </Box>

      <Drawer variant="persistent" anchor="right" open={Boolean(selected)}
        sx={{ '& .MuiDrawer-paper': { width: RIGHT, top: 49, height: 'calc(100% - 49px)' } }}>
        {selected && (
          <Inspector node={selected} netboxUrl={netboxUrl} rootId={rootId}
            onClose={() => setSelected(null)}
            onChanged={afterChange}
            onDeleted={(id) => { ctl.current?.hide(id); setSelected(null); sync() }}
            onShowPath={(ids) => ctl.current?.highlight(ids)}
            onAddedChild={(pid) => afterChange([pid]).then(() => ctl.current?.expand(pid)).then(sync).catch(fail)} />
        )}
      </Drawer>

      <NodeMenu anchor={menu} node={menu?.node ?? null} expanded={Boolean(menu && ctl.current?.isExpanded(menu.node.id))}
        onClose={() => setMenu(null)} onAction={onMenu} />
    </ThemeProvider>
  )
}
