-- =====================================================================================================
-- Vertices: one row per NetBox object that takes part in the graph.
--   kind | nb_id | label | subtype | status | props(jsonb)
-- Key = (kind, nb_id). The text id used by the API/UI is  kind || ':' || nb_id   (e.g. 'device:42').
-- =====================================================================================================
SET check_function_bodies = off;

CREATE OR REPLACE FUNCTION nbgraph.vertices_fn()
RETURNS TABLE (kind text, nb_id bigint, label text, subtype text, status text, props jsonb)
LANGUAGE sql STABLE AS
$fn$
-- organisation ---------------------------------------------------------------------------------------
SELECT 'region'::text, r.id, r.name::text, CASE WHEN r.parent_id IS NULL THEN 'root' ELSE 'region' END,
       'active'::text,
       jsonb_build_object('slug', r.slug, 'description', r.description, 'parent_id', r.parent_id,
                          'path', r.path::text)
  FROM public.dcim_region r
UNION ALL
SELECT 'site', s.id, s.name::text, 'site', s.status::text,
       jsonb_build_object('slug', s.slug, 'facility', s.facility, 'description', s.description,
                          'region_id', s.region_id, 'latitude', s.latitude, 'longitude', s.longitude,
                          'time_zone', s.time_zone)
  FROM public.dcim_site s
UNION ALL
SELECT 'location', l.id, l.name::text, 'location', l.status::text,
       jsonb_build_object('slug', l.slug, 'site_id', l.site_id, 'description', l.description)
  FROM public.dcim_location l
UNION ALL
SELECT 'tenant', t.id, t.name::text, 'tenant', 'active',
       jsonb_build_object('slug', t.slug, 'group_id', t.group_id, 'description', t.description)
  FROM public.tenancy_tenant t
UNION ALL
SELECT 'provider', p.id, p.name::text, 'provider', 'active',
       jsonb_build_object('slug', p.slug, 'description', p.description)
  FROM public.circuits_provider p
-- physical -------------------------------------------------------------------------------------------
UNION ALL
SELECT 'device', d.id, COALESCE(d.name, dt.model || ' #' || d.id)::text, dr.slug::text, d.status::text,
       jsonb_build_object('role', dr.name, 'role_color', dr.color, 'model', dt.model, 'device_type_id', dt.id,
                          'serial', d.serial, 'site_id', d.site_id, 'location_id', d.location_id,
                          'tenant', t.name, 'tenant_id', d.tenant_id,
                          'primary_ip4', host(pip.address), 'description', d.description,
                          'interface_count', d.interface_count)
  FROM public.dcim_device d
  JOIN public.dcim_devicerole dr ON dr.id = d.role_id
  JOIN public.dcim_devicetype dt ON dt.id = d.device_type_id
  LEFT JOIN public.tenancy_tenant t ON t.id = d.tenant_id
  LEFT JOIN public.ipam_ipaddress pip ON pip.id = d.primary_ip4_id
UNION ALL
SELECT 'interface', i.id, i.name::text, i.type::text,
       CASE WHEN NOT i.enabled THEN 'disabled'
            WHEN EXISTS (SELECT 1 FROM public.circuits_virtualcircuittermination vt WHERE vt.interface_id = i.id)
              OR EXISTS (SELECT 1 FROM public.dcim_interface c
                          JOIN public.circuits_virtualcircuittermination vt2 ON vt2.interface_id = c.id
                         WHERE c.parent_id = i.id)
              THEN 'provisioned'
            ELSE 'active' END,
       jsonb_build_object('device_id', i.device_id, 'device', d.name, 'device_role', dr.slug,
                          'enabled', i.enabled, 'mode', i.mode, 'mgmt_only', i.mgmt_only,
                          'description', i.description, 'cable_id', i.cable_id, 'parent_id', i.parent_id,
                          'mtu', i.mtu, 'speed', i.speed,
                          'service_class', CASE
                              WHEN i.type IN ('gpon','xgs-pon','xg-pon','epon','10g-epon','ngpon2') THEN 'pon'
                              WHEN i.name ILIKE 'wan%'  THEN 'wan'
                              WHEN i.name ILIKE 'voip%' THEN 'voip'
                              WHEN i.name ILIKE 'eth%'  THEN 'ethernet'
                              WHEN i.name ILIKE 'uplink%' OR i.name ILIKE 'xe-%' THEN 'uplink'
                              WHEN i.mgmt_only THEN 'mgmt'
                              ELSE 'other' END)
  FROM public.dcim_interface i
  JOIN public.dcim_device d ON d.id = i.device_id
  JOIN public.dcim_devicerole dr ON dr.id = d.role_id
UNION ALL
SELECT 'frontport', f.id, f.name::text, f.type::text, CASE WHEN f.cable_id IS NULL THEN 'free' ELSE 'connected' END,
       jsonb_build_object('device_id', f.device_id, 'device', d.name, 'positions', f.positions, 'cable_id', f.cable_id)
  FROM public.dcim_frontport f JOIN public.dcim_device d ON d.id = f.device_id
UNION ALL
SELECT 'rearport', r.id, r.name::text, r.type::text, CASE WHEN r.cable_id IS NULL THEN 'free' ELSE 'connected' END,
       jsonb_build_object('device_id', r.device_id, 'device', d.name, 'positions', r.positions, 'cable_id', r.cable_id)
  FROM public.dcim_rearport r JOIN public.dcim_device d ON d.id = r.device_id
UNION ALL
SELECT 'circuit', c.id, c.cid::text, ct.slug::text, c.status::text,
       jsonb_build_object('provider', p.name, 'provider_id', c.provider_id, 'type', ct.name,
                          'commit_rate_kbps', c.commit_rate, 'description', c.description)
  FROM public.circuits_circuit c
  JOIN public.circuits_provider p ON p.id = c.provider_id
  JOIN public.circuits_circuittype ct ON ct.id = c.type_id
UNION ALL
SELECT 'circuittermination', tt.id, (c.cid || ' / ' || tt.term_side)::text, 'term-' || lower(tt.term_side),
       CASE WHEN tt.cable_id IS NULL THEN 'free' ELSE 'connected' END,
       jsonb_build_object('circuit_id', tt.circuit_id, 'term_side', tt.term_side, 'site_id', tt._site_id,
                          'port_speed_kbps', tt.port_speed, 'cable_id', tt.cable_id)
  FROM public.circuits_circuittermination tt JOIN public.circuits_circuit c ON c.id = tt.circuit_id
-- inventory ("numbers") --------------------------------------------------------------------------------
UNION ALL
SELECT 'prefix', p.id, p.prefix::text, COALESCE(rl.slug, 'prefix')::text, p.status::text,
       jsonb_build_object('role', rl.name, 'site_id', p._site_id, 'is_pool', p.is_pool,
                          'description', p.description, 'size', 2 ^ (CASE WHEN family(p.prefix) = 4 THEN 32 ELSE 128 END - masklen(p.prefix)),
                          'used', (SELECT count(*) FROM public.ipam_ipaddress a
                                    WHERE host(a.address)::inet <<= p.prefix
                                      AND a.vrf_id IS NOT DISTINCT FROM p.vrf_id))
  FROM public.ipam_prefix p LEFT JOIN public.ipam_role rl ON rl.id = p.role_id
UNION ALL
SELECT 'ipaddress', a.id, a.address::text, COALESCE(NULLIF(a.role, ''), 'address')::text, a.status::text,
       jsonb_build_object('dns_name', a.dns_name, 'description', a.description, 'tenant_id', a.tenant_id,
                          'assigned_object_id', a.assigned_object_id)
  FROM public.ipam_ipaddress a
UNION ALL
SELECT 'vlangroup', g.id, g.name::text, 'vlangroup', 'active',
       jsonb_build_object('slug', g.slug, 'vid_ranges', g.vid_ranges::text, 'total_vlan_ids', g.total_vlan_ids,
                          'used', (SELECT count(*) FROM public.ipam_vlan v WHERE v.group_id = g.id))
  FROM public.ipam_vlangroup g
UNION ALL
SELECT 'vlan', v.id, (v.vid || ' ' || v.name)::text, COALESCE(NULLIF(v.qinq_role, ''), 'vlan')::text, v.status::text,
       jsonb_build_object('vid', v.vid, 'name', v.name, 'group_id', v.group_id, 'qinq_role', v.qinq_role,
                          'qinq_svlan_id', v.qinq_svlan_id, 'tenant_id', v.tenant_id, 'description', v.description)
  FROM public.ipam_vlan v
UNION ALL
SELECT 'number', n.id, n.number::text, 'did', n.status::text,
       jsonb_build_object('site_id', n.site_id, 'tenant_id', n.tenant_id, 'interface_id', n.interface_id,
                          'sip_username', n.sip_username, 'description', n.description)
  FROM public.netbox_numbers_telephonenumber n
-- service ----------------------------------------------------------------------------------------------
UNION ALL
SELECT 'virtualcircuit', vc.id, vc.cid::text, vt.slug::text, vc.status::text,
       jsonb_build_object('type', vt.name, 'tenant_id', vc.tenant_id, 'tenant', t.name,
                          'provider_network', pn.name, 'description', vc.description)
  FROM public.circuits_virtualcircuit vc
  JOIN public.circuits_virtualcircuittype vt ON vt.id = vc.type_id
  JOIN public.circuits_providernetwork pn ON pn.id = vc.provider_network_id
  LEFT JOIN public.tenancy_tenant t ON t.id = vc.tenant_id
$fn$;

CREATE OR REPLACE VIEW nbgraph.vertices AS
SELECT v.kind || ':' || v.nb_id AS id, v.*, k.layer, k.title AS kind_title,
       k.api_path || v.nb_id || '/' AS api_path, k.ui_path || v.nb_id || '/' AS ui_path
  FROM nbgraph.vertices_fn() v
  JOIN nbgraph.kind k ON k.kind = v.kind;

COMMENT ON VIEW nbgraph.vertices IS 'All graph vertices (live projection of NetBox objects)';
