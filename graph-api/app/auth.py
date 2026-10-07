"""
Per-user authentication (AUTH_MODE=oidc).

  1. The UI signs the user in with the IdP (authorization code + PKCE) and sends the access token on every
     /api call (Authorization: Bearer ..., or ?access_token= for the SSE stream, which can't set headers).
  2. verify() checks the JWT against the IdP's JWKS: signature, expiry, issuer, audience.
  3. netbox_token_for() makes sure a matching NetBox user exists, mirrors the user's IdP groups onto NetBox
     groups of the same name, and mints a short-lived NetBox API token for that user (cached until it nears
     expiry). The request then runs with that token in netbox.request_token, so every NetBox write is made as
     the user: NetBox's object permissions apply, and its change log and webhooks name the real user.

With AUTH_MODE=none none of this runs and the service token is used, as before.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx
import jwt

from .netbox import NetBox, NetBoxError
from .settings import get_settings

log = logging.getLogger('nbgraph.auth')

TOKEN_DESCRIPTION = 'nb_graph session (minted by graph-api)'
RENEW_BEFORE = 300  # seconds


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


@dataclass
class User:
    username: str
    email: str = ''
    name: str = ''
    groups: list[str] = field(default_factory=list)
    claims: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {'username': self.username, 'email': self.email, 'name': self.name, 'groups': self.groups}


def enabled() -> bool:
    return get_settings().auth_mode.lower() == 'oidc'


def public_config() -> dict:
    s = get_settings()
    if not enabled():
        return {'mode': 'none'}
    return {'mode': 'oidc', 'issuer': s.oidc_issuer.rstrip('/'), 'client_id': s.oidc_client_id}


def _internal(url: str) -> str:
    """Rewrite a public IdP URL to the one this container can reach (e.g. localhost:8180 -> keycloak:8080)."""
    s = get_settings()
    pub, internal = s.oidc_issuer.rstrip('/'), s.oidc_internal_url.rstrip('/')
    return internal + url[len(pub):] if internal and url.startswith(pub) else url


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    s = get_settings()
    base = (s.oidc_internal_url or s.oidc_issuer).rstrip('/')
    doc = httpx.get(f'{base}/.well-known/openid-configuration', timeout=10).raise_for_status().json()
    return jwt.PyJWKClient(_internal(doc['jwks_uri']), cache_keys=True, lifespan=3600)


def verify(token: str, jwks: jwt.PyJWKClient | None = None) -> User:
    s = get_settings()
    try:
        key = (jwks or _jwks_client()).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'PS256'],
                            audience=s.oidc_audience or s.oidc_client_id, issuer=s.oidc_issuer.rstrip('/'),
                            options={'require': ['exp', 'iss', 'sub']}, leeway=30)
    except jwt.PyJWTError as exc:
        raise AuthError(f'invalid access token: {exc}') from exc
    except httpx.HTTPError as exc:
        raise AuthError(f'identity provider unreachable: {exc}', 503) from exc
    groups = [g.lstrip('/') for g in claims.get(s.oidc_groups_claim) or [] if isinstance(g, str)]
    allowed = {g.strip() for g in s.oidc_groups.split(',') if g.strip()}
    if allowed and not allowed & set(groups):
        raise AuthError(f'user is not in any of the groups {sorted(allowed)}', 403)
    username = claims.get('preferred_username') or claims.get('email') or claims['sub']
    name = claims.get('name') or ' '.join(filter(None, [claims.get('given_name'), claims.get('family_name')]))
    return User(username=username, email=claims.get('email', ''), name=name, groups=sorted(groups), claims=claims)


# ------------------------------------------------------------------------------- NetBox user + token
_tokens: dict[str, tuple[str, float]] = {}  # username -> (bearer, expires_at)
_lock = threading.Lock()


def _is_superuser(username: str) -> bool:
    """NetBox 4.7's REST API doesn't expose is_superuser, so read it from NetBox's own table."""
    from . import db
    row = db.query_one('SELECT is_superuser FROM public.users_user WHERE username = %s', (username,))
    return bool(row and row['is_superuser'])


def _sync_user(nb: NetBox, user: User) -> dict:
    s = get_settings()
    allowed = {g.strip() for g in s.oidc_groups.split(',') if g.strip()}
    group_ids = []
    for gname in sorted(allowed & set(user.groups)):
        grp = nb.first('users/groups/', name=gname)
        if grp:
            group_ids.append(grp['id'])
        else:
            log.warning('IdP group %s has no NetBox group of the same name: no permissions from it', gname)
    first, _, last = user.name.partition(' ')
    body = {'email': user.email, 'first_name': first[:150], 'last_name': last[:150], 'groups': group_ids,
            'is_active': True}
    existing = nb.first('users/users/', username=user.username)
    if existing:
        # Never let an IdP account take over a privileged local account (e.g. an IdP user called "admin"):
        # the service token could otherwise mint tokens for the NetBox superuser.
        if _is_superuser(user.username):
            raise AuthError(f'NetBox user "{user.username}" is a superuser and cannot be used through OIDC '
                            'sign-in; give the IdP user a different username', 403)
        return nb.patch(f'users/users/{existing["id"]}/', body)
    # The password is never used: this account only signs in through graph-api-minted tokens (or NetBox SSO).
    return nb.post('users/users/', {'username': user.username, 'password': secrets.token_urlsafe(32), **body})


def netbox_token_for(user: User) -> str:
    with _lock:
        hit = _tokens.get(user.username)
        if hit and hit[1] - time.time() > RENEW_BEFORE:
            return hit[0]
    s = get_settings()
    nb = NetBox(token=s.netbox_token)  # service account: needs permission to manage users and grant tokens
    try:
        nb_user = _sync_user(nb, user)
        for old in nb.list('users/tokens/', user_id=nb_user['id']):
            if old.get('description') == TOKEN_DESCRIPTION:  # never touch the user's own tokens
                nb.delete(f'users/tokens/{old["id"]}/')
        expires = datetime.now(timezone.utc) + timedelta(minutes=s.user_token_ttl_minutes)
        tok = nb.post('users/tokens/', {'user': nb_user['id'], 'description': TOKEN_DESCRIPTION,
                                        'expires': expires.isoformat(), 'write_enabled': True})
    except NetBoxError as exc:
        raise AuthError(f'could not provision NetBox access for {user.username}: {exc}', 502) from exc
    finally:
        nb.close()
    bearer = f'nbt_{tok["key"]}.{tok["token"]}' if tok.get('version', 2) == 2 else tok['token']
    with _lock:
        _tokens[user.username] = (bearer, expires.timestamp())
    log.info('minted NetBox token for %s (groups %s)', user.username, ','.join(user.groups) or '-')
    return bearer


# ------------------------------------------------------------------------------- ASGI middleware
PUBLIC_PATHS = {'/api/health', '/api/events/netbox'}  # the webhook has its own shared secret
QUERY_TOKEN_PATHS = {'/api/events/stream'}            # EventSource can't send an Authorization header


class AuthMiddleware:
    """Pure ASGI (keeps SSE streaming intact). Only active when AUTH_MODE=oidc."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        from starlette.concurrency import run_in_threadpool
        from starlette.responses import JSONResponse

        from .netbox import request_token

        path = scope.get('path', '')
        if (scope['type'] != 'http' or not enabled() or not path.startswith('/api/') or path in PUBLIC_PATHS
                or scope.get('method') == 'OPTIONS'):
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get('headers', [])}
        token = headers.get('authorization', '')
        token = token[7:].strip() if token.lower().startswith('bearer ') else ''
        if not token and path in QUERY_TOKEN_PATHS:
            from urllib.parse import parse_qs
            token = (parse_qs(scope.get('query_string', b'').decode()).get('access_token') or [''])[0]
        try:
            if not token:
                raise AuthError('sign in required (missing bearer token)')
            user = await run_in_threadpool(verify, token)
            nb_token = await run_in_threadpool(netbox_token_for, user)
        except AuthError as exc:
            resp = JSONResponse({'detail': str(exc)}, status_code=exc.status,
                                headers={'WWW-Authenticate': 'Bearer'} if exc.status == 401 else None)
            return await resp(scope, receive, send)
        scope.setdefault('state', {})['user'] = user
        ctx = request_token.set(nb_token)
        try:
            await self.app(scope, receive, send)
        finally:
            request_token.reset(ctx)
