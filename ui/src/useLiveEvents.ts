// Subscribes to /api/events/stream (SSE) and batches change notifications.
import { useEffect, useRef, useState } from 'react'
import { accessToken, onTokenChange } from './auth'

export interface ChangeEvent {
  ts: number
  source: 'netbox' | 'nb_graph'
  event: string
  kind: string
  id: string
  display?: string | null
  user?: string
}

export function useLiveEvents(onBatch: (events: ChangeEvent[]) => void) {
  const [connected, setConnected] = useState(false)
  const cb = useRef(onBatch)
  cb.current = onBatch
  // EventSource can't send headers: the token goes in the URL, so reconnect whenever it is renewed
  const [token, setToken] = useState(accessToken())
  useEffect(() => onTokenChange(() => setToken(accessToken())), [])

  useEffect(() => {
    let buf: ChangeEvent[] = []
    let timer: ReturnType<typeof setTimeout> | null = null
    const es = new EventSource(token ? `/api/events/stream?access_token=${encodeURIComponent(token)}` : '/api/events/stream')
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.addEventListener('change', (msg) => {
      try {
        buf.push(JSON.parse((msg as MessageEvent).data))
      } catch {
        return
      }
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        const batch = buf
        buf = []
        cb.current(batch)
      }, 700)
    })
    return () => {
      es.close()
      if (timer) clearTimeout(timer)
    }
  }, [token])

  return connected
}
