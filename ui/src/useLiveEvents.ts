// Subscribes to /api/events/stream (SSE) and batches change notifications.
import { useEffect, useRef, useState } from 'react'

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

  useEffect(() => {
    let buf: ChangeEvent[] = []
    let timer: ReturnType<typeof setTimeout> | null = null
    const es = new EventSource('/api/events/stream')
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
  }, [])

  return connected
}
