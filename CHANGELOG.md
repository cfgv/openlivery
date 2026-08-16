# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The three services (`apps/api`, `apps/web`, `apps/whatsapp`) share a single version
and are released together.

## [Unreleased]

## [0.1.0] - 2026-08-16

First tagged release.

### Added

- Multi-tenant, agency-scoped data model: agencies, users, clients, agents,
  conversations and messages, with every query isolated by `agency_id`.
- FastAPI backend with JWT auth in httpOnly cookies, SQLAlchemy models and
  Alembic migrations.
- Next.js web app: auth, dashboard, clients, agents, inbox, chat playground,
  settings, client portal and an embeddable chat widget.
- Typed i18n system (English default, Spanish) for all user-facing copy.
- WhatsApp integration through a Baileys bridge, with stateful sessions and a
  human/AI conversation mode toggle.
- AI chat over any OpenAI-compatible endpoint, with per-connection base URL and
  model configuration and connection testing.
- Knowledge documents: PDF text extraction, chunking, embedding and semantic
  retrieval assembled into the agent system prompt.
- Structured business brief for agents.
- Encryption at rest for AI API keys and WhatsApp session state.
- OpenAI and Anthropic model presets, including the GPT-5.6 family
  (`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`) and the `gpt-transcribe`
  transcription model.

### Infrastructure

- Docker Compose stack with a Makefile wrapper for build, run, migrate and test.
- Single-origin Caddy gateway (`/api/*` to the backend, everything else to the
  frontend).
- Prebuilt images published to GHCR.
- Per-IP rate limiting on public and unauthenticated endpoints.
- Custom per-client portal domains with on-demand TLS.
- README and self-hosting guide.

[Unreleased]: https://github.com/sarrazola/openlivery/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sarrazola/openlivery/releases/tag/v0.1.0
