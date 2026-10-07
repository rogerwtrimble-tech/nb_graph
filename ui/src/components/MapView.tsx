// Geographic view: sites placed by their NetBox latitude/longitude, sized by device count, joined by the
// site-to-site circuits. Dragging a marker (or placing an unplaced site) writes the new position back to
// NetBox through the CRUD API, so NetBox stays the source of truth.
import { useEffect, useRef, useState } from 'react'
import { Box, Button, Chip, List, ListItem, ListItemText, Paper, Stack, Switch, FormControlLabel, Typography } from '@mui/material'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSnackbar } from 'notistack'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api, ApiError, type MapSite } from '../api'
import { KIND_COLORS } from '../graph/style'

const OSM = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const round6 = (v: number) => Math.round(v * 1e6) / 1e6 // NetBox stores lat/long as decimal(8,6) / (9,6)

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

function markerIcon(site: MapSite) {
  const size = Math.round(18 + Math.min(26, Math.sqrt(site.devices) * 4))
  const color = site.status === 'active' ? KIND_COLORS.site : '#9e9e9e'
  return L.divIcon({
    className: 'nbg-site-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:3px solid #fff;`
      + `box-shadow:0 1px 4px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;`
      + `color:#fff;font:600 11px Inter,Roboto,sans-serif">${site.devices}</div>`,
  })
}

function popupHtml(s: MapSite) {
  const roles = Object.entries(s.roles).sort().map(([r, n]) => `${esc(r)}&nbsp;${n}`).join(' · ') || 'no devices'
  return `<div style="font:13px Inter,Roboto,sans-serif;min-width:180px">
    <div style="font-weight:700;font-size:14px">${esc(s.name)}</div>
    <div style="opacity:.7">${esc(s.region ?? 'no region')}${s.facility ? ` · ${esc(s.facility)}` : ''}</div>
    <div style="margin:6px 0">${roles}<br/>${s.services} active service${s.services === 1 ? '' : 's'}</div>
    <a href="#" data-nbg-show="${esc(s.node_id)}">Show in graph →</a></div>`
}

interface Props {
  dark: boolean
  visible: boolean
  onShowInGraph: (site: MapSite) => void
}

export default function MapView({ dark, visible, onShowInGraph }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const fitted = useRef(false)
  const siteIndex = useRef(new Map<string, MapSite>())
  const [editing, setEditing] = useState(false)
  const [placing, setPlacing] = useState<MapSite | null>(null)
  const placingRef = useRef<MapSite | null>(null)
  placingRef.current = placing
  const showRef = useRef(onShowInGraph)
  showRef.current = onShowInGraph
  const qc = useQueryClient()
  const { enqueueSnackbar } = useSnackbar()
  const data = useQuery({ queryKey: ['map'], queryFn: api.map, enabled: visible })

  const move = async (site: MapSite, ll: L.LatLng) => {
    try {
      await api.update('site', site.id, { latitude: round6(ll.lat), longitude: round6(ll.lng) })
      enqueueSnackbar(`${site.name} moved to ${round6(ll.lat)}, ${round6(ll.lng)}`, { variant: 'success' })
    } catch (e) {
      enqueueSnackbar(e instanceof ApiError ? e.message : String(e), { variant: 'error' })
    }
    qc.invalidateQueries({ queryKey: ['map'] })
  }
  const moveRef = useRef(move)
  moveRef.current = move

  // ---------------------------------------------------------------------------------- leaflet lifecycle
  useEffect(() => {
    const m = L.map(el.current!, { zoomControl: true, worldCopyJump: true }).setView([39.5, -95], 4)
    L.tileLayer(OSM, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(m)
    layer.current = L.layerGroup().addTo(m)
    m.on('click', (ev: L.LeafletMouseEvent) => {
      const site = placingRef.current
      if (!site) return
      setPlacing(null)
      moveRef.current(site, ev.latlng)
    })
    m.on('popupopen', (ev: L.PopupEvent) => {
      ev.popup.getElement()?.querySelector('[data-nbg-show]')?.addEventListener('click', (e) => {
        e.preventDefault()
        const id = (e.currentTarget as HTMLElement).dataset.nbgShow
        const site = siteIndex.current.get(id ?? '')
        if (site) showRef.current(site)
      })
    })
    map.current = m
    return () => { m.remove(); map.current = null }
  }, [])

  // Leaflet measures its container on init; re-measure whenever the view becomes visible.
  useEffect(() => { if (visible) setTimeout(() => map.current?.invalidateSize(), 0) }, [visible])

  // ---------------------------------------------------------------------------------- draw sites + links
  useEffect(() => {
    const m = map.current
    const g = layer.current
    if (!m || !g || !data.data) return
    g.clearLayers()
    const placed = data.data.sites.filter((s) => s.latitude !== null && s.longitude !== null)
    siteIndex.current = new Map(placed.map((s) => [s.node_id, s]))
    const byId = new Map(placed.map((s) => [s.id, s]))
    for (const l of data.data.links) {
      const a = byId.get(l.a_site_id)
      const z = byId.get(l.z_site_id)
      if (!a || !z) continue
      L.polyline([[a.latitude!, a.longitude!], [z.latitude!, z.longitude!]], {
        color: KIND_COLORS.circuit ?? '#f4511e', weight: 3, opacity: l.status === 'active' ? 0.85 : 0.4,
        dashArray: l.status === 'active' ? undefined : '6 6',
      }).bindTooltip(`${l.cid} · ${l.provider} · ${l.status}`, { sticky: true }).addTo(g)
    }
    for (const s of placed) {
      const mk = L.marker([s.latitude!, s.longitude!], { icon: markerIcon(s), draggable: editing, title: s.name })
        .bindPopup(popupHtml(s))
        .bindTooltip(s.name, { direction: 'top', offset: [0, -14] })
      mk.on('dragend', () => moveRef.current(s, mk.getLatLng()))
      mk.addTo(g)
    }
    if (!fitted.current && placed.length) {
      m.fitBounds(L.latLngBounds(placed.map((s) => [s.latitude!, s.longitude!] as [number, number])).pad(0.25))
      fitted.current = true
    }
  }, [data.data, editing])

  const unplaced = data.data?.sites.filter((s) => s.latitude === null || s.longitude === null) ?? []

  return (
    <Box sx={{ position: 'absolute', inset: 0, display: visible ? 'block' : 'none',
      // simple dark tiles: invert + hue-rotate keeps water blue-ish and labels readable
      '& .leaflet-tile-pane': dark ? { filter: 'invert(1) hue-rotate(180deg) brightness(.9) contrast(.9)' } : {},
      '& .leaflet-container': { cursor: placing ? 'crosshair' : undefined, bgcolor: 'background.default' } }}>
      <Box ref={el} sx={{ position: 'absolute', inset: 0 }} />
      <Paper elevation={3} sx={{ position: 'absolute', top: 12, right: 12, zIndex: 1000, p: 1.5, width: 260 }}>
        <Stack spacing={1}>
          <Typography variant="subtitle2">Sites on map</Typography>
          <Stack direction="row" spacing={1}>
            <Chip size="small" label={`${(data.data?.sites.length ?? 0) - unplaced.length} placed`} />
            <Chip size="small" variant="outlined" label={`${data.data?.links.length ?? 0} circuits`} />
          </Stack>
          <FormControlLabel control={<Switch size="small" checked={editing} onChange={(e) => setEditing(e.target.checked)} />}
            label={<Typography variant="body2">Drag to reposition</Typography>} />
          {placing && (
            <Chip color="warning" label={`Click the map to place ${placing.name}`} onDelete={() => setPlacing(null)} />
          )}
          {unplaced.length > 0 && (
            <>
              <Typography variant="caption" color="text.secondary">No latitude/longitude in NetBox:</Typography>
              <List dense disablePadding sx={{ maxHeight: 220, overflow: 'auto' }}>
                {unplaced.map((s) => (
                  <ListItem key={s.id} disableGutters
                    secondaryAction={<Button size="small" onClick={() => setPlacing(s)}>Place</Button>}>
                    <ListItemText primary={s.name} secondary={s.region ?? undefined} />
                  </ListItem>
                ))}
              </List>
            </>
          )}
        </Stack>
      </Paper>
    </Box>
  )
}
