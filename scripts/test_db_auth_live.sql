-- Throwaway test database only (scripts/test_db.py). Never apply to a shared project.
-- The plain supabase/postgres image ships older auth helpers than a GoTrue-migrated project:
-- its auth.uid() reads only request.jwt.claim.sub and auth.jwt() does not exist. These are the
-- definitions read from the live project `pulse` (schema dump of `auth`, 2026-10-30), so tests see
-- the same auth.uid()/auth.role()/auth.email()/auth.jwt() behaviour as production.
-- Re-check against the live dump during each database sync (PULSE_DATABASE_SYNC_POLICY.md).

create or replace function auth.uid() returns uuid language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

create or replace function auth.role() returns text language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;

create or replace function auth.email() returns text language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.email', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'email')
  )::text
$$;

create or replace function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')
  )::jsonb
$$;

grant execute on function auth.uid(), auth.role(), auth.email(), auth.jwt() to anon, authenticated, service_role;
