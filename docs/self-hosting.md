# Self-hosting OpenLivery

Run and operate your own OpenLivery instance. For a feature overview see the
[README](../README.md).

OpenLivery is four services orchestrated by Docker Compose, with a `Makefile`
wrapping the common commands:

| Service | Image | Role |
| --- | --- | --- |
| `db` | PostgreSQL | All data (encrypted secrets at rest). |
| `api` | FastAPI | REST API, models, AI/knowledge/provider services. |
| `web` | Next.js | Agency dashboard, client portal, playground, widget. |
| `whatsapp` | Node.js + Baileys | WhatsApp Web bridge (internal only). |

One instance = **one agency** (the first registered user is its admin).

## Contents

- [Before you begin](#before-you-begin)
- [Install](#install)
- [Access your install](#access-your-install)
- [Secure your install](#secure-your-install)
- [Go to production (HTTPS)](#go-to-production-https)
- [Environment variables](#environment-variables)
- [Manage your install](#manage-your-install)
- [Backups](#backups)
- [Upgrade](#upgrade)
- [Uninstall](#uninstall)
- [Run without Docker](#run-without-docker)
- [Connect WhatsApp](#connect-whatsapp)
- [Tests](#tests)
- [WhatsApp / Baileys caveats](#whatsapp--baileys-caveats)

## Before you begin

You need a host with Docker:

- macOS / Windows — [Docker Desktop](https://www.docker.com/products/docker-desktop/).
- Linux / a server — Docker Engine with the Compose plugin.

Check it is running:

```bash
docker --version
docker compose version
```

For a public deployment you also need a **domain** and a server with ports
**80** and **443** open (see [Go to production](#go-to-production-https)).

## Install

```bash
git clone <REPOSITORY_URL>
cd openlivery
./scripts/generate-docker-env.sh   # writes .env.docker with random secrets (gitignored)
make up                            # build, start, run migrations
```

`make up` builds the images, starts the four containers, creates the database
and applies the Alembic migrations. All four should report `healthy`:

```bash
make ps
```

Override host ports inline when they clash with other services (this keeps the
browser's API URL in sync automatically):

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

## Access your install

- **App / dashboard** — http://localhost:3000
- **API docs** — http://localhost:8000/docs
- **PostgreSQL** — `make shell-db` (or connect to `localhost:5432`)

On the first screen choose **Create agency**; that account is the admin. The
WhatsApp bridge port is never published on the host — only the backend reaches
it over the private Compose network.

## Secure your install

Do this before exposing OpenLivery to anyone else.

- **Secrets.** `generate-docker-env.sh` fills `SECRET_KEY`, `ENCRYPTION_KEY`,
  `WHATSAPP_BRIDGE_TOKEN` and `POSTGRES_PASSWORD` with random values. If you set
  them by hand, use long random strings and never reuse them across installs.
- ⚠️ **`ENCRYPTION_KEY` must never change** once secrets are stored — it decrypts
  the provider API keys and the WhatsApp sessions. Losing or changing it makes
  them unrecoverable.
- **Keep services private.** Leave `BIND_HOST=127.0.0.1` (the default) so the
  database, API and frontend are only reachable from the host; expose the app to
  the internet **only** through the reverse proxy (next section). Never publish
  the PostgreSQL port on a public interface.
- **Do not commit `.env.docker`** or any backup that contains it; store it in a
  secret manager.
- Provider API keys are encrypted at rest and never returned in full to the
  browser; the WhatsApp auth state and QR are encrypted too. `WHATSAPP_BRIDGE_TOKEN`
  authenticates the backend↔bridge calls — do not reuse it as a password or key.

## Go to production (HTTPS)

The stack includes an optional **Caddy** reverse proxy that obtains and renews
HTTPS certificates automatically and serves the whole app from a single domain
(frontend and API share one origin, so the session cookie works with no extra
config).

1. Point your domain's DNS (an `A` record) at the server's IP and open ports
   **80** and **443**.
2. Set the domain in `.env.docker`:

   ```bash
   DOMAIN=agency.example.com
   ```

3. Deploy:

   ```bash
   make deploy
   ```

Caddy issues the certificate on the first request and routes `/api/*` to the
backend and everything else to the frontend. `FRONTEND_URL`, `NEXT_PUBLIC_API_URL`
and `COOKIE_SECURE=true` are configured for the domain automatically.

`make deploy` is `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d`.
To use your own proxy instead, skip the overlay and set `FRONTEND_URL`,
`NEXT_PUBLIC_API_URL` and `COOKIE_SECURE` yourself. If the frontend and API end
up on **different registrable domains**, also set `COOKIE_SAMESITE=none` (which
requires `COOKIE_SECURE=true`).

## Environment variables

`generate-docker-env.sh` fills the secrets. To set values by hand, copy
`.env.docker.example` to `.env.docker` and replace every `CHANGE_*`.

| Variable | Scope | Use |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Private network | Main PostgreSQL database. |
| `POSTGRES_TEST_DB` | Private network | Isolated database for `pytest`. |
| `SECRET_KEY` | Backend | Signs the agency and portal sessions. |
| `ENCRYPTION_KEY` | Backend / persisted data | Encrypts API keys, QR and the WhatsApp session. **Must not change** after secrets are stored. |
| `WHATSAPP_BRIDGE_TOKEN` | Backend + bridge | Authenticates the private backend↔bridge calls. |
| `FRONTEND_URL` | Backend | Origin allowed by CORS. |
| `NEXT_PUBLIC_API_URL` | Browser / frontend build | Address the browser uses to reach the API (baked at build time). |
| `COOKIE_SECURE` | Backend | `true` behind HTTPS so the session cookie is only sent over TLS. |
| `COOKIE_SAMESITE` | Backend | `lax` (default); `none` when the frontend and API are on different sites (requires `COOKIE_SECURE=true`). |
| `DOMAIN` | Reverse proxy | Public domain for `make deploy`. |
| `ACCESS_TOKEN_MINUTES` | Backend | Session lifetime. |
| `WHATSAPP_LOG_LEVEL` | Bridge | Log level; `silent` avoids exposing sensitive data. |
| `API_PORT`, `WEB_PORT`, `DB_PORT` | Host | Host ports (defaults `8000` / `3000` / `5432`). |
| `BIND_HOST` | Host | Bind address: `127.0.0.1` (local) or `0.0.0.0` (expose directly). |

## Manage your install

```bash
make logs                 # follow logs from all services (SERVICE=api to filter)
make ps                   # service status
make stop                 # stop containers (keep them)
make start                # start stopped containers
make restart              # restart all services
make migrate              # apply Alembic migrations in the running api container
make shell-api            # shell inside the api container
make shell-db             # psql inside the database
make down                 # stop and remove containers (keeps data volumes)
```

Run `make help` for the full list.

## Backups

Export PostgreSQL without stopping the app:

```bash
mkdir -p backups
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/openlivery.dump
```

Also store `.env.docker` in a secret manager: a backup with API keys or a
WhatsApp session needs the same `ENCRYPTION_KEY` to be decrypted.

Restore (replaces data in the target database — back up first):

```bash
docker compose --env-file .env.docker stop api whatsapp
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/openlivery.dump
docker compose --env-file .env.docker start api whatsapp
```

## Upgrade

```bash
git pull
make up        # or `make deploy` for the HTTPS production setup
```

New images are built and the backend runs `alembic upgrade head` on start, so
schema changes are applied automatically. Take a backup first.

## Uninstall

`make down` removes the containers and network but keeps your data. To delete
**everything** — database, PDFs, keys and WhatsApp sessions in the volumes:

```bash
make destroy   # irreversible
```

## Run without Docker

Requirements: Python 3.12+, Node.js 20+, PostgreSQL 14+ running.

```bash
# 1) databases
psql -d postgres -c "CREATE ROLE openlivery LOGIN PASSWORD 'openlivery';"
createdb -O openlivery openlivery
createdb -O openlivery openlivery_test

# 2) env
cp .env.example .env          # then set SECRET_KEY and ENCRYPTION_KEY

# 3) backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api && alembic upgrade head && uvicorn app.main:app --reload --port 8000

# 4) frontend (new terminal)
cd apps/web && npm install && npm run dev

# 5) WhatsApp bridge (new terminal)
cd apps/whatsapp && npm install && npm run start
```

The bridge listens only on `127.0.0.1:3101` and must stay running alongside the
backend. See `.env.example` for the full variable list (`DATABASE_URL`,
`BACKEND_URL`, `WHATSAPP_BRIDGE_URL`, `WHATSAPP_BRIDGE_PORT`, …).

## Connect WhatsApp

1. Open **Clients → the client → Channels → WhatsApp → Configure**.
2. Choose one of that client's agents and click **Connect with QR code**.
3. On the phone: **WhatsApp → Settings → Linked devices → Link a device**, scan
   the QR and wait for **Connected**.

Incoming messages appear in the agency **Inbox** and the client portal. Click
**Take over** to answer as a human (the AI pauses) and **Return to AI** to
resume. On restart the bridge reloads enabled sessions from PostgreSQL and
reconnects automatically — no new QR unless WhatsApp ends the session, the device
is unlinked or `ENCRYPTION_KEY` changes.

## Tests

Inside Docker:

```bash
make test   # backend pytest + rebuild the web/whatsapp validation stages
```

Locally:

```bash
cd apps/api && ../../.venv/bin/pytest -q     # backend (needs the openlivery_test DB)
cd apps/whatsapp && npm test && npm run build
cd apps/web && npm run lint && npm run build
```

Re-test the migrations from scratch:

```bash
cd apps/api && alembic downgrade base && alembic upgrade head
```

## WhatsApp / Baileys caveats

Baileys connects to the multi-device protocol of **WhatsApp Web**; the number is
linked as an extra device via QR. It is **not** the official WhatsApp Business
Cloud API, and this project is not affiliated with or endorsed by WhatsApp/Meta.

- WhatsApp may change its protocol or revoke a session/device without notice.
- Abusive automation, spam or mass sending can get a number restricted. Use only
  numbers authorized by each client and respect WhatsApp's terms.
- The QR links the account while valid — never share it or screenshot it publicly.
- The integration handles one-to-one conversations (text, plus transcribed voice
  notes and described images when the agent's capabilities are on). It ignores
  groups, statuses, newsletters, documents, locations, reactions and calls.
- One WhatsApp account belongs to one client; another client needs a different
  number. `apps/whatsapp/package.json` pins an exact Baileys version.
