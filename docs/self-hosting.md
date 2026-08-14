# Self-hosting OpenLivery

Everything you need to run OpenLivery in production or locally. For a feature
overview see the [README](../README.md).

OpenLivery is four services: PostgreSQL, the FastAPI backend, the Next.js
frontend and the WhatsApp bridge (Baileys). Docker Compose runs all four; a
`Makefile` wraps the common commands.

## Contents

- [Run with Docker](#run-with-docker)
- [Environment variables](#environment-variables)
- [Day-to-day operation](#day-to-day-operation)
- [Backup and restore](#backup-and-restore)
- [Run without Docker](#run-without-docker)
- [Connect WhatsApp](#connect-whatsapp)
- [Tests](#tests)
- [Security](#security)
- [WhatsApp / Baileys caveats](#whatsapp--baileys-caveats)

## Run with Docker

Requirements: Docker Desktop (macOS/Windows) or Docker Engine + Compose plugin
(Linux). Check it is running with `docker compose version`.

```bash
git clone <REPOSITORY_URL>
cd openlivery
./scripts/generate-docker-env.sh   # writes .env.docker with random secrets (gitignored)
make up                            # build and start everything
```

`make up` builds the images, starts the four containers, creates the database
and runs the Alembic migrations. Then open:

- App — http://localhost:3000
- API docs — http://localhost:8000/docs

The WhatsApp bridge port is never published on the host; only the backend
reaches it over the private Compose network.

Override host ports inline when they clash with other services (this keeps the
browser's API URL in sync automatically):

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

`make` targets: `up`, `down`, `stop`, `start`, `restart`, `build`, `logs`
(`SERVICE=api` to filter), `ps`, `migrate`, `test`, `shell-api`, `shell-db`,
`destroy`, `help`.

> `NEXT_PUBLIC_API_URL` is baked into the frontend at build time. `make` derives
> it from `API_PORT`; if you build the web image with raw `docker compose`, pass
> `NEXT_PUBLIC_API_URL` yourself or it will point at the default port.

## Environment variables

`./scripts/generate-docker-env.sh` fills these with random values. To set them by
hand, copy `.env.docker.example` to `.env.docker` and replace every `CHANGE_*`.

| Variable | Scope | Use |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Private network | Main PostgreSQL database. |
| `POSTGRES_TEST_DB` | Private network | Isolated database for `pytest`. |
| `SECRET_KEY` | Backend | Signs the agency and portal sessions. |
| `ENCRYPTION_KEY` | Backend / persisted data | Encrypts API keys, QR and the WhatsApp session. **Must not change** after secrets are stored. |
| `WHATSAPP_BRIDGE_TOKEN` | Backend + bridge | Authenticates the private backend↔bridge calls. |
| `FRONTEND_URL` | Backend | Origin allowed by CORS; usually `http://localhost:3000`. |
| `NEXT_PUBLIC_API_URL` | Browser / frontend build | Address the browser uses to reach the API. |
| `ACCESS_TOKEN_MINUTES` | Backend | Session lifetime. |
| `WHATSAPP_LOG_LEVEL` | Bridge | Log level; `silent` avoids exposing sensitive data. |
| `API_PORT`, `WEB_PORT`, `DB_PORT` | Host | Host ports (defaults `8000` / `3000` / `5432`). |
| `BIND_HOST` | Host | Bind address: `127.0.0.1` (local) or `0.0.0.0` (expose on a server). |

## Day-to-day operation

```bash
make logs                 # all services (SERVICE=api to filter)
make down                 # stop and remove containers (keeps data volumes)
make migrate              # apply Alembic migrations in the running api container
git pull && make up       # update after pulling a new version
```

## Backup and restore

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

Delete a test install (**permanently** removes the database, PDFs, keys and
WhatsApp sessions in the volumes):

```bash
make destroy
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
backend to send and receive messages. See `.env.example` for the full variable
list (`DATABASE_URL`, `BACKEND_URL`, `WHATSAPP_BRIDGE_URL`, `WHATSAPP_BRIDGE_PORT`,
`WHATSAPP_BRIDGE_TOKEN`, …).

## Connect WhatsApp

1. Open **Clients → the client → Channels → WhatsApp → Configure**.
2. Choose one of that client's agents and click **Connect with QR code**.
3. On the phone: **WhatsApp → Settings → Linked devices → Link a device**, scan
   the QR and wait for **Connected**.

Incoming messages appear in the agency **Inbox** and in the client portal. Click
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

## Security

- Provider API keys are encrypted (key derived from `ENCRYPTION_KEY`) and never
  returned in full to the browser.
- The full WhatsApp auth state and the temporary QR are encrypted before being
  stored in PostgreSQL; the browser only ever receives the temporary QR, and only
  for an authenticated agency admin.
- Backend and bridge authenticate with `WHATSAPP_BRIDGE_TOKEN`; do not reuse it as
  a portal password or an API key.
- Every query is scoped by `agency_id`; agency and portal endpoints re-check
  ownership before reading or sending data.
- Do not commit `.env`, databases, logs or secrets. For a public install enable
  HTTPS, `secure` cookies, a restrictive CORS policy and strong keys.

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
