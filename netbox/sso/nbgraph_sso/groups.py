"""Pure helpers (no Django), shared by the pipeline and its tests."""
from __future__ import annotations

import os


def allowed_groups(env: dict | None = None) -> set[str]:
    raw = (env if env is not None else os.environ).get('NBGRAPH_OIDC_GROUPS', 'nbgraph-editors,nbgraph-viewers')
    return {g.strip() for g in raw.split(',') if g.strip()}


def claim_groups(value) -> set[str]:
    """Normalise a groups claim: list of names (Keycloak may prefix '/'), or a single string."""
    if isinstance(value, str):
        value = [value]
    return {g.lstrip('/') for g in value or [] if isinstance(g, str) and g.strip('/')}


def plan_groups(claimed: set[str], allowed: set[str], current: set[str]) -> tuple[set[str], set[str]]:
    """Which managed NetBox groups to add and remove. Groups outside `allowed` are never touched,
    so memberships an admin granted by hand in NetBox survive sign-ins."""
    want = claimed & allowed
    return want - current, (current & allowed) - want
