import { Box, Chip, Divider, LinearProgress, Stack, Tooltip, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { EDGE_STYLE, GLYPHS, KIND_COLORS } from '../graph/style'

const LEGEND: { key: string; label: string; glyph: string }[] = [
  { key: 'region', label: 'Region', glyph: 'region' },
  { key: 'site', label: 'Site', glyph: 'site' },
  { key: 'location', label: 'Location', glyph: 'location' },
  { key: 'device:olt', label: 'OLT', glyph: 'olt' },
  { key: 'device:splitter', label: 'Splitter', glyph: 'splitter' },
  { key: 'device:ont', label: 'ONT', glyph: 'ont' },
  { key: 'device:bng', label: 'BNG', glyph: 'bng' },
  { key: 'interface:pon', label: 'PON port', glyph: 'pon' },
  { key: 'interface:ethernet', label: 'Ethernet', glyph: 'ethernet' },
  { key: 'interface:voip', label: 'VOIP', glyph: 'voip' },
  { key: 'interface:wan', label: 'WAN', glyph: 'wan' },
  { key: 'interface:uplink', label: 'Uplink', glyph: 'uplink' },
  { key: 'virtualcircuit', label: 'Service (VC)', glyph: 'virtualcircuit' },
  { key: 'ipaddress', label: 'IP address', glyph: 'ipaddress' },
  { key: 'prefix', label: 'Prefix', glyph: 'prefix' },
  { key: 'vlan', label: 'VLAN', glyph: 'vlan' },
  { key: 'number', label: 'Phone number', glyph: 'number' },
  { key: 'circuit', label: 'Circuit', glyph: 'circuit' },
  { key: 'tenant', label: 'Subscriber', glyph: 'tenant' },
]

export default function LeftPanel() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 30_000 })
  const h = health.data
  return (
    <Box sx={{ p: 2, overflow: 'auto', height: '100%' }}>
      <Typography variant="overline" color="text.secondary">Stack</Typography>
      {health.isLoading && <LinearProgress />}
      {h && (
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.6, mb: 1 }}>
          <Chip size="small" color="primary" label={`PostgreSQL ${h.postgres}`} />
          <Chip size="small" color="secondary" label={`NetBox ${h.netbox}`} />
          <Chip size="small" color={h.graph_schema === 'ready' ? 'success' : 'warning'} label={`graph ${h.graph_schema}`} />
        </Stack>
      )}
      {stats.data && (
        <Typography variant="caption" color="text.secondary">
          {Object.values(stats.data.vertices).reduce((a, b) => a + b, 0)} vertices ·{' '}
          {Object.values(stats.data.edges).reduce((a, b) => a + b, 0)} edges, computed live from NetBox tables
        </Typography>
      )}
      <Divider sx={{ my: 1.5 }} />
      <Typography variant="overline" color="text.secondary">Vertices</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.8, mt: 0.5 }}>
        {LEGEND.map((l) => (
          <Box key={l.key} sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
            <Box sx={{ width: 20, height: 20, borderRadius: '6px', bgcolor: KIND_COLORS[l.key], flexShrink: 0,
              backgroundImage: `url("${GLYPHS[l.glyph]}")`, backgroundSize: '70%', backgroundRepeat: 'no-repeat', backgroundPosition: 'center' }} />
            <Typography variant="caption" noWrap>{l.label}</Typography>
          </Box>
        ))}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        Green ring = provisioned/assigned · faded = available/free · dashed = disabled · "▸ n" = unexpanded links
      </Typography>
      <Divider sx={{ my: 1.5 }} />
      <Typography variant="overline" color="text.secondary">Edges</Typography>
      <Stack spacing={0.4} sx={{ mt: 0.5 }}>
        {Object.entries(EDGE_STYLE).map(([label, s]) => (
          <Tooltip key={label} title={label} placement="right">
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box sx={{ width: 34, borderTop: `${Math.max(s.width, 1.5)}px ${s.style} ${s.color}` }} />
              <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: 10.5 }}>{label}</Typography>
              {stats.data?.edges[label] !== undefined && (
                <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>{stats.data.edges[label]}</Typography>
              )}
            </Box>
          </Tooltip>
        ))}
      </Stack>
      <Divider sx={{ my: 1.5 }} />
      <Typography variant="overline" color="text.secondary">How to</Typography>
      <Typography variant="caption" component="div" color="text.secondary" sx={{ lineHeight: 1.7 }}>
        • <b>Double-click</b> a node to expand or collapse it<br />
        • <b>Right-click</b> for actions: provision, add, edit, delete, trace<br />
        • <b>Click</b> a node to open the inspector<br />
        • Lenses: <b>Service</b> (hierarchy + services), <b>Physical</b> (cables, splitters, circuits), <b>Inventory</b> (IPs, VLANs, numbers)
      </Typography>
    </Box>
  )
}
