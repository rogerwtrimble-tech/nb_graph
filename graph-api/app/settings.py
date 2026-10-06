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

    # Shared secret NetBox webhooks send to /api/events/netbox (header X-NBGraph-Secret)
    webhook_secret: str = 'nbgraph-demo-webhook'


@lru_cache
def get_settings() -> Settings:
    return Settings()
