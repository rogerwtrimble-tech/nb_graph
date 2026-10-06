"""
Live change feed.

NetBox event rule -> webhook -> POST /api/events/netbox -> in-memory hub -> SSE /api/events/stream -> UI.
nb_graph's own CRUD and provisioning calls publish to the same hub, so every open graph refreshes
the nodes that changed, whoever made the edit and wherever it was made.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .settings import get_settings

router = APIRouter(prefix='/api/events', tags=['events'])

MODEL_KIND = {
    'telephonenumber': 'number',
}


class Hub:
    def __init__(self):
        self._subs: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self.recent: deque = deque(maxlen=50)

    def bind(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            self._subs.discard(q)

    def publish(self, event: dict):
        """Safe to call from sync endpoints (thread pool) and from async code."""
        event = {'ts': time.time(), **event}
        self.recent.append(event)
        if not self._loop:
            return
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            self._loop.call_soon_threadsafe(self._offer, q, event)

    @staticmethod
    def _offer(q: asyncio.Queue, event: dict):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(event)


hub = Hub()


@router.post('/netbox')
async def netbox_webhook(request: Request, x_nbgraph_secret: str | None = Header(default=None)):
    if x_nbgraph_secret != get_settings().webhook_secret:
        raise HTTPException(403, 'bad webhook secret')
    payload = await request.json()
    object_type = payload.get('object_type') or payload.get('model', '')
    model = object_type.split('.')[-1]
    kind = MODEL_KIND.get(model, model)
    data = payload.get('data') or {}
    hub.publish({'source': 'netbox', 'event': payload.get('event'), 'kind': kind,
                 'id': f'{kind}:{data.get("id")}', 'display': data.get('display'),
                 'user': payload.get('username')})
    return {'ok': True}


@router.get('/recent')
def recent():
    return list(hub.recent)


@router.get('/stream')
async def stream(request: Request):
    q = hub.subscribe()

    async def gen():
        try:
            yield 'retry: 3000\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f'event: change\ndata: {json.dumps(ev)}\n\n'
                except asyncio.TimeoutError:
                    yield ': keep-alive\n\n'
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
