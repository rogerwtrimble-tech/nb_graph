-- =====================================================================================================
-- nb_graph : property-graph projection of NetBox, kept in PostgreSQL 19
--
-- Every vertex and edge is computed live from NetBox's own tables, so nothing is copied and nothing
-- needs syncing.
--
-- Design notes
--   * The *_fn() functions are plain LANGUAGE sql functions with string bodies. PostgreSQL inlines them
--     into the calling query, so filters such as  WHERE src_kind = 'site' AND src_id = 7  reach each
--     UNION ALL branch and use NetBox's FK indexes. Unlike views on NetBox tables, they register no
--     catalog dependencies, so NetBox migrations never get blocked by the graph layer.
--   * The vertex/edge shape matches SQL/PGQ (label + key + properties). When SQL/PGQ ships (it was
--     pulled from PG19 on 2026-09-07 and is expected in PG20), 090_pgq_future.sql can be applied with
--     no change to the API contract.
-- =====================================================================================================
SET check_function_bodies = off;

CREATE SCHEMA IF NOT EXISTS nbgraph;
COMMENT ON SCHEMA nbgraph IS 'nb_graph: property-graph projection over NetBox tables (vertices/edges/traversal)';

-- Content-type id -> graph kind (NetBox generic FKs: cable terminations, IP assignment, scopes)
CREATE OR REPLACE FUNCTION nbgraph.ct(app text, mdl text) RETURNS integer
LANGUAGE sql STABLE PARALLEL SAFE AS
$$ SELECT id FROM public.django_content_type WHERE app_label = app AND model = mdl $$;

CREATE OR REPLACE FUNCTION nbgraph.ct_kind(ct_id integer) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS
$$ SELECT CASE model WHEN 'circuittermination' THEN 'circuittermination' ELSE model END
     FROM public.django_content_type WHERE id = ct_id $$;

-- Registry of vertex kinds: label, UI grouping, and NetBox REST + UI paths.
CREATE TABLE IF NOT EXISTS nbgraph.kind (
    kind        text PRIMARY KEY,
    title       text NOT NULL,
    layer       text NOT NULL,   -- organisation | physical | logical | inventory | service
    api_path    text NOT NULL,   -- NetBox REST path, relative to /api/
    ui_path     text NOT NULL    -- NetBox web UI path
);

INSERT INTO nbgraph.kind VALUES
  ('region',             'Region',               'organisation', 'dcim/regions/',                      'dcim/regions/'),
  ('site',               'Site',                 'organisation', 'dcim/sites/',                        'dcim/sites/'),
  ('location',           'Location',             'organisation', 'dcim/locations/',                    'dcim/locations/'),
  ('device',             'Device',               'physical',     'dcim/devices/',                      'dcim/devices/'),
  ('interface',          'Interface',            'physical',     'dcim/interfaces/',                   'dcim/interfaces/'),
  ('frontport',          'Front port',           'physical',     'dcim/front-ports/',                  'dcim/front-ports/'),
  ('rearport',           'Rear port',            'physical',     'dcim/rear-ports/',                   'dcim/rear-ports/'),
  ('circuit',            'Circuit',              'physical',     'circuits/circuits/',                 'circuits/circuits/'),
  ('circuittermination', 'Circuit termination',  'physical',     'circuits/circuit-terminations/',     'circuits/circuit-terminations/'),
  ('provider',           'Provider',             'organisation', 'circuits/providers/',                'circuits/providers/'),
  ('prefix',             'Prefix',               'inventory',    'ipam/prefixes/',                     'ipam/prefixes/'),
  ('ipaddress',          'IP address',           'inventory',    'ipam/ip-addresses/',                 'ipam/ip-addresses/'),
  ('vlangroup',          'VLAN group',           'inventory',    'ipam/vlan-groups/',                  'ipam/vlan-groups/'),
  ('vlan',               'VLAN',                 'inventory',    'ipam/vlans/',                        'ipam/vlans/'),
  ('number',             'Telephone number',     'inventory',    'plugins/numbers/telephone-numbers/', 'plugins/numbers/telephone-numbers/'),
  ('virtualcircuit',     'Service (virtual circuit)', 'service', 'circuits/virtual-circuits/',         'circuits/virtual-circuits/'),
  ('tenant',             'Tenant / subscriber',  'organisation', 'tenancy/tenants/',                   'tenancy/tenants/')
ON CONFLICT (kind) DO UPDATE SET title = EXCLUDED.title, layer = EXCLUDED.layer,
                                 api_path = EXCLUDED.api_path, ui_path = EXCLUDED.ui_path;

-- Registry of edge labels (documentation + UI lens defaults)
CREATE TABLE IF NOT EXISTS nbgraph.edge_label (
    label       text PRIMARY KEY,
    description text NOT NULL,
    lens        text[] NOT NULL  -- which UI lenses show it: service, physical, inventory
);

INSERT INTO nbgraph.edge_label VALUES
  ('CONTAINS',        'Region/site/location/group containment',                  '{service,physical,inventory}'),
  ('HOSTS',           'Site or location hosts a device',                         '{service,physical,inventory}'),
  ('HAS_INTERFACE',   'Device owns an interface',                                '{service,physical,inventory}'),
  ('HAS_SUBINTERFACE','Interface parent -> child (e.g. eth1 -> eth1.101)',       '{service,physical,inventory}'),
  ('HAS_PORT',        'Device owns a front/rear pass-through port',              '{physical}'),
  ('MAPS',            'Rear port position -> front port (splitter leg)',         '{physical}'),
  ('CABLED',          'Physical cable between two terminations',                 '{physical}'),
  ('FEEDS',           'OLT PON port feeds an ONT (derived from NetBox cable trace)', '{service,physical}'),
  ('ASSIGNED_IP',     'IP address assigned to an interface',                     '{service,inventory}'),
  ('UNTAGGED_VLAN',   'Access / native VLAN of an interface',                    '{service,inventory}'),
  ('TAGGED_VLAN',     'Tagged VLAN on a trunk interface',                        '{service,inventory}'),
  ('QINQ_SVLAN',      'Q-in-Q service VLAN of an interface',                     '{service,inventory}'),
  ('CARRIES',         'S-VLAN carries a C-VLAN (Q-in-Q)',                        '{inventory}'),
  ('ASSIGNED_NUMBER', 'Telephone number assigned to an interface',               '{service,inventory}'),
  ('TERMINATES',      'Interface terminates a service (virtual circuit)',        '{service}'),
  ('HAS_PREFIX',      'Site-scoped prefix (IP pool)',                            '{inventory}'),
  ('HAS_VLAN_GROUP',  'Site-scoped VLAN group',                                  '{inventory}'),
  ('HAS_NUMBER',      'Telephone number in the site DID pool',                   '{inventory}'),
  ('CONTAINS_IP',     'Prefix contains IP address',                              '{inventory}'),
  ('PART_OF',         'Circuit termination belongs to a circuit',                '{physical}'),
  ('PROVIDED_BY',     'Circuit delivered by a provider',                         '{physical}'),
  ('BELONGS_TO',      'Object belongs to a tenant / subscriber',                 '{service}')
ON CONFLICT (label) DO UPDATE SET description = EXCLUDED.description, lens = EXCLUDED.lens;
