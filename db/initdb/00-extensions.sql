-- Runs once, when the PostgreSQL 19 data volume is first initialised.
-- NetBox 4.7 needs ltree (and creates it during migration if it can); creating it here up front means
-- the migration never depends on superuser rights. pg_trgm speeds up ILIKE search on the graph.
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
