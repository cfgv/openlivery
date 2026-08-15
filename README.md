<p align="center">
  <img src="apps/web/public/brand/openlivery-logo-original.png" width="88" alt="OpenLivery" />
</p>

<h1 align="center">OpenLivery</h1>

<p align="center">
  Open-source, white-label platform for agencies to build, run and manage AI agents for their clients.
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-black" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/frontend-Next.js-black" alt="Next.js" />
</p>

---

OpenLivery is a multi-tenant workspace where an agency creates AI agents for its
clients, gives each client a branded portal, and talks to end users over
WhatsApp or an embeddable web chat widget. Bring your own OpenAI / Anthropic
keys and self-host the whole thing with one command.

## Features

**Agents**
- ✅ Instructions, personality, per-client & per-agent context, timezone, and temperature / max-tokens / memory controls
- ✅ Multimodal capabilities: **image recognition** (vision) and **audio transcription** for incoming media
- ✅ Creation wizard with a live token counter and industry starter templates
- ✅ Knowledge base: manual context, structured **Q&A pairs** and PDF upload, with embedding-based semantic retrieval (keyword fallback)

**AI providers**
- ✅ Bring-your-own **OpenAI** (Responses API) and **Anthropic** (Messages API) keys — agency-level, encrypted, and validated when saved

**Channels**
- ✅ **WhatsApp** through Baileys — QR link, per-client number, encrypted persistent session
- ✅ Embeddable **web chat widget** for any website
- 🚧 Instagram DM, Facebook Messenger, WhatsApp Cloud API *(planned)*

**Operations**
- ✅ Unified **Inbox** with server-side search, filter tabs (all / unread / human / AI), unread tracking, pagination and human takeover
- ✅ Per-client **portal** with its own login and Inbox
- ✅ **Dashboard** with activity, top agents, token usage by model and a date-range filter
- ✅ Agency **white-label** (name, identifier, color, logo) and toast notifications

## Architecture

Three services plus PostgreSQL, orchestrated by Docker Compose:

| App | Stack | Role |
| --- | --- | --- |
| `apps/api` | FastAPI · SQLAlchemy · Alembic | REST API, data model, AI/knowledge/provider services |
| `apps/web` | Next.js · React · TypeScript · Tailwind | Agency dashboard, client portal, playground, widget |
| `apps/whatsapp` | Node.js · Baileys | WhatsApp Web bridge (stateful sessions) |

All data lives in PostgreSQL; provider keys and WhatsApp sessions are encrypted
at rest. Every query is scoped by `agency_id` for tenant isolation.

## Quick start

Requires Docker (Desktop or Engine + Compose plugin).

```bash
git clone <REPOSITORY_URL>
cd openlivery
./scripts/generate-docker-env.sh   # random secrets in .env.docker (gitignored)
make up                            # build, start, migrate
```

Then open **http://localhost:3000** (API docs at **http://localhost:8000/docs**).
Ports clashing? `API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up`.

Full setup, environment variables, backups, non-Docker install and WhatsApp
linking are in **[docs/self-hosting.md](docs/self-hosting.md)**.

### First steps

1. **Create agency** on the first screen.
2. **Settings** → add your OpenAI and/or Anthropic API key (verified on save).
3. Create a **client**, then an **agent** for it (pick provider + model, write its instructions).
4. Add knowledge (context, Q&A, PDFs) and optionally enable image/audio.
5. Open the **Playground** to chat, then connect a **WhatsApp** number or copy the **Widget** embed snippet.

## How knowledge reaches the model

The system prompt is assembled in order: the agent's instructions and
personality → the local date/time in its timezone → the client's general
context → the agent's manual context → its Q&A pairs → retrieved PDF text →
recent history.

Small knowledge bases (≈45k characters) are sent in full; larger ones are
chunked, embedded on upload and retrieved by cosine similarity, with keyword
ranking as a fallback. Embeddings are stored as portable JSON vectors, so no
database extension is required.

## Project structure

```text
apps/
  api/         FastAPI backend (app/, migrations/, tests/)
  web/         Next.js frontend (app/, components/, lib/, types/)
  whatsapp/    Baileys WhatsApp bridge (src/)
docs/          Self-hosting and operations guide
scripts/       Helper scripts (generate-docker-env.sh)
Makefile       Common commands (make help)
docker-compose.yml
```

Language convention: all code, identifiers, comments and docs are in English.
End-user UI is localized (English default, Spanish) through the typed i18n
system in `apps/web/lib/i18n`.

## License

[MIT](./LICENSE).
