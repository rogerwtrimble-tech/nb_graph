"""
Steps inserted into NetBox's SOCIAL_AUTH_PIPELINE:

  require_group       (after social_uid) - refuse users who are in none of NBGRAPH_OIDC_GROUPS before any NetBox
                      account is created or linked.
  link_existing_user  (after social_user) - graph-api creates NetBox users with the IdP's preferred_username
                      the first time someone uses the nb_graph UI. Link the SSO login to that same account
                      instead of creating "alice-1a2b3c". Never links onto a superuser.
  sync_groups         (after associate_user) - mirror the IdP groups listed in NBGRAPH_OIDC_GROUPS onto NetBox
                      groups of the same name (the same rule graph-api applies).
"""
from __future__ import annotations

import logging

from social_core.exceptions import AuthForbidden

from .groups import allowed_groups, claim_groups, plan_groups

log = logging.getLogger('nbgraph_sso')
GROUPS_CLAIM = 'groups'


def require_group(backend, response, *args, **kwargs):
    allowed = allowed_groups()
    if allowed and not claim_groups((response or {}).get(GROUPS_CLAIM)) & allowed:
        log.warning('refusing SSO login %s: in none of %s', (response or {}).get('preferred_username'), sorted(allowed))
        raise AuthForbidden(backend)
    return None


def link_existing_user(backend, details, user=None, *args, **kwargs):
    if user is not None:
        return None
    username = (details or {}).get('username')
    if not username:
        return None
    from django.contrib.auth import get_user_model
    existing = get_user_model().objects.filter(username=username).first()
    if existing is None:
        return None
    if existing.is_superuser:
        log.warning('refusing to link SSO login %s onto a NetBox superuser', username)
        raise AuthForbidden(backend)
    if existing.social_auth.filter(provider=backend.name).exists():
        # linked to a different IdP subject already (social_user would have matched the same one)
        log.warning('refusing to link SSO login %s: account is bound to another %s identity', username, backend.name)
        raise AuthForbidden(backend)
    log.info('linking SSO login %s to existing NetBox user', username)
    return {'user': existing, 'is_new': False}


def sync_groups(backend, user, response, *args, **kwargs):
    if user is None:
        return None
    if user.is_superuser:
        raise AuthForbidden(backend)
    from users.models import Group
    allowed = allowed_groups()
    claimed = claim_groups((response or {}).get(GROUPS_CLAIM))
    current = set(user.groups.values_list('name', flat=True))
    add, remove = plan_groups(claimed, allowed, current)
    if add:
        found = list(Group.objects.filter(name__in=add))
        missing = add - {g.name for g in found}
        if missing:
            log.warning('IdP groups %s have no NetBox group of the same name', sorted(missing))
        user.groups.add(*found)
    if remove:
        user.groups.remove(*Group.objects.filter(name__in=remove))
    return None
