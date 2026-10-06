-- =====================================================================================================
-- Traversal on the live projection.
--   nbgraph.neighbors(kind, id, dir, labels)              one hop
--   nbgraph.traverse(kind, id, depth, labels, dir, limit) breadth-first expansion, with visited set
--   nbgraph.shortest_path(a_kind, a_id, b_kind, b_id, max_depth, labels)
--
-- SQL/PGQ in PG19 would only have allowed fixed-length MATCH patterns. These functions give the
-- variable-length / shortest-path behaviour the UI needs, using plain PL/pgSQL BFS that works on PG15+.
-- Dynamic SQL puts each frontier kind in as a literal, so the planner prunes the UNION ALL down to
-- the one or two branches that can match and uses NetBox's FK indexes.
-- =====================================================================================================
SET check_function_bodies = off;

CREATE OR REPLACE FUNCTION nbgraph.neighbors(p_kind text, p_id bigint, p_dir text DEFAULT 'out',
                                             p_labels text[] DEFAULT NULL)
RETURNS TABLE (label text, src_kind text, src_id bigint, dst_kind text, dst_id bigint, props jsonb)
LANGUAGE plpgsql STABLE AS
$fn$
BEGIN
  IF p_dir IN ('out', 'both') THEN
    RETURN QUERY EXECUTE format(
      'SELECT e.label, e.src_kind, e.src_id, e.dst_kind, e.dst_id, e.props FROM nbgraph.edges_fn() e
        WHERE e.src_kind = %L AND e.src_id = $1 AND ($2::text[] IS NULL OR e.label = ANY($2))', p_kind)
      USING p_id, p_labels;
  END IF;
  IF p_dir IN ('in', 'both') THEN
    RETURN QUERY EXECUTE format(
      'SELECT e.label, e.src_kind, e.src_id, e.dst_kind, e.dst_id, e.props FROM nbgraph.edges_fn() e
        WHERE e.dst_kind = %L AND e.dst_id = $1 AND ($2::text[] IS NULL OR e.label = ANY($2))', p_kind)
      USING p_id, p_labels;
  END IF;
END
$fn$;

CREATE OR REPLACE FUNCTION nbgraph.traverse(p_kind text, p_id bigint, p_depth int DEFAULT 2,
                                            p_labels text[] DEFAULT NULL, p_dir text DEFAULT 'out',
                                            p_limit int DEFAULT 2500)
RETURNS TABLE (depth int, label text, src_kind text, src_id bigint, dst_kind text, dst_id bigint, props jsonb)
LANGUAGE plpgsql STABLE AS
$fn$
DECLARE
  visited  text[] := ARRAY[p_kind || ':' || p_id];
  frontier text[] := ARRAY[p_kind || ':' || p_id];
  nxt      text[];
  k        text;
  ids      bigint[];
  rec      record;
  other    text;
  n        int := 0;
  d        int;
BEGIN
  FOR d IN 1..greatest(p_depth, 1) LOOP
    nxt := '{}';
    FOR k IN SELECT DISTINCT split_part(x, ':', 1) FROM unnest(frontier) x LOOP
      ids := ARRAY(SELECT split_part(x, ':', 2)::bigint FROM unnest(frontier) x WHERE split_part(x, ':', 1) = k);
      FOR rec IN EXECUTE format(
          'SELECT e.label, e.src_kind, e.src_id, e.dst_kind, e.dst_id, e.props, true AS fwd FROM nbgraph.edges_fn() e
            WHERE %1$L IN (''out'',''both'') AND e.src_kind = %2$L AND e.src_id = ANY($1)
              AND ($2::text[] IS NULL OR e.label = ANY($2))
           UNION ALL
           SELECT e.label, e.src_kind, e.src_id, e.dst_kind, e.dst_id, e.props, false FROM nbgraph.edges_fn() e
            WHERE %1$L IN (''in'',''both'') AND e.dst_kind = %2$L AND e.dst_id = ANY($1)
              AND ($2::text[] IS NULL OR e.label = ANY($2))', p_dir, k)
        USING ids, p_labels
      LOOP
        depth := d; label := rec.label; src_kind := rec.src_kind; src_id := rec.src_id;
        dst_kind := rec.dst_kind; dst_id := rec.dst_id; props := rec.props;
        RETURN NEXT;
        other := CASE WHEN rec.fwd THEN rec.dst_kind || ':' || rec.dst_id ELSE rec.src_kind || ':' || rec.src_id END;
        IF NOT other = ANY(visited) THEN
          visited := visited || other;
          nxt := nxt || other;
        END IF;
        n := n + 1;
        IF n >= p_limit THEN RETURN; END IF;
      END LOOP;
    END LOOP;
    EXIT WHEN cardinality(nxt) = 0;
    frontier := nxt;
  END LOOP;
END
$fn$;

-- Undirected BFS shortest path. Returns the ordered hops: step, node id, and the edge used to reach it.
CREATE OR REPLACE FUNCTION nbgraph.shortest_path(a_kind text, a_id bigint, b_kind text, b_id bigint,
                                                 p_max_depth int DEFAULT 12, p_labels text[] DEFAULT NULL)
RETURNS TABLE (step int, node text, via_label text, via_dir text)
LANGUAGE plpgsql STABLE AS
$fn$
DECLARE
  target   text := b_kind || ':' || b_id;
  parent   jsonb := jsonb_build_object(a_kind || ':' || a_id, jsonb_build_object('p', NULL));
  frontier text[] := ARRAY[a_kind || ':' || a_id];
  nxt      text[];
  k        text;
  ids      bigint[];
  rec      record;
  other    text;
  cur      text;
  hops     jsonb := '[]';
  d        int;
BEGIN
  IF a_kind = b_kind AND a_id = b_id THEN
    step := 0; node := target; via_label := NULL; via_dir := NULL; RETURN NEXT; RETURN;
  END IF;
  FOR d IN 1..p_max_depth LOOP
    nxt := '{}';
    FOR k IN SELECT DISTINCT split_part(x, ':', 1) FROM unnest(frontier) x LOOP
      ids := ARRAY(SELECT split_part(x, ':', 2)::bigint FROM unnest(frontier) x WHERE split_part(x, ':', 1) = k);
      FOR rec IN EXECUTE format(
          'SELECT e.label, e.src_kind || '':'' || e.src_id AS here, e.dst_kind || '':'' || e.dst_id AS there, ''out'' AS dir
             FROM nbgraph.edges_fn() e
            WHERE e.src_kind = %1$L AND e.src_id = ANY($1) AND ($2::text[] IS NULL OR e.label = ANY($2))
           UNION ALL
           SELECT e.label, e.dst_kind || '':'' || e.dst_id, e.src_kind || '':'' || e.src_id, ''in''
             FROM nbgraph.edges_fn() e
            WHERE e.dst_kind = %1$L AND e.dst_id = ANY($1) AND ($2::text[] IS NULL OR e.label = ANY($2))', k)
        USING ids, p_labels
      LOOP
        other := rec.there;
        IF NOT parent ? other THEN
          parent := parent || jsonb_build_object(other, jsonb_build_object('p', rec.here, 'l', rec.label, 'd', rec.dir));
          nxt := nxt || other;
          IF other = target THEN
            -- walk the parent chain back to the start
            cur := target;
            WHILE cur IS NOT NULL LOOP
              hops := jsonb_build_array(jsonb_build_object('n', cur, 'l', parent -> cur ->> 'l',
                                                           'd', parent -> cur ->> 'd')) || hops;
              cur := parent -> cur ->> 'p';
            END LOOP;
            FOR rec IN SELECT ord, h FROM jsonb_array_elements(hops) WITH ORDINALITY AS t(h, ord) LOOP
              step := rec.ord - 1; node := rec.h ->> 'n'; via_label := rec.h ->> 'l'; via_dir := rec.h ->> 'd';
              RETURN NEXT;
            END LOOP;
            RETURN;
          END IF;
        END IF;
      END LOOP;
    END LOOP;
    EXIT WHEN cardinality(nxt) = 0;
    frontier := nxt;
  END LOOP;
END
$fn$;

-- Out-degree per vertex for a set of ids of one kind (shows the UI which nodes can still expand)
CREATE OR REPLACE FUNCTION nbgraph.out_degree(p_kind text, p_ids bigint[], p_labels text[] DEFAULT NULL)
RETURNS TABLE (nb_id bigint, degree bigint)
LANGUAGE plpgsql STABLE AS
$fn$
BEGIN
  RETURN QUERY EXECUTE format(
    'SELECT e.src_id, count(*) FROM nbgraph.edges_fn() e
      WHERE e.src_kind = %L AND e.src_id = ANY($1) AND ($2::text[] IS NULL OR e.label = ANY($2))
      GROUP BY e.src_id', p_kind)
    USING p_ids, p_labels;
END
$fn$;

CREATE OR REPLACE VIEW nbgraph.stats AS
SELECT 'vertex' AS element, kind AS name, count(*) AS total FROM nbgraph.vertices_fn() GROUP BY kind
UNION ALL
SELECT 'edge', label, count(*) FROM nbgraph.edges_fn() GROUP BY label;
