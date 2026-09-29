-- db/provision_vicmap_loader.sql
--
-- D-60: run once, by hand, by a PostgreSQL superuser, against the target
-- database named in vicmap.toml's [database] section. No Phase 3 code path
-- ever executes this script -- the pipeline itself never needs superuser
-- privileges to stage or load a Vicmap delivery. The vicmap_loader role
-- this script creates is deliberately weaker than the hand that runs it,
-- and vicmap_acquire.staging.preflight_staging_privileges proves that
-- weakness at runtime rather than trusting this file to have been read.
--
-- Usage: psql -f db/provision_vicmap_loader.sql -d <dbname>
-- Then set vicmap_loader's password to the value stored in the 1Password
-- item created in 03-01 (op://nixos-services/vicmap_loader_credentials/password)
-- and export it as VICMAP_DB_PASSWORD wherever stage_order.py runs.

-- Replace the placeholder below with the real password before running this
-- script by hand -- never commit a real credential to this file.
CREATE ROLE vicmap_loader LOGIN PASSWORD 'REPLACE_WITH_1PASSWORD_VALUE';

CREATE EXTENSION IF NOT EXISTS postgis;

-- D-59: vicmap_loader owns both schemas it will ever write to. Ownership
-- (not a later grant statement) is what gives it USAGE/CREATE here -- there
-- is nothing further to grant on either of these two schemas.
CREATE SCHEMA IF NOT EXISTS vicmap_staging AUTHORIZATION vicmap_loader;
CREATE SCHEMA IF NOT EXISTS vicmap AUTHORIZATION vicmap_loader;

-- Deliberately no grant statement on schema public anywhere in this script
-- (D-59, DB-05): the loader must be unable to write there, and
-- vicmap_acquire.staging.preflight_staging_privileges proves that absence
-- at runtime with a real has_schema_privilege() check rather than trusting
-- this comment.
--
-- PostgreSQL 15 and later already revoke the ability to create objects in
-- schema public from the PUBLIC pseudo-role by default, so a fresh
-- PostgreSQL 15+ database needs nothing further here. On an older server,
-- the operator must remove that ability from the PUBLIC pseudo-role
-- explicitly -- this script deliberately issues no statement that would do
-- so, because altering an existing production database's global grants is
-- not something a provisioning script should do silently.

-- ---------------------------------------------------------------------
-- D-69/D-70: the publication gate's durable record lives in a dedicated
-- vicmap_audit schema, owned by the superuser running this script -- NOT
-- by vicmap_loader (research Open Question 2's tighter model). The loader
-- is granted only SELECT+INSERT on the one table inside it: append-only,
-- no CREATE/UPDATE/DELETE, so the gate record can never be silently
-- rewritten by the pipeline that reads and writes it (T-04-08).
--
-- CURRENT_USER at script-run time is the connecting superuser, so this
-- schema is owned by whichever superuser role runs this script.
CREATE SCHEMA IF NOT EXISTS vicmap_audit AUTHORIZATION CURRENT_USER;

-- D-69: per staging run, the run_ts + frozen manifest digest + per-layer
-- verdict plus the D-56 metrics (row count, SRID, geometry type, repaired
-- count) -- nothing about mailbox state, idempotency, or history (that is
-- OPS-01's full audit subsystem, explicitly deferred).
CREATE TABLE IF NOT EXISTS vicmap_audit.staging_validation (
    run_ts text NOT NULL,
    manifest_digest text NOT NULL,
    target_table text NOT NULL,
    staging_table text NOT NULL,
    verdict text NOT NULL,
    spatial boolean NOT NULL,
    row_count bigint NOT NULL,
    srid integer,
    geometry_type text,
    repaired_count bigint,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_ts, manifest_digest, target_table)
);

GRANT USAGE ON SCHEMA vicmap_audit TO vicmap_loader;
GRANT SELECT, INSERT ON vicmap_audit.staging_validation TO vicmap_loader;

-- D-78/D-79/D-80/D-81: the publication generation marker, one row per
-- (run_ts, manifest_digest, target_table), written only inside
-- promote_order's own transaction and read by every publish_order.py run to
-- classify resumability (D-86) instead of inferring it from staging-table
-- absence alone. vicmap_loader is granted SELECT, INSERT only -- no
-- UPDATE/DELETE -- so a written marker can never be silently rewritten by
-- the pipeline that reads and writes it (T-04-08/D-88's no-backfill rule).
CREATE TABLE IF NOT EXISTS vicmap_audit.publication (
    run_ts text NOT NULL,
    manifest_digest text NOT NULL,
    target_table text NOT NULL,
    table_oid oid NOT NULL,
    server_version text NOT NULL,
    published_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_ts, manifest_digest, target_table)
);

GRANT SELECT, INSERT ON vicmap_audit.publication TO vicmap_loader;

-- ---------------------------------------------------------------------
-- D-72: the reader role is provisioned once by hand here -- never by the
-- pipeline. LOGIN + USAGE ON SCHEMA vicmap only: no CREATE, no table
-- privileges. Per-table SELECT is granted per-publish by vicmap_loader
-- (D-73, inside the publish transaction), never here (T-04-02).
--
-- Replace the placeholder below with the real password before running this
-- script by hand -- never commit a real credential to this file. The value
-- comes from the 1Password item created for Phase 4
-- (op://nixos-services/vicmap_reader_credentials/password) and is exported
-- as VICMAP_READER_PASSWORD wherever publish_order.py runs (D-74).
CREATE ROLE vicmap_reader LOGIN PASSWORD 'REPLACE_WITH_1PASSWORD_VALUE';
GRANT USAGE ON SCHEMA vicmap TO vicmap_reader;

-- ---------------------------------------------------------------------
-- Verification (paste into psql after running the statements above,
-- connected as any role against the same database -- these checks are
-- exactly what preflight_staging_privileges proves at runtime):
--
-- SELECT rolsuper FROM pg_roles WHERE rolname = 'vicmap_loader';
--   -- expect: false
-- SELECT has_schema_privilege('vicmap_loader', 'vicmap_staging', 'USAGE');
--   -- expect: true
-- SELECT has_schema_privilege('vicmap_loader', 'vicmap_staging', 'CREATE');
--   -- expect: true
-- SELECT has_schema_privilege('vicmap_loader', 'public', 'CREATE');
--   -- expect: false
-- SELECT 1 FROM spatial_ref_sys WHERE srid = 7899;
--   -- expect: one row
-- SELECT has_table_privilege('vicmap_loader', 'vicmap_audit.staging_validation', 'INSERT');
--   -- expect: true
-- SELECT has_table_privilege('vicmap_loader', 'vicmap_audit.staging_validation', 'UPDATE');
--   -- expect: false
-- SELECT has_table_privilege('vicmap_loader', 'vicmap_audit.publication', 'INSERT');
--   -- expect: true
-- SELECT has_table_privilege('vicmap_loader', 'vicmap_audit.publication', 'SELECT');
--   -- expect: true
-- SELECT has_table_privilege('vicmap_loader', 'vicmap_audit.publication', 'UPDATE');
--   -- expect: false
-- SELECT has_table_privilege('vicmap_loader', 'vicmap_audit.publication', 'DELETE');
--   -- expect: false
-- SELECT has_schema_privilege('vicmap_reader', 'vicmap', 'USAGE');
--   -- expect: true
-- SELECT has_schema_privilege('vicmap_reader', 'vicmap', 'CREATE');
--   -- expect: false
-- ---------------------------------------------------------------------
