# Supabase storage on free Render hosting

Supabase keeps accounts and logs outside Render's temporary filesystem. Set up this backend before keeping real data. Free-tier limits, inactivity pausing, and backup needs still apply; external storage does not guarantee unlimited availability or prevent deletion.

1. In the Supabase project, run `supabase/setup.sql` once in SQL Editor. It creates `public.training_logs`, enables row-level security, revokes public/anonymous privileges, and grants signed-in users select/insert/update on their own row. The screenshot-guided setup already created this table; do not run it again if it exists.
2. Copy the project's HTTPS URL and its **publishable** key (`sb_publishable_…`). No database password, secret key, or service-role key is used by this integration.
3. In Render → elijah-risso → Environment, add:
   - `SUPABASE_URL`: your Supabase project HTTPS URL (no trailing path).
   - `SUPABASE_PUBLISHABLE_KEY`: the publishable key.
4. Save and deploy. With both configured, accounts use Supabase Auth and logs use Supabase PostgREST. Partial/invalid configuration fails explicitly; it never silently falls back to temporary SQLite storage.
5. In Supabase → Authentication → URL Configuration, set Site URL to `https://elijah-risso.onrender.com` and allow that same URL as a redirect. Keep email confirmation enabled. New signup sends a confirmation email; after confirming, return to the app and sign in. Existing SQLite test accounts are separate; create a Supabase account. No old account data is automatically migrated.
6. Test an account with sample data: log a lift, save a calorie goal, sign out/in on a second browser, and verify both. Verify storage persists after a Render restart before relying on it.

The browser gets HttpOnly access/refresh cookies, not a service-role key. The server verifies the signed-in user through Supabase Auth and sends that user's bearer token for every table request. The publishable key alone cannot read logs. Initial storage creation ignores duplicate inserts rather than replacing existing data. Writes compare the saved revision and return a conflict if a newer update exists. Supabase errors are shown without saving changes to SQLite as a fallback.

Guest mode remains browser-only. Use “Import this device’s earlier logs” after signing in to explicitly copy guest logs and goals. Photos are analyzed on demand but not stored in this table.

Local validation covers routing, email-confirmation behavior, token renewal, authorization headers, per-user query filters, stale-write handling, offline errors, and config failure. A live project/auth/storage request remains unverified until its publishable configuration is supplied. The tests mock Supabase service responses; they do not prove the remote project's configuration.

The SQL privacy policies were also executed against a disposable PostgreSQL 17 database with simulated Supabase auth roles. Tests verified two-user read isolation, allowed own-row writes, rejected foreign inserts/updates, stale revision protection, and rejected anonymous reads. This validates the SQL locally, not the remote project or live Auth service.
