-- =====================================================================================================
-- OPTIONAL / FUTURE: native SQL/PGQ property graph over NetBox (ISO SQL:2023 Part 16)
--
-- Status (Oct 2026): SQL/PGQ was committed for PostgreSQL 19 and then REVERTED on 2026-09-07 before
-- GA, so PG19 GA does NOT have CREATE PROPERTY GRAPH. It is expected back in PG20.
-- nb_graph therefore does NOT apply this file automatically. The graph-api skips 09x files.
--
-- This file was checked against PostgreSQL 19beta3 (the last beta that still had SQL/PGQ) with the
-- nb_graph demo data. See docs/pg19-graph.md for the exact queries and their output.
-- Vertex/edge names match nbgraph.vertices / nbgraph.edges, so the API can switch to GRAPH_TABLE
-- for fixed-depth MATCH patterns without changing its contract.
--
-- Apply manually on a PGQ-capable server:   psql -f db/graph/090_pgq_future.sql
-- =====================================================================================================

-- NetBox puts the "natural_sort" collation on some name columns. SQL/PGQ needs a property to have one
-- type and collation across all labels, so shared properties (name, status, slug, role) are cast to text, and name is also
-- given COLLATE "default", below.

-- Helper views for relationships NetBox stores as generic FKs or derived cable traces
CREATE OR REPLACE VIEW nbgraph.pgq_assigned_ip AS
SELECT a.id, a.assigned_object_id AS interface_id, a.id AS ipaddress_id
  FROM public.ipam_ipaddress a
 WHERE a.assigned_object_type_id = nbgraph.ct('dcim', 'interface');

CREATE OR REPLACE VIEW nbgraph.pgq_feeds AS
SELECT cp.id, split_part(cp.path -> -1 ->> 0, ':', 2)::bigint AS pon_interface_id, oi.device_id AS ont_device_id
  FROM public.dcim_cablepath cp
  JOIN public.dcim_interface oi ON oi.id = split_part(cp.path -> 0 ->> 0, ':', 2)::bigint
  JOIN public.dcim_device od ON od.id = oi.device_id
  JOIN public.dcim_devicerole r ON r.id = od.role_id AND r.slug = 'ont'
 WHERE cp.is_complete
   AND split_part(cp.path -> 0 ->> 0, ':', 1)::int = nbgraph.ct('dcim', 'interface')
   AND split_part(cp.path -> -1 ->> 0, ':', 1)::int = nbgraph.ct('dcim', 'interface');

CREATE OR REPLACE VIEW nbgraph.pgq_device AS
SELECT d.id, d.name, d.status, d.site_id, d.location_id, d.tenant_id, r.slug AS role
  FROM public.dcim_device d JOIN public.dcim_devicerole r ON r.id = d.role_id;

DROP PROPERTY GRAPH IF EXISTS nbgraph.network;

CREATE PROPERTY GRAPH nbgraph.network
  VERTEX TABLES (
    public.dcim_region      AS region         KEY (id) LABEL region         PROPERTIES (id, name::text COLLATE "default" AS name, slug::text AS slug),
    public.dcim_site        AS site           KEY (id) LABEL site           PROPERTIES (id, name::text COLLATE "default" AS name, slug::text AS slug, status::text AS status),
    public.dcim_location    AS location       KEY (id) LABEL location       PROPERTIES (id, name::text COLLATE "default" AS name, site_id),
    nbgraph.pgq_device      AS device         KEY (id) LABEL device         PROPERTIES (id, name::text COLLATE "default" AS name, status::text AS status, role::text AS role),
    public.dcim_interface   AS interface      KEY (id) LABEL interface      PROPERTIES (id, name::text COLLATE "default" AS name, type, enabled, device_id),
    public.ipam_ipaddress   AS ipaddress      KEY (id) LABEL ipaddress      PROPERTIES (id, address, status::text AS status),
    public.ipam_vlan        AS vlan           KEY (id) LABEL vlan           PROPERTIES (id, vid, name::text COLLATE "default" AS name, qinq_role),
    public.netbox_numbers_telephonenumber AS number KEY (id) LABEL number   PROPERTIES (id, number, status::text AS status),
    public.circuits_virtualcircuit AS virtualcircuit KEY (id) LABEL virtualcircuit PROPERTIES (id, cid, status::text AS status),
    public.tenancy_tenant   AS tenant         KEY (id) LABEL tenant         PROPERTIES (id, name::text COLLATE "default" AS name)
  )
  EDGE TABLES (
    public.dcim_region AS region_contains_region KEY (id)
      SOURCE KEY (parent_id) REFERENCES region (id) DESTINATION KEY (id) REFERENCES region (id)
      LABEL contains NO PROPERTIES,
    public.dcim_site AS region_contains_site KEY (id)
      SOURCE KEY (region_id) REFERENCES region (id) DESTINATION KEY (id) REFERENCES site (id)
      LABEL contains NO PROPERTIES,
    public.dcim_location AS site_contains_location KEY (id)
      SOURCE KEY (site_id) REFERENCES site (id) DESTINATION KEY (id) REFERENCES location (id)
      LABEL contains NO PROPERTIES,
    nbgraph.pgq_device AS site_hosts_device KEY (id)
      SOURCE KEY (site_id) REFERENCES site (id) DESTINATION KEY (id) REFERENCES device (id)
      LABEL hosts NO PROPERTIES,
    public.dcim_interface AS device_has_interface KEY (id)
      SOURCE KEY (device_id) REFERENCES device (id) DESTINATION KEY (id) REFERENCES interface (id)
      LABEL has_interface NO PROPERTIES,
    nbgraph.pgq_feeds AS feeds KEY (id)
      SOURCE KEY (pon_interface_id) REFERENCES interface (id) DESTINATION KEY (ont_device_id) REFERENCES device (id)
      LABEL feeds NO PROPERTIES,
    nbgraph.pgq_assigned_ip AS assigned_ip KEY (id)
      SOURCE KEY (interface_id) REFERENCES interface (id) DESTINATION KEY (ipaddress_id) REFERENCES ipaddress (id)
      LABEL assigned_ip NO PROPERTIES,
    public.dcim_interface AS untagged_vlan KEY (id)
      SOURCE KEY (id) REFERENCES interface (id) DESTINATION KEY (untagged_vlan_id) REFERENCES vlan (id)
      LABEL untagged_vlan NO PROPERTIES,
    public.netbox_numbers_telephonenumber AS assigned_number KEY (id)
      SOURCE KEY (interface_id) REFERENCES interface (id) DESTINATION KEY (id) REFERENCES number (id)
      LABEL assigned_number NO PROPERTIES,
    public.circuits_virtualcircuittermination AS terminates KEY (id)
      SOURCE KEY (interface_id) REFERENCES interface (id) DESTINATION KEY (virtual_circuit_id) REFERENCES virtualcircuit (id)
      LABEL terminates PROPERTIES (role::text AS role),
    public.circuits_virtualcircuit AS service_belongs_to KEY (id)
      SOURCE KEY (id) REFERENCES virtualcircuit (id) DESTINATION KEY (tenant_id) REFERENCES tenant (id)
      LABEL belongs_to NO PROPERTIES
  );

COMMENT ON PROPERTY GRAPH nbgraph.network IS 'nb_graph SQL/PGQ graph over NetBox (requires a PGQ-capable PostgreSQL)';

-- Example: Site -> OLT -> PON -> ONT -> port -> service, as one fixed-length MATCH
-- SELECT * FROM GRAPH_TABLE (nbgraph.network
--   MATCH (s IS site)-[IS hosts]->(olt IS device)-[IS has_interface]->(pon IS interface)
--         -[IS feeds]->(ont IS device)-[IS has_interface]->(port IS interface)-[IS terminates]->(svc IS virtualcircuit)
--   WHERE s.slug = 'chi-co-01' AND olt.role = 'olt'
--   COLUMNS (olt.name AS olt, pon.name AS pon, ont.name AS ont, port.name AS port, svc.cid AS service)
-- ) ORDER BY ont, port;
