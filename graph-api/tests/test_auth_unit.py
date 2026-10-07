"""Unit tests for OIDC auth: JWT validation with a local RSA key and the ASGI middleware. No IdP needed."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth
from app.settings import get_settings

ISS = 'http://idp.test/realms/nbgraph'
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def get_signing_key_from_jwt(self, _token):
        return type('K', (), {'key': KEY.public_key()})()


def token(key=KEY, **over):
    claims = {'iss': ISS, 'aud': 'nb-graph', 'sub': 'u1', 'exp': int(time.time()) + 300,
              'preferred_username': 'alice', 'email': 'alice@example.com', 'name': 'Alice Editor',
              'groups': ['/nbgraph-editors', 'other']}
    claims.update(over)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm='RS256')


@pytest.fixture(autouse=True)
def oidc_env(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'oidc')
    monkeypatch.setenv('OIDC_ISSUER', ISS + '/')
    monkeypatch.setenv('OIDC_CLIENT_ID', 'nb-graph')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_valid_token_maps_user_and_strips_group_paths():
    u = auth.verify(token(), FakeJWKS())
    assert (u.username, u.email, u.name) == ('alice', 'alice@example.com', 'Alice Editor')
    assert u.groups == ['nbgraph-editors', 'other']


@pytest.mark.parametrize('bad', [
    {'exp': int(time.time()) - 120},          # expired (beyond leeway)
    {'iss': 'http://evil.test/realms/x'},     # wrong issuer
    {'aud': 'some-other-client'},             # wrong audience
    {'sub': None},                            # required claim missing
])
def test_rejected_claims(bad):
    with pytest.raises(auth.AuthError) as e:
        auth.verify(token(**bad), FakeJWKS())
    assert e.value.status == 401


def test_wrong_signature_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify(token(key=OTHER), FakeJWKS())


def test_user_outside_allowed_groups_is_forbidden():
    with pytest.raises(auth.AuthError) as e:
        auth.verify(token(groups=['/somebody-else']), FakeJWKS())
    assert e.value.status == 403


def test_internal_url_rewrite(monkeypatch):
    monkeypatch.setenv('OIDC_INTERNAL_URL', 'http://keycloak:8080/realms/nbgraph')
    get_settings.cache_clear()
    assert auth._internal(ISS + '/protocol/openid-connect/certs') == \
        'http://keycloak:8080/realms/nbgraph/protocol/openid-connect/certs'
    assert auth._internal('http://elsewhere/x') == 'http://elsewhere/x'


# ------------------------------------------------------------------------------------------- middleware
@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI, Request

    from app.netbox import request_token

    def fake_verify(tok, jwks=None):
        if tok != 'good':
            raise auth.AuthError('invalid access token')
        return auth.User(username='alice', groups=['nbgraph-editors'])

    monkeypatch.setattr(auth, 'verify', fake_verify)
    monkeypatch.setattr(auth, 'netbox_token_for', lambda u: f'nbt_for_{u.username}')
    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)

    @app.get('/api/me')
    def me(request: Request):  # sync: runs in a worker thread, like the real endpoints
        return {'user': request.state.user.username, 'token': request_token.get()}

    @app.get('/api/events/stream')
    def stream(request: Request):
        return {'user': request.state.user.username}

    @app.get('/api/health')
    def health():
        return {'ok': True}

    return TestClient(app)


def test_middleware_requires_token(client):
    r = client.get('/api/me')
    assert r.status_code == 401 and r.headers['www-authenticate'] == 'Bearer'
    assert client.get('/api/me', headers={'Authorization': 'Bearer nope'}).status_code == 401


def test_middleware_sets_user_and_per_user_netbox_token(client):
    r = client.get('/api/me', headers={'Authorization': 'Bearer good'}).json()
    assert r == {'user': 'alice', 'token': 'nbt_for_alice'}


def test_query_token_only_for_sse(client):
    assert client.get('/api/me?access_token=good').status_code == 401
    assert client.get('/api/events/stream?access_token=good').json() == {'user': 'alice'}


def test_public_paths_skip_auth(client):
    assert client.get('/api/health').status_code == 200


def test_real_health_advertises_oidc(monkeypatch):
    from app import main
    monkeypatch.setattr(main.db, 'server_version', lambda: '19beta4')
    monkeypatch.setattr(main.NetBox, 'status', lambda self: {'netbox-version': '4.7.2'})
    r = TestClient(main.app).get('/api/health')
    assert r.status_code == 200
    assert r.json()['auth'] == {'mode': 'oidc', 'issuer': ISS, 'client_id': 'nb-graph'}


def test_auth_mode_none_is_a_no_op(monkeypatch, client):
    monkeypatch.setenv('AUTH_MODE', 'none')
    get_settings.cache_clear()
    assert auth.public_config() == {'mode': 'none'}
    assert client.get('/api/health').status_code == 200


class FakeNB:
    def __init__(self, users):
        self.users, self.calls = users, []

    def first(self, path, **kw):
        if path == 'users/users/':
            return next((u for u in self.users if u['username'] == kw['username']), None)
        return {'id': 7, 'name': kw.get('name')}

    def patch(self, path, body):
        self.calls.append(('patch', path, body))
        return {'id': 1, **body}

    def post(self, path, body):
        self.calls.append(('post', path, body))
        return {'id': 2, **body}


def test_sync_refuses_superuser_accounts(monkeypatch):
    monkeypatch.setattr(auth, '_is_superuser', lambda username: username == 'admin')
    nb = FakeNB([{'id': 1, 'username': 'admin'}])
    with pytest.raises(auth.AuthError) as e:
        auth._sync_user(nb, auth.User(username='admin', groups=['nbgraph-editors']))
    assert e.value.status == 403 and nb.calls == []      # nothing patched, no groups changed


def test_sync_updates_ordinary_user_and_maps_only_allowed_groups(monkeypatch):
    monkeypatch.setattr(auth, '_is_superuser', lambda username: False)
    nb = FakeNB([{'id': 1, 'username': 'alice', 'is_superuser': False}])
    auth._sync_user(nb, auth.User(username='alice', name='Alice Editor', groups=['nbgraph-editors', 'other']))
    (op, path, body), = nb.calls
    assert (op, path, body['groups'], body['first_name']) == ('patch', 'users/users/1/', [7], 'Alice')
