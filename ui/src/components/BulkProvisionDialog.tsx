// Bulk provisioning: pick a service for every free, eligible ONT port under a region / site / OLT / PON port /
// ONT. The plan is a dry run (read-only SQL). Running it starts a background job on graph-api that
// provisions each port through the normal saga, one at a time. This dialog polls the job for progress.
import { useEffect, useState } from 'react'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, LinearProgress,
  List, ListItem, ListItemIcon, ListItemText, Stack, Switch, ToggleButton, ToggleButtonGroup, Typography,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError, type GNode } from '../api'
import { SERVICE_TEXT } from './ProvisionPanel'

const PREVIEW = 60

/** Node kinds bulk provisioning accepts as a scope (mirrors graph-api bulk._scope_kind). */
export function isBulkScope(n: GNode): boolean {
  if (n.kind === 'region' || n.kind === 'site') return true
  if (n.kind === 'device') return n.subtype === 'olt' || n.subtype === 'ont'
  return n.kind === 'interface' && n.props.device_role === 'olt' && n.props.service_class === 'pon'
}

export default function BulkProvisionDialog({ node, onClose, onFinished }: {
  node: GNode | null
  onClose: () => void
  onFinished: (scopeId: string) => void
}) {
  const [service, setService] = useState('hsi')
  const [stopOnError, setStopOnError] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { setJobId(null); setError(null) }, [node?.id])

  const plan = useQuery({
    queryKey: ['bulk-plan', node?.id, service],
    queryFn: () => api.bulkPlan(node!.id, service),
    enabled: Boolean(node) && !jobId,
  })
  const job = useQuery({
    queryKey: ['bulk-job', jobId],
    queryFn: () => api.bulkJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (q) => (q.state.data?.status === 'running' || !q.state.data ? 1000 : false),
  })
  const running = job.data?.status === 'running'
  const finished = Boolean(job.data && !running)

  useEffect(() => { if (finished && node) onFinished(node.id) }, [finished]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setError(null)
    try {
      const j = await api.bulkStart({ scope: node!.id, service, stop_on_error: stopOnError })
      setJobId(j.id)
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }

  const p = plan.data
  const j = job.data
  return (
    <Dialog open={Boolean(node)} onClose={running ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Bulk provision · {node?.label}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <ToggleButtonGroup size="small" exclusive value={service} disabled={Boolean(jobId)}
            onChange={(_, v) => v && setService(v)}>
            {Object.entries(SERVICE_TEXT).map(([k, v]) => <ToggleButton key={k} value={k}>{v.title}</ToggleButton>)}
          </ToggleButtonGroup>
          <Typography variant="body2" color="text.secondary">{SERVICE_TEXT[service]?.what}</Typography>
          {error && <Alert severity="error">{error}</Alert>}

          {!jobId && plan.isLoading && <LinearProgress />}
          {!jobId && plan.error && <Alert severity="error">{String((plan.error as Error).message)}</Alert>}
          {!jobId && p && (
            <>
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                <Chip label={`${p.onts} ONTs in scope`} />
                <Chip variant="outlined" label={`${p.eligible} eligible ports`} />
                <Chip variant="outlined" color="success" label={`${p.already_provisioned} already provisioned`} />
                <Chip color="warning" label={`${p.targets.length} to provision`} />
              </Stack>
              {p.truncated && <Alert severity="info">Capped at {p.targets.length} ports per job.</Alert>}
              {p.targets.length === 0
                ? <Alert severity="success">Every eligible port in this scope already has a {service.toUpperCase()} service.</Alert>
                : (
                  <List dense disablePadding sx={{ maxHeight: 260, overflow: 'auto', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    {p.targets.slice(0, PREVIEW).map((t) => (
                      <ListItem key={t.interface_id}><ListItemText primary={`${t.device} · ${t.interface}`} secondary={t.site} /></ListItem>
                    ))}
                    {p.targets.length > PREVIEW && <ListItem><ListItemText secondary={`… and ${p.targets.length - PREVIEW} more`} /></ListItem>}
                  </List>
                )}
              <FormControlLabel control={<Switch size="small" checked={stopOnError} onChange={(e) => setStopOnError(e.target.checked)} />}
                label={<Typography variant="body2">Stop at the first failure (each port is rolled back on its own either way)</Typography>} />
            </>
          )}

          {j && (
            <Box>
              <Stack direction="row" sx={{ mb: 0.5, justifyContent: 'space-between' }}>
                <Typography variant="body2">{j.done} / {j.total} · {j.status}</Typography>
                <Typography variant="body2"><b>{j.ok}</b> ok · <b>{j.failed}</b> failed</Typography>
              </Stack>
              <LinearProgress variant="determinate" value={j.total ? (100 * j.done) / j.total : 0}
                color={j.failed ? 'warning' : 'primary'} />
              <List dense disablePadding sx={{ mt: 1, maxHeight: 260, overflow: 'auto' }}>
                {[...j.results].reverse().map((r) => (
                  <ListItem key={r.interface_id} disableGutters>
                    <ListItemIcon sx={{ minWidth: 30 }}>
                      {r.status === 'provisioned' ? <CheckCircleIcon fontSize="small" color="success" /> : <ErrorIcon fontSize="small" color="error" />}
                    </ListItemIcon>
                    <ListItemText primary={`${r.device ?? ''} · ${r.interface ?? r.interface_id}`}
                      secondary={r.cid ?? r.error} />
                  </ListItem>
                ))}
              </List>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        {running && <Button color="warning" onClick={() => api.bulkCancel(jobId!)}>Cancel job</Button>}
        <Button onClick={onClose} disabled={running}>{finished ? 'Close' : 'Cancel'}</Button>
        {!jobId && (
          <Button variant="contained" color="warning" disabled={!p || p.targets.length === 0} onClick={start}>
            Provision {p?.targets.length ?? 0} port{p?.targets.length === 1 ? '' : 's'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  )
}
