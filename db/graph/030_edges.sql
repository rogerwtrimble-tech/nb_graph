-- =====================================================================================================
-- Edges: directed, labelled relationships between vertices, derived from NetBox FKs, generic FKs,
-- cable terminations and NetBox's own cable-path trace (dcim_cablepath).
--   label | src_kind | src_id | dst_kind | dst_id | props(jsonb)
-- Direction runs "downward" (Region -> Site -> Device -> Interface -> number/service), so expanding
-- a node's outgoing edges walks the hierarchy the way an operator thinks about it.
-- =====================================================================================================
SET check_function_bodies = off;

CREATE OR REPLACE FUNCTION nbgraph.edges_fn()
RETURNS TABLE (label text, src_kind text, src_id bigint, dst_kind text, dst_id bigint, props jsonb)
LANGUAGE sql STABLE AS
$fn$
-- containment ------------------------------------------------------------------------------------------
SELECT 'CONTAINS'::text, 'region'::text, r.parent_id, 'region'::text, r.id, NULL::jsonb
  FROM public.dcim_region r WHERE r.parent_id IS NOT NULL
UNION ALL
SELECT 'CONTAINS', 'region', s.region_id, 'site', s.id, NULL FROM public.dcim_site s WHERE s.region_id IS NOT NULL
UNION ALL
SELECT 'CONTAINS', 'site', l.site_id, 'location', l.id, NULL FROM public.dcim_location l WHERE l.parent_id IS NULL
UNION ALL
SELECT 'CONTAINS', 'location', l.parent_id, 'location', l.id, NULL FROM public.dcim_location l WHERE l.parent_id IS NOT NULL
UNION ALL
SELECT 'HOSTS', 'site', d.site_id, 'device', d.id, jsonb_build_object('role', dr.slug)
  FROM public.dcim_device d JOIN public.dcim_devicerole dr ON dr.id = d.role_id WHERE d.location_id IS NULL
UNION ALL
SELECT 'HOSTS', 'location', d.location_id, 'device', d.id, jsonb_build_object('role', dr.slug)
  FROM public.dcim_device d JOIN public.dcim_devicerole dr ON dr.id = d.role_id WHERE d.location_id IS NOT NULL
-- components ---------------------------------------------------------------------------------------------
UNION ALL
SELECT 'HAS_INTERFACE', 'device', i.device_id, 'interface', i.id, NULL
  FROM public.dcim_interface i WHERE i.parent_id IS NULL
UNION ALL
SELECT 'HAS_SUBINTERFACE', 'interface', i.parent_id, 'interface', i.id, NULL
  FROM public.dcim_interface i WHERE i.parent_id IS NOT NULL
UNION ALL
SELECT 'HAS_PORT', 'device', f.device_id, 'frontport', f.id, NULL FROM public.dcim_frontport f
UNION ALL
SELECT 'HAS_PORT', 'device', r.device_id, 'rearport', r.id, NULL FROM public.dcim_rearport r
UNION ALL
SELECT 'MAPS', 'rearport', m.rear_port_id, 'frontport', m.front_port_id,
       jsonb_build_object('rear_position', m.rear_port_position, 'front_position', m.front_port_position)
  FROM public.dcim_portmapping m
-- cabling (A end -> B end) -------------------------------------------------------------------------------
UNION ALL
SELECT 'CABLED', nbgraph.ct_kind(a.termination_type_id), a.termination_id,
                 nbgraph.ct_kind(b.termination_type_id), b.termination_id,
       jsonb_build_object('cable_id', c.id, 'label', c.label, 'status', c.status, 'type', c.type, 'color', c.color)
  FROM public.dcim_cable c
  JOIN public.dcim_cabletermination a ON a.cable_id = c.id AND a.cable_end = 'A'
  JOIN public.dcim_cabletermination b ON b.cable_id = c.id AND b.cable_end = 'B'
-- derived: OLT PON port FEEDS ONT, using NetBox's completed cable trace (through splitter ports) ---------
UNION ALL
SELECT 'FEEDS', 'interface', split_part(cp.path -> -1 ->> 0, ':', 2)::bigint,
                'device', oi.device_id,
       jsonb_build_object('via', 'cablepath', 'path_id', cp.id, 'hops', jsonb_array_length(cp.path),
                          'ont_pon_interface_id', oi.id, 'active', cp.is_active)
  FROM public.dcim_cablepath cp
  JOIN public.dcim_interface oi ON oi.id = split_part(cp.path -> 0 ->> 0, ':', 2)::bigint
                               AND split_part(cp.path -> 0 ->> 0, ':', 1)::int = nbgraph.ct('dcim', 'interface')
  JOIN public.dcim_device od ON od.id = oi.device_id
  JOIN public.dcim_devicerole odr ON odr.id = od.role_id AND odr.slug = 'ont'
 WHERE cp.is_complete
   AND split_part(cp.path -> -1 ->> 0, ':', 1)::int = nbgraph.ct('dcim', 'interface')
-- addressing / numbering ---------------------------------------------------------------------------------
UNION ALL
SELECT 'ASSIGNED_IP', 'interface', a.assigned_object_id, 'ipaddress', a.id, NULL
  FROM public.ipam_ipaddress a
 WHERE a.assigned_object_type_id = nbgraph.ct('dcim', 'interface')
UNION ALL
SELECT 'UNTAGGED_VLAN', 'interface', i.id, 'vlan', i.untagged_vlan_id, NULL
  FROM public.dcim_interface i WHERE i.untagged_vlan_id IS NOT NULL
UNION ALL
SELECT 'TAGGED_VLAN', 'interface', tv.interface_id, 'vlan', tv.vlan_id, NULL
  FROM public.dcim_interface_tagged_vlans tv
UNION ALL
SELECT 'QINQ_SVLAN', 'interface', i.id, 'vlan', i.qinq_svlan_id, NULL
  FROM public.dcim_interface i WHERE i.qinq_svlan_id IS NOT NULL
UNION ALL
SELECT 'CARRIES', 'vlan', v.qinq_svlan_id, 'vlan', v.id, NULL
  FROM public.ipam_vlan v WHERE v.qinq_svlan_id IS NOT NULL
UNION ALL
SELECT 'CONTAINS', 'vlangroup', v.group_id, 'vlan', v.id, NULL
  FROM public.ipam_vlan v WHERE v.group_id IS NOT NULL
UNION ALL
SELECT 'ASSIGNED_NUMBER', 'interface', n.interface_id, 'number', n.id, NULL
  FROM public.netbox_numbers_telephonenumber n WHERE n.interface_id IS NOT NULL
UNION ALL
SELECT 'HAS_NUMBER', 'site', n.site_id, 'number', n.id, NULL
  FROM public.netbox_numbers_telephonenumber n WHERE n.site_id IS NOT NULL
UNION ALL
SELECT 'HAS_PREFIX', 'site', p._site_id, 'prefix', p.id, NULL
  FROM public.ipam_prefix p WHERE p._site_id IS NOT NULL
UNION ALL
SELECT 'HAS_VLAN_GROUP', 'site', g.scope_id, 'vlangroup', g.id, NULL
  FROM public.ipam_vlangroup g WHERE g.scope_type_id = nbgraph.ct('dcim', 'site')
UNION ALL
SELECT 'CONTAINS_IP', 'prefix', p.id, 'ipaddress', a.id, NULL
  FROM public.ipam_prefix p
  JOIN public.ipam_ipaddress a ON host(a.address)::inet <<= p.prefix AND a.vrf_id IS NOT DISTINCT FROM p.vrf_id
-- services & circuits -----------------------------------------------------------------------------------
UNION ALL
SELECT 'TERMINATES', 'interface', t.interface_id, 'virtualcircuit', t.virtual_circuit_id,
       jsonb_build_object('role', t.role)
  FROM public.circuits_virtualcircuittermination t
UNION ALL
SELECT 'PART_OF', 'circuittermination', t.id, 'circuit', t.circuit_id, jsonb_build_object('side', t.term_side)
  FROM public.circuits_circuittermination t
UNION ALL
SELECT 'PROVIDED_BY', 'circuit', c.id, 'provider', c.provider_id, NULL FROM public.circuits_circuit c
-- ownership ----------------------------------------------------------------------------------------------
UNION ALL
SELECT 'BELONGS_TO', 'device', d.id, 'tenant', d.tenant_id, NULL FROM public.dcim_device d WHERE d.tenant_id IS NOT NULL
UNION ALL
SELECT 'BELONGS_TO', 'virtualcircuit', v.id, 'tenant', v.tenant_id, NULL
  FROM public.circuits_virtualcircuit v WHERE v.tenant_id IS NOT NULL
$fn$;

CREATE OR REPLACE VIEW nbgraph.edges AS
SELECT e.label || ':' || e.src_kind || ':' || e.src_id || '>' || e.dst_kind || ':' || e.dst_id AS id,
       e.src_kind || ':' || e.src_id AS src, e.dst_kind || ':' || e.dst_id AS dst, e.*
  FROM nbgraph.edges_fn() e;

COMMENT ON VIEW nbgraph.edges IS 'All graph edges (live projection of NetBox relationships)';
