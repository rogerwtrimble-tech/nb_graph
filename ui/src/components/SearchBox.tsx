import { useEffect, useState } from 'react'
import { Autocomplete, Box, InputAdornment, TextField, Typography } from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { api, type GNode } from '../api'
import { KIND_COLORS, styleKey } from '../graph/style'

export default function SearchBox({ onPick }: { onPick: (n: GNode) => void }) {
  const [input, setInput] = useState('')
  const [options, setOptions] = useState<GNode[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (input.trim().length < 2) {
      setOptions([])
      return
    }
    let live = true
    setLoading(true)
    const t = setTimeout(() => {
      api
        .search(input.trim())
        .then((r) => live && setOptions(r.results))
        .catch(() => live && setOptions([]))
        .finally(() => live && setLoading(false))
    }, 220)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [input])

  return (
    <Autocomplete
      size="small"
      sx={{ width: { xs: 220, md: 380 } }}
      options={options}
      loading={loading}
      filterOptions={(x) => x}
      getOptionLabel={(o) => o.label}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      onInputChange={(_, v) => setInput(v)}
      onChange={(_, v) => v && onPick(v)}
      noOptionsText={input.length < 2 ? 'Type 2+ characters' : 'No matches'}
      renderOption={(props, o) => {
        const { key, ...rest } = props as typeof props & { key: string }
        return (
          <Box component="li" key={key} {...rest} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: KIND_COLORS[styleKey(o)] ?? '#999', flexShrink: 0 }} />
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" noWrap>{o.label}</Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {o.kind_title}
                {o.props?.device ? ` · ${o.props.device}` : ''} · {o.subtype}
              </Typography>
            </Box>
          </Box>
        )
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          placeholder="Search sites, devices, IPs, numbers, circuits…"
          slotProps={{
            ...params.slotProps,
            input: {
              ...params.slotProps.input,
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
      )}
    />
  )
}
