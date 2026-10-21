# Private alpha hosting

The alpha does not have a public address yet. Publishing the Codex environment does not deploy the app to the web.

This repository includes a Dockerfile, requires no package dependencies, and reads the host's `PORT` variable (default 3002). Account data is SQLite under `DATA_DIR` (default `.data` beside the source). The container defaults to `/data`; mount a persistent volume there, writable by UID 10001. Use a single server instance with SQLite. Do not include the development `.data` directory, API keys, or real account data in deployment images.

At your chosen Docker-compatible host:

1. Deploy this source using the Dockerfile, behind the host's HTTPS endpoint.
2. For free external storage, follow `SUPABASE-SETUP.md` and configure its two variables. SQLite alone instead needs persistent storage at `/data` and backups; without either option, redeployment may erase accounts and logs.
3. Optionally add `AI_API_KEY` securely to enable meal analysis. Lift tracking, food search, and manual macros work without it.
4. Open the host-provided HTTPS address and create a new alpha account. Verify sign-in and a saved lift from a second browser/device.

The development server and accounts are for a small private alpha. Password recovery, email verification, production monitoring, and a production server are still outstanding. Hosting may incur charges; no host or paid resources have been provisioned.
