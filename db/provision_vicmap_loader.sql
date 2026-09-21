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
-- Verification (paste into psql after running the statements above,
-- connected as any role against the same database -- these five checks are
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
-- ---------------------------------------------------------------------
