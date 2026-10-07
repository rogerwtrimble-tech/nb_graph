-- =====================================================================================================
-- Map view: sites placed by NetBox latitude/longitude, with per-site inventory roll-ups, and the
-- site-to-site circuits that join them.
--   nbgraph.site_map    one row per site (lat/long NULL = not placed on the map yet)
--   nbgraph.site_links  one row per circuit whose A and Z ends terminate on two different sites
-- =====================================================================================================

CREATE OR REPLACE VIEW nbgraph.site_map AS
SELECT s.id, s.name::text AS name, s.slug::text AS slug, s.status::text AS status, s.facility::text AS facility,
       r.id AS region_id, r.name::text AS region,
       s.latitude::float8 AS latitude, s.longitude::float8 AS longitude,
       COALESCE(d.devices, 0) AS devices,
       COALESCE(d.roles, '{}'::jsonb) AS roles,
       COALESCE(v.services, 0) AS services
  FROM public.dcim_site s
  LEFT JOIN public.dcim_region r ON r.id = s.region_id
  LEFT JOIN LATERAL (
        SELECT sum(n)::int AS devices, jsonb_object_agg(role, n) AS roles
          FROM (SELECT dr.slug::text AS role, count(*)::int AS n
                  FROM public.dcim_device dv JOIN public.dcim_devicerole dr ON dr.id = dv.role_id
                 WHERE dv.site_id = s.id GROUP BY dr.slug) x) d ON true
  LEFT JOIN LATERAL (
        SELECT count(DISTINCT t.virtual_circuit_id)::int AS services
          FROM public.circuits_virtualcircuittermination t
          JOIN public.dcim_interface i ON i.id = t.interface_id
          JOIN public.dcim_device dv ON dv.id = i.device_id
         WHERE dv.site_id = s.id) v ON true;

CREATE OR REPLACE VIEW nbgraph.site_links AS
SELECT c.id, c.cid::text AS cid, c.status::text AS status, p.name::text AS provider,
       a._site_id AS a_site_id, z._site_id AS z_site_id
  FROM public.circuits_circuit c
  JOIN public.circuits_provider p ON p.id = c.provider_id
  JOIN public.circuits_circuittermination a ON a.circuit_id = c.id AND a.term_side = 'A'
  JOIN public.circuits_circuittermination z ON z.circuit_id = c.id AND z.term_side = 'Z'
 WHERE a._site_id IS NOT NULL AND z._site_id IS NOT NULL AND a._site_id <> z._site_id;
