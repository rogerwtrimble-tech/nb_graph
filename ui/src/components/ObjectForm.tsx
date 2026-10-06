// Schema-driven create/edit form. Field list = nb_graph curation + NetBox OPTIONS metadata.
import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Autocomplete, Box, Button, CircularProgress, FormControlLabel, MenuItem, Stack, Switch, TextField,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError, type FieldSpec } from '../api'

type Ref = { id: number; display: string }
type Values = Record<string, unknown>

function FkPicker({ field, value, onChange, filters }: {
  field: FieldSpec; value: Ref | null; onChange: (v: Ref | null) => void; filters?: Record<string, string | number>
}) {
  const [input, setInput] = useState('')
  const [opts, setOpts] = useState<Ref[]>([])
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let live = true
    setLoading(true)
    const t = setTimeout(() => {
      api.lookup(field.endpoint!, input, filters)
        .then((r) => live && setOpts(r.results.map((x) => ({ id: x.id, display: x.display }))))
        .catch(() => live && setOpts([]))
        .finally(() => live && setLoading(false))
    }, 200)
    return () => { live = false; clearTimeout(t) }
  }, [input, field.endpoint, JSON.stringify(filters)])
  return (
    <Autocomplete
      size="small"
      options={opts}
      value={value}
      loading={loading}
      filterOptions={(x) => x}
      getOptionLabel={(o) => o.display}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, v, reason) => reason === 'input' && setInput(v)}
      onChange={(_, v) => onChange(v)}
      renderInput={(p) => <TextField {...p} label={field.label} required={field.required} helperText={field.help || undefined} />}
    />
  )
}

/** Turn a NetBox REST object into flat form values ({id,display} for FKs, raw value for choices). */
function fromNetBox(obj: Record<string, unknown>, fields: FieldSpec[]): Values {
  const out: Values = {}
  for (const f of fields) {
    const v = obj[f.name]
    if (v === undefined) continue
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const o = v as Record<string, unknown>
      if ('value' in o && 'label' in o) out[f.name] = o.value
      else if ('id' in o) out[f.name] = { id: o.id as number, display: String(o.display ?? o.name ?? o.id) }
      else out[f.name] = v
    } else out[f.name] = v
  }
  return out
}

function toPayload(values: Values, fields: FieldSpec[], dirtyOnly?: Set<string>): Values {
  const body: Values = {}
  for (const f of fields) {
    if (f.read_only) continue
    if (dirtyOnly && !dirtyOnly.has(f.name)) continue
    const v = values[f.name]
    if (v === undefined) continue
    if (f.type === 'fk') body[f.name] = v ? (v as Ref).id : null
    else if (f.type === 'integer') body[f.name] = v === '' || v === null ? null : parseInt(String(v), 10)
    else if (f.type === 'number') body[f.name] = v === '' || v === null ? null : Number(v)
    else if (f.type === 'choice') body[f.name] = v === '' ? null : v
    else body[f.name] = v
  }
  return body
}

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

export default function ObjectForm({ kind, nbId, prefill, onSaved, onCancel }: {
  kind: string
  nbId?: number
  prefill?: Values
  onSaved: (obj: Record<string, unknown>) => void
  onCancel?: () => void
}) {
  const schema = useQuery({ queryKey: ['schema', kind], queryFn: () => api.schema(kind), staleTime: 300_000 })
  const existing = useQuery({
    queryKey: ['object', kind, nbId], queryFn: () => api.object(kind, nbId!), enabled: nbId !== undefined,
  })
  const [values, setValues] = useState<Values>({})
  const [dirty, setDirty] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const fields = useMemo(() => schema.data?.fields ?? [], [schema.data])

  useEffect(() => {
    if (!fields.length) return
    if (nbId !== undefined && existing.data) setValues(fromNetBox(existing.data, fields))
    if (nbId === undefined) setValues({ ...(prefill ?? {}) })
  }, [fields, existing.data, nbId, JSON.stringify(prefill)])

  // prefilled FK ids arrive as numbers - resolve them to {id, display} for the pickers
  useEffect(() => {
    if (nbId !== undefined || !prefill) return
    fields.filter((f) => f.type === 'fk' && typeof prefill[f.name] === 'number').forEach((f) => {
      api.lookup(f.endpoint!, '', { id: prefill[f.name] as number }).then((r) => {
        const hit = r.results[0]
        if (hit) setValues((v) => ({ ...v, [f.name]: { id: hit.id, display: hit.display } }))
      })
    })
  }, [fields, JSON.stringify(prefill), nbId])

  const set = (name: string, v: unknown) => {
    setValues((prev) => {
      const next = { ...prev, [name]: v }
      const slugField = fields.find((f) => f.slug_from === name)
      if (slugField && nbId === undefined && !dirty.has(slugField.name)) next[slugField.name] = slugify(String(v ?? ''))
      return next
    })
    setDirty((d) => new Set(d).add(name))
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const obj = nbId === undefined
        ? await api.create(kind, { ...toPayload(values, fields) })
        : await api.update(kind, nbId, toPayload(values, fields, dirty))
      onSaved(obj)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  if (schema.isLoading || (nbId !== undefined && existing.isLoading)) return <CircularProgress size={24} sx={{ m: 2 }} />
  if (schema.error) return <Alert severity="error">{String(schema.error)}</Alert>

  return (
    <Stack spacing={1.6} sx={{ pt: 1 }}>
      {fields.map((f) => {
        const v = values[f.name]
        if (f.type === 'fk') {
          const filters: Record<string, string | number> = {}
          if (f.name === 'interface' && values.device) filters.device_id = (values.device as Ref).id
          if (f.name === 'location' && values.site) filters.site_id = (values.site as Ref).id
          return <FkPicker key={f.name} field={f} value={(v as Ref) ?? null} onChange={(x) => set(f.name, x)} filters={filters} />
        }
        if (f.type === 'boolean')
          return (
            <FormControlLabel key={f.name} label={f.label}
              control={<Switch checked={Boolean(v)} onChange={(e) => set(f.name, e.target.checked)} />} />
          )
        if (f.type === 'choice')
          return (
            <TextField key={f.name} select size="small" label={f.label} required={f.required}
              value={(v as string) ?? ''} onChange={(e) => set(f.name, e.target.value)}>
              <MenuItem value=""><em>—</em></MenuItem>
              {f.choices?.map((c) => <MenuItem key={String(c.value)} value={c.value}>{c.label}</MenuItem>)}
            </TextField>
          )
        return (
          <TextField key={f.name} size="small" label={f.label} required={f.required}
            type={f.type === 'integer' || f.type === 'number' ? 'number' : 'text'}
            value={(v as string | number | null) ?? ''} helperText={f.help || undefined}
            multiline={f.name === 'description'} maxRows={4}
            onChange={(e) => set(f.name, e.target.value)} />
        )
      })}
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
      <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
        <Button variant="contained" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : nbId === undefined ? 'Create in NetBox' : 'Save to NetBox'}
        </Button>
      </Box>
    </Stack>
  )
}
