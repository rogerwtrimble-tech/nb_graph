"""Thin NetBox REST client used by the CRUD proxy, the provisioning engine and the seeder."""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

import httpx

from .settings import get_settings

log = logging.getLogger('nbgraph.netbox')

# Set per request by the auth middleware in OIDC mode, so NetBox() acts as the signed-in user.
# Sync endpoints run in a thread pool that copies the context, so they see it too.
request_token: ContextVar[str | None] = ContextVar('nbgraph_netbox_token', default=None)


class NetBoxError(Exception):
    def __init__(self, status: int, detail: Any, method: str = '', path: str = ''):
        self.status = status
        self.detail = detail
        super().__init__(f'{method} {path} -> {status}: {detail}')


class NetBox:
    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 30.0):
        s = get_settings()
        self.base = (url or s.netbox_url).rstrip('/')
        token = token or request_token.get() or s.netbox_token
        self.client = httpx.Client(
            base_url=f'{self.base}/api/',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            timeout=timeout,
        )

    # -- low level -----------------------------------------------------------------------------
    def request(self, method: str, path: str, **kw) -> Any:
        path = path.lstrip('/')
        r = self.client.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except ValueError:
                detail = r.text[:500]
            raise NetBoxError(r.status_code, detail, method, path)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def get(self, path: str, **params) -> Any:
        return self.request('GET', path, params=params or None)

    def post(self, path: str, data: Any) -> Any:
        return self.request('POST', path, json=data)

    def patch(self, path: str, data: Any) -> Any:
        return self.request('PATCH', path, json=data)

    def delete(self, path: str) -> None:
        self.request('DELETE', path)

    def options(self, path: str) -> Any:
        return self.request('OPTIONS', path)

    # -- helpers -------------------------------------------------------------------------------
    def list(self, path: str, **params) -> list[dict]:
        params.setdefault('limit', 1000)
        out: list[dict] = []
        data = self.get(path, **params)
        out.extend(data['results'])
        while data.get('next'):
            nxt = data['next']
            rel = nxt.split('/api/', 1)[1]
            data = self.request('GET', rel)
            out.extend(data['results'])
        return out

    def first(self, path: str, **params) -> dict | None:
        params['limit'] = 1
        res = self.get(path, **params)['results']
        return res[0] if res else None

    def get_or_create(self, path: str, lookup: dict, body: dict | None = None) -> dict:
        """Return the first object matching `lookup` (query filters), else POST `body` (defaults to lookup)."""
        found = self.first(path, **lookup)
        if found:
            return found
        return self.post(path, body if body is not None else lookup)

    def status(self) -> dict:
        return self.get('status/')

    def close(self):
        self.client.close()
