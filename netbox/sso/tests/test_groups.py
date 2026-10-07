from nbgraph_sso.groups import allowed_groups, claim_groups, plan_groups


def test_allowed_groups_default_and_env():
    assert allowed_groups({}) == {'nbgraph-editors', 'nbgraph-viewers'}
    assert allowed_groups({'NBGRAPH_OIDC_GROUPS': ' a, b ,,'}) == {'a', 'b'}


def test_claim_groups_normalises():
    assert claim_groups(['/nbgraph-editors', 'x', '', '/', 3]) == {'nbgraph-editors', 'x'}
    assert claim_groups('nbgraph-viewers') == {'nbgraph-viewers'}
    assert claim_groups(None) == set()


def test_plan_groups_only_touches_managed_groups():
    allowed = {'nbgraph-editors', 'nbgraph-viewers'}
    # promoted from viewer to editor; a hand-granted 'noc' group is left alone
    add, remove = plan_groups({'nbgraph-editors', 'other'}, allowed, {'nbgraph-viewers', 'noc'})
    assert add == {'nbgraph-editors'} and remove == {'nbgraph-viewers'}
    assert plan_groups({'nbgraph-editors'}, allowed, {'nbgraph-editors'}) == (set(), set())
