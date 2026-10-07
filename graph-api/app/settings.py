"""Runtime configuration for the nb_graph API (environment driven)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='', case_sensitive=False)

    # PostgreSQL 19 database shared with NetBox. The graph layer is read-only SQL over NetBox's tables.
    database_url: str = 'postgresql://netbox:netbox@postgres:5432/netbox'

    # NetBox REST API. All writes (CRUD and provisioning) go through it, so NetBox keeps
    # validation, change logging, webhooks and permissions.
    netbox_url: str = 'http://netbox:8080'
    netbox_public_url: str = 'http://localhost:8000'
    netbox_token: str = ''  # full v2 bearer value: nbt_<key>.<token>

    # Graph schema bootstrap
    graph_sql_dir: str = '/app/sql'
    graph_auto_install: bool = True

    # CORS origins for local UI development (vite dev server)
    cors_origins: str = 'http://localhost:5173,http://localhost:8080'

    # Authentication. 'none' (demo): the UI is open and every NetBox write uses NETBOX_TOKEN.
    # 'oidc': every /api call needs an OIDC access token (Keycloak, Entra ID, Okta, ...). Writes then go to
    # NetBox as that user, through a short-lived per-user NetBox token minted with NETBOX_TOKEN.
    auth_mode: str = 'none'
    oidc_issuer: str = ''          # must equal the token's "iss" (the URL the browser uses)
    oidc_internal_url: str = ''    # same issuer as reached from this container, if different
    oidc_client_id: str = 'nb-graph'
    oidc_audience: str = ''        # defaults to oidc_client_id
    oidc_groups_claim: str = 'groups'
    # Users must be in one of these IdP groups. Each one is mirrored to a NetBox group of the same name,
    # and NetBox object permissions on those groups decide what the user may change.
    oidc_groups: str = 'nbgraph-editors,nbgraph-viewers'
    user_token_ttl_minutes: int = 480

    # Shared secret NetBox webhooks send to /api/events/netbox (header X-NBGraph-Secret)
    webhook_secret: str = 'nbgraph-demo-webhook'


@lru_cache
def get_settings() -> Settings:
    return Settings()
