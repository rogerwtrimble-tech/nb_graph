import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Box, Breadcrumbs, Button, Chip, CircularProgress, Divider, IconButton, Link, List, ListItemButton,
  ListItemText, Stack, Tab, Tabs, TextField, Tooltip, Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import DeleteIcon from '@mui/icons-material/Delete'
import AddIcon from '@mui/icons-material/AddCircleOutlineOutlined'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSnackbar } from 'notistack'
import { api, ApiError, type CreateRule, type GNode } from '../api'
import { KIND_COLORS, glyphFor, styleKey } from '../graph/style'
import ObjectForm from './ObjectForm'
import ProvisionPanel from './ProvisionPanel'

const HIDE = new Set(['url', 'display_url', 'custom_fields', 'tags', 'created', 'last_updated', 'id', 'display',
  'comments', 'owner', '_occupied', 'link_peers', 'connected_endpoints', 'link_peers_type', 'connected_endpoints_type',
  'connected_endpoints_reachable', 'wireless_link', 'wireless_lans', 'l2vpn_termination', 'local_context_data',
  'config_context', 'vdcs', 'tagged_vlans', 'mac_addresses', 'primary_mac_address', 'module', 'vrf'])

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (Array.isArray(v)) return v.length ? v.map(fmt).join(', ') : '—'
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>
    return String(o.label ?? o.display ?? o.name ?? o.value ?? JSON.stringify(o))
  }
  return String(v)
}

export default function Inspector({ node, netboxUrl, rootId, onClose, onChanged, onDeleted, onShowPath, onAddedChild }: {
  node: GNode
  netboxUrl: string
  rootId: string | null
  onClose: () => void
  onChanged: (ids: string[]) => void
  onDeleted: (id: string) => void
  onShowPath: (ids: string[]) => void
  onAddedChild: (parentId: string) => void
}) {
  const qc = useQueryClient()
  const { enqueueSnackbar } = useSnackbar()
  const isOntPort = node.kind === 'interface' && node.props.device_role === 'ont'
  const isPon = node.kind === 'interface' && node.props.service_class === 'pon' && node.props.device_role === 'olt'
  const tabs = ['overview', 'edit', ...(isOntPort ? ['services'] : []), 'add', 'raw']
  const [tab, setTab] = useState(isOntPort ? 'services' : 'overview')
  const [rule, setRule] = useState<CreateRule | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [ontSerial, setOntSerial] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setTab(isOntPort ? 'services' : 'overview')
    setRule(null)
    setConfirm(false)
  }, [node.id])

  const obj = useQuery({ queryKey: ['object', node.kind, node.nb_id], queryFn: () => api.object(node.kind, node.nb_id) })
  const schema = useQuery({ queryKey: ['schema', node.kind], queryFn: () => api.schema(node.kind), staleTime: 300_000 })
  const crumbs = useQuery({
    queryKey: ['crumbs', node.id, rootId],
    queryFn: () => api.path(node.id, rootId!, { lens: 'service', labels: 'CONTAINS,HOSTS,HAS_INTERFACE,HAS_SUBINTERFACE,FEEDS' }),
    enabled: Boolean(rootId) && rootId !== node.id,
    retry: false,
  })

  const color = KIND_COLORS[styleKey(node)] ?? '#607d8b'
  const prefill = (r: CreateRule) => {
    const out: Record<string, unknown> = {}
    Object.entries(r.prefill).forEach(([k, v]) => {
      if (v === '$id') out[k] = node.nb_id
      else if (typeof v === 'string' && v.startsWith('$props.')) out[k] = node.props[v.slice(7)]
      else out[k] = v
    })
    return out
  }

  const rows = useMemo(() => {
    if (!obj.data) return []
    return Object.entries(obj.data).filter(([k, v]) => !HIDE.has(k) && v !== null && v !== '' && !(Array.isArray(v) && !v.length))
  }, [obj.data])

  const doDelete = async () => {
    setBusy(true)
    try {
      await api.remove(node.kind, node.nb_id)
      enqueueSnackbar(`Deleted ${node.label}`, { variant: 'info' })
      onDeleted(node.id)
    } catch (e) {
      enqueueSnackbar(e instanceof ApiError ? e.message : String(e), { variant: 'error' })
    } finally {
      setBusy(false)
      setConfirm(false)
    }
  }

  const addOnt = async () => {
    setBusy(true)
    try {
      const r = await api.addOnt({ pon_interface_id: node.nb_id, serial: ontSerial || undefined })
      enqueueSnackbar(`Created ${r.device.name} on ${r.splitter_port}`, { variant: 'success' })
      onAddedChild(node.id)
    } catch (e) {
      enqueueSnackbar(e instanceof ApiError ? e.message : String(e), { variant: 'error' })
    } finally { setBusy(false) }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ p: 2, pb: 1, display: 'flex', gap: 1.5, alignItems: 'center' }}>
        <Box sx={{ width: 44, height: 44, borderRadius: 2, bgcolor: color, flexShrink: 0,
          backgroundImage: `url("${glyphFor(node)}")`, backgroundSize: '64%', backgroundRepeat: 'no-repeat', backgroundPosition: 'center' }} />
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="h6" noWrap title={node.label} sx={{ lineHeight: 1.2 }}>{node.label}</Typography>
          <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
            <Chip size="small" label={node.kind_title} />
            <Chip size="small" variant="outlined" label={node.subtype} />
            <Chip size="small" variant="outlined" color={node.status === 'provisioned' || node.status === 'assigned' ? 'success' : 'default'} label={node.status} />
          </Stack>
        </Box>
        <Tooltip title="Open in NetBox">
          <IconButton href={`${netboxUrl}/${node.ui_path}`} target="_blank" rel="noreferrer"><OpenInNewIcon /></IconButton>
        </Tooltip>
        <IconButton onClick={onClose}><CloseIcon /></IconButton>
      </Box>

      {crumbs.data?.hops && (
        <Breadcrumbs maxItems={7} sx={{ px: 2, pb: 1, fontSize: 12 }}>
          {[...crumbs.data.hops].reverse().map((h) => {
            const n = crumbs.data!.nodes.find((x) => x.id === h)
            return (
              <Link key={h} component="button" underline="hover" color={h === node.id ? 'text.primary' : 'inherit'}
                sx={{ fontSize: 12 }} onClick={() => onShowPath(crumbs.data!.hops!)}>{n?.label ?? h}</Link>
            )
          })}
        </Breadcrumbs>
      )}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ px: 1, minHeight: 40 }}>
        {tabs.map((t) => <Tab key={t} value={t} label={t} sx={{ minHeight: 40, textTransform: 'capitalize' }} />)}
      </Tabs>
      <Divider />

      <Box sx={{ p: 2, overflow: 'auto', flex: 1 }}>
        {tab === 'overview' && (
          <>
            {obj.isLoading && <CircularProgress size={22} />}
            {obj.error && <Alert severity="error">{String(obj.error)}</Alert>}
            <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: 13,
              '& td': { py: 0.6, borderBottom: '1px solid', borderColor: 'divider', verticalAlign: 'top' },
              '& td:first-of-type': { color: 'text.secondary', width: '38%', pr: 1, textTransform: 'capitalize' } }}>
              <tbody>
                {rows.map(([k, v]) => (
                  <tr key={k}><td>{k.replace(/_/g, ' ')}</td><td style={{ wordBreak: 'break-word' }}>{fmt(v)}</td></tr>
                ))}
              </tbody>
            </Box>
            <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button size="small" variant="outlined" startIcon={<OpenInNewIcon />} href={`${netboxUrl}/${node.ui_path}`} target="_blank">NetBox</Button>
              <Button size="small" variant="outlined" color="error" startIcon={<DeleteIcon />} onClick={() => setConfirm(true)}>Delete</Button>
            </Box>
            {confirm && (
              <Alert severity="warning" sx={{ mt: 2 }} action={
                <Stack direction="row" spacing={1}>
                  <Button color="inherit" size="small" onClick={() => setConfirm(false)}>Cancel</Button>
                  <Button color="error" size="small" variant="contained" disabled={busy} onClick={doDelete}>Delete</Button>
                </Stack>}>
                Delete <b>{node.label}</b> from NetBox? Dependent objects may be deleted or blocked by NetBox.
              </Alert>
            )}
          </>
        )}

        {tab === 'edit' && (
          <ObjectForm kind={node.kind} nbId={node.nb_id} onSaved={() => {
            enqueueSnackbar(`Saved ${node.label}`, { variant: 'success' })
            qc.invalidateQueries({ queryKey: ['object', node.kind, node.nb_id] })
            onChanged([node.id])
          }} />
        )}

        {tab === 'services' && isOntPort && <ProvisionPanel node={node} onChanged={onChanged} />}

        {tab === 'add' && (
          <Stack spacing={2}>
            {isPon && (
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Add ONT on this PON</Typography>
                <Typography variant="caption" color="text.secondary">
                  Creates an ONT in the subscriber location and cables it to the next free splitter output, so NetBox's cable trace
                  links it back to this port.
                </Typography>
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <TextField size="small" label="Serial (optional)" value={ontSerial} onChange={(e) => setOntSerial(e.target.value)} />
                  <Button variant="contained" disabled={busy} onClick={addOnt}>Add ONT</Button>
                </Stack>
                <Divider sx={{ mt: 2 }} />
              </Box>
            )}
            {!rule && (
              <List dense>
                {(schema.data?.create ?? []).map((r) => (
                  <ListItemButton key={r.title} onClick={() => setRule(r)}>
                    <AddIcon fontSize="small" sx={{ mr: 1 }} />
                    <ListItemText primary={r.title} secondary={`new ${r.kind} linked to ${node.label}`} />
                  </ListItemButton>
                ))}
                {schema.data && !schema.data.create.length && !isPon && <Alert severity="info">Nothing to create below a {node.kind_title}.</Alert>}
              </List>
            )}
            {rule && (
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>New {rule.title}</Typography>
                <ObjectForm kind={rule.kind} prefill={prefill(rule)} onCancel={() => setRule(null)} onSaved={(o) => {
                  enqueueSnackbar(`Created ${String(o.display ?? '')}`, { variant: 'success' })
                  setRule(null)
                  onAddedChild(node.id)
                }} />
              </Box>
            )}
          </Stack>
        )}

        {tab === 'raw' && (
          <Box component="pre" sx={{ fontSize: 11, m: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify({ graph: node, netbox: obj.data }, null, 2)}
          </Box>
        )}
      </Box>
    </Box>
  )
}
