// Service provisioning for an ONT interface: shows what is live on the port and runs the
// provisioning saga (tenant -> VLAN -> IP -> DID -> virtual circuit) through the graph API.
import { useState } from 'react'
import {
  Alert, Autocomplete, Box, Button, Card, CardContent, Chip, CircularProgress, Divider, List, ListItem,
  ListItemIcon, ListItemText, MenuItem, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RemoveCircleIcon from '@mui/icons-material/RemoveCircle'
import BoltIcon from '@mui/icons-material/Bolt'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSnackbar } from 'notistack'
import { api, ApiError, type GNode, type ProvisionResult } from '../api'

export const SERVICE_TEXT: Record<string, { title: string; what: string }> = {
  hsi: { title: 'High-Speed Internet', what: 'C-VLAN 100 · IP from Subscriber WAN pool · HSI virtual circuit' },
  voip: { title: 'Voice (VOIP)', what: 'C-VLAN 200 · IP from VOIP pool · next free DID · VOIP virtual circuit' },
  ethernet: { title: 'Business Ethernet', what: 'new sub-interface · per-customer C-VLAN (Q-in-Q under the PON S-VLAN) · EVC' },
}

export default function ProvisionPanel({ node, onChanged }: { node: GNode; onChanged: (ids: string[]) => void }) {
  const qc = useQueryClient()
  const { enqueueSnackbar } = useSnackbar()
  const info = useQuery({ queryKey: ['services', node.nb_id], queryFn: () => api.services(node.nb_id) })
  const [service, setService] = useState<string>('')
  const [tenantMode, setTenantMode] = useState<'auto' | 'existing' | 'new'>('auto')
  const [tenant, setTenant] = useState<{ id: number; display: string } | null>(null)
  const [tenantOpts, setTenantOpts] = useState<{ id: number; display: string }[]>([])
  const [tenantName, setTenantName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ProvisionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (info.isLoading) return <CircularProgress size={22} sx={{ m: 2 }} />
  if (info.error) return <Alert severity="error">{String(info.error)}</Alert>
  const data = info.data!
  const svc = service || data.eligible[0] || ''

  const refresh = (r: ProvisionResult) => {
    qc.invalidateQueries({ queryKey: ['services', node.nb_id] })
    qc.invalidateQueries({ queryKey: ['object'] })
    onChanged([node.id, `interface:${r.interface_id}`, String(node.props.device_id ? `device:${node.props.device_id}` : '')].filter(Boolean))
  }

  const run = async () => {
    setBusy(true); setError(null); setResult(null)
    try {
      const r = await api.provision({
        interface_id: node.nb_id, service: svc, description: description || undefined,
        tenant_id: tenantMode === 'existing' ? tenant?.id : undefined,
        tenant_name: tenantMode === 'new' ? tenantName || undefined : undefined,
      })
      setResult(r)
      enqueueSnackbar(`Provisioned ${r.virtual_circuit?.cid}`, { variant: 'success' })
      refresh(r)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally { setBusy(false) }
  }

  const remove = async (vcId: number, cid: string) => {
    setBusy(true); setError(null)
    try {
      const r = await api.deprovision(node.nb_id, vcId)
      setResult(r)
      enqueueSnackbar(`Removed ${cid}`, { variant: 'info' })
      refresh(r)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally { setBusy(false) }
  }

  const searchTenants = (text: string) =>
    api.lookup('tenancy/tenants/', text).then((r) => setTenantOpts(r.results)).catch(() => setTenantOpts([]))

  return (
    <Stack spacing={2} sx={{ pt: 1 }}>
      <Typography variant="subtitle2" color="text.secondary">
        {data.interface.device} · {data.interface.name} ({data.interface.type})
      </Typography>

      {data.services.length === 0 && <Alert severity="info" variant="outlined">No services on this port yet.</Alert>}
      {data.services.map((s) => (
        <Card key={s.virtual_circuit.id} variant="outlined">
          <CardContent sx={{ pb: '12px !important' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{s.virtual_circuit.cid}</Typography>
              <Chip size="small" color="success" label={s.virtual_circuit.status} />
            </Box>
            <Stack direction="row" spacing={0.6} sx={{ flexWrap: 'wrap', gap: 0.6 }}>
              <Chip size="small" variant="outlined" label={s.virtual_circuit.type} />
              {s.interface.id !== node.nb_id && <Chip size="small" variant="outlined" label={s.interface.name} />}
              {s.vlan && <Chip size="small" variant="outlined" label={`VLAN ${s.vlan.vid}`} />}
              {s.ip_addresses.map((i) => <Chip key={i.id} size="small" variant="outlined" label={i.address} />)}
              {s.numbers.map((n) => <Chip key={n.id} size="small" variant="outlined" color="secondary" label={n.number} />)}
              {s.virtual_circuit.tenant && <Chip size="small" label={s.virtual_circuit.tenant} />}
            </Stack>
            <Box sx={{ textAlign: 'right', mt: 1 }}>
              <Button size="small" color="error" startIcon={<RemoveCircleIcon />} disabled={busy}
                onClick={() => remove(s.virtual_circuit.id, s.virtual_circuit.cid)}>Deprovision</Button>
            </Box>
          </CardContent>
        </Card>
      ))}

      <Divider />
      {data.eligible.length === 0 ? (
        <Alert severity="warning" variant="outlined">
          Only ONT ports can be provisioned: wan* (HSI), voip* (Voice) or eth* (Business Ethernet).
        </Alert>
      ) : (
        <>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Provision a service</Typography>
          <TextField select size="small" label="Service" value={svc} onChange={(e) => setService(e.target.value)}>
            {data.eligible.map((s) => <MenuItem key={s} value={s}>{SERVICE_TEXT[s]?.title ?? s}</MenuItem>)}
          </TextField>
          {svc && <Typography variant="caption" color="text.secondary">{SERVICE_TEXT[svc]?.what}</Typography>}
          <ToggleButtonGroup size="small" exclusive value={tenantMode} onChange={(_, v) => v && setTenantMode(v)}>
            <ToggleButton value="auto">Auto subscriber</ToggleButton>
            <ToggleButton value="existing">Existing tenant</ToggleButton>
            <ToggleButton value="new">New tenant</ToggleButton>
          </ToggleButtonGroup>
          {tenantMode === 'existing' && (
            <Autocomplete size="small" options={tenantOpts} value={tenant} filterOptions={(x) => x}
              getOptionLabel={(o) => o.display} isOptionEqualToValue={(a, b) => a.id === b.id}
              onOpen={() => searchTenants('')} onInputChange={(_, v, r) => r === 'input' && searchTenants(v)}
              onChange={(_, v) => setTenant(v)} renderInput={(p) => <TextField {...p} label="Tenant" />} />
          )}
          {tenantMode === 'new' && (
            <TextField size="small" label="Tenant name" value={tenantName} onChange={(e) => setTenantName(e.target.value)} />
          )}
          <TextField size="small" label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          <Button variant="contained" startIcon={<BoltIcon />} disabled={busy || !svc} onClick={run}>
            {busy ? 'Provisioning…' : 'Provision via NetBox API'}
          </Button>
        </>
      )}

      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
      {result && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="subtitle2" gutterBottom>
              {result.status === 'provisioned' ? 'NetBox changes (rolled back automatically on failure)' : 'Removed'}
            </Typography>
            <List dense disablePadding>
              {result.steps.map((s, i) => (
                <ListItem key={i} disableGutters>
                  <ListItemIcon sx={{ minWidth: 30 }}>
                    <CheckCircleIcon fontSize="small" color={s.action === 'deleted' || s.action === 'released' ? 'warning' : 'success'} />
                  </ListItemIcon>
                  <ListItemText primary={`${s.action} ${s.kind}`} secondary={s.display ?? (s.id ? `#${s.id}` : '')} />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      )}
    </Stack>
  )
}
