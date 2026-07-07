# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**literature-ai** — 科研文献智能解析与知识服务系统 (Academic Literature AI Parsing & Knowledge Service System). Upload PDF papers, parse them via LLM, build a FAISS vector knowledge base, then ask questions and generate reports against the paper content.

## Code Navigation — Use CodeGraph First

This repo is indexed by **CodeGraph** (a local code knowledge graph, exposed as MCP tools). Before diving into a task, use it to understand the code's structure and call relationships instead of blindly scanning files — it's faster and uses far fewer tokens.

**Workflow for any non-trivial task:**
1. **First, query the graph** to understand the relevant code logic:
   - `codegraph_explore <topic/feature>` — get relevant symbols' source + call paths in one shot (start here).
   - `codegraph_node <symbol|file>` — one symbol's source with its caller/callee trail, or a file with its dependents.
   - `callers` / `callees` / `impact <symbol>` — trace who calls a function, what it calls, and the blast radius of changing it.
2. **Then** read specific files. **Before making any code change, confirm the plan with the user first — do NOT edit code on your own initiative.** Explain what you intend to change and why, and wait for approval.
3. The index auto-syncs on file changes; if results look stale, run `codegraph sync` (or `codegraph init` to rebuild).

**Collaboration rules (multi-developer repo):**
- Cross-cutting changes are allowed: you may modify any file in the repo, including code originally written by other teammates, when the task calls for it. (Previously teammate code was off-limits; that restriction has been lifted.)
- When a change touches shared/other-owned code, prefer additive, backward-compatible edits (e.g. new optional props/query params) so existing features keep working, and call out the cross-file impact in your plan.
- Always confirm the plan before editing, deleting, or refactoring existing code.

CLI equivalents (`codegraph explore ...`, `codegraph node ...`) exist for terminal use, but prefer the MCP tools in-session.

## Repository Layout

```
aiproject/
├── backend/                  # Python FastAPI backend
│   ├── app/                  # FastAPI application (main, config, models, API routers)
│   │   ├── api/              # Route handlers: auth, papers, qa, reports, user, admin, mcp
│   │   ├── models.py         # SQLAlchemy ORM models + DB session
│   │   ├── config.py         # Paths, JWT secret, encryption key, upload limits
│   │   └── main.py           # FastAPI app entry point
│   ├── ai/                   # AI pipeline (PDF parsing, LLM, embeddings, QA, reports)
│   ├── mcp/                  # MCP tools: file_system, terminal, git, model
│   ├── prompts/              # LLM prompt templates (extraction.txt, qa_system.txt, report_templates/*.txt)
│   ├── data/                 # Runtime data — SQLite DB, uploads/, vectors/ (gitignored)
│   └── mcp_config.py         # MCP tool configuration
├── frontend/                 # Vue 3 + Vite SPA
│   └── src/
│       ├── api/index.js      # Axios client + all API wrappers
│       ├── stores/           # Pinia stores: auth, papers, user, ui
│       ├── pages/            # HomePage, PaperDetailPage
│       ├── components/       # Layout, PaperCard, QAInterface, ReportPanel, UploadModal, etc.
│       └── router/           # Vue Router routes
├── md/API.md                 # Full API contract document (authoritative)
└── doc/plantuml/             # Architecture diagrams
```

## Commands

### Backend (Python/FastAPI)

```bash
# Start dev server
cd backend
uvicorn app.main:app --reload --port 8000

# API docs: http://localhost:8000/docs
# Admin page: http://localhost:8000/admin
```

No formal test runner configured yet (pytest is in requirements.txt).

### Frontend (Vue 3/Vite)

```bash
cd frontend
npm install
npm run dev            # Dev server with HMR
npm run build          # Production build
npm run lint           # ESLint + Oxlint
npm run test:unit      # Vitest unit tests
npm run test:e2e       # Playwright E2E tests
npm run format         # Prettier
```

## Architecture

### Backend

- **Framework**: FastAPI on port 8000, CORS open to all origins.
- **Database**: MySQL via SQLAlchemy + PyMySQL (migrated from SQLite in commit `d49a817`). Connection string lives in `backend/db_config.json` (`DATABASE_URL`, e.g. `mysql+pymysql://...@localhost:3306/literature_db?charset=utf8mb4`). Tables: `users`, `admins`, `papers`, `paper_structured_info`, `chunks`, `conversations`, `messages`, `reports`.
  - **MySQL TEXT sizing**: SQLAlchemy `Text` maps to MySQL `TEXT` (64KB max), which overflows on full paper text → `(1406) Data too long`. Long LLM/extraction columns in `paper_structured_info` use MySQL dialect types: `full_text` is `LONGTEXT`; the other extraction fields are `MEDIUMTEXT` (imported from `sqlalchemy.dialects.mysql`). Use these dialect types, NOT generic `Text(length=...)` — autogenerate reflects MySQL columns back as `MEDIUMTEXT`/`LONGTEXT`, so a generic `Text(length=N)` in the model produces spurious "type change" diffs on every run. `create_all` only creates missing tables — it does NOT alter existing columns.
  - **Schema migrations (Alembic)**: managed by Alembic under `backend/migrations/` (config `backend/alembic.ini`). The DB URL is NOT hardcoded — `migrations/env.py` injects it from `db_config.json` (override via `ALEMBIC_DATABASE_URL`). `target_metadata = app.models.Base.metadata` drives `--autogenerate`. Baseline revision `8ffb22fe7333` matches the post-manual-ALTER schema. **Existing DBs must be stamped once** (`alembic stamp head`) so Alembic doesn't try to recreate tables; fresh DBs run `alembic upgrade head`. Daily flow: edit `models.py` → `alembic revision --autogenerate -m "..."` → **review the script** (autogenerate misses renames/type changes) → `alembic upgrade head` → commit. Teammates run `alembic upgrade head` after pull. Do NOT hand-write `ALTER` `.sql` anymore. Run alembic with the interpreter that has the deps installed (Windows: `...\Programs\Python\Python39`, not the WindowsApps shim). Full workflow: `backend/migrations/README.md`.
- **Auth**: Dual identity — anonymous sessions (`X-Session-ID` header) and JWT tokens (`Authorization: Bearer`). Anonymous data can be merged into a registered account. `get_current_user()` dependency handles both paths.
- **Admin**: Separate `admins` table, separate JWT with `role: "admin"` claim. Admin routes under `/api/admin/`. Frontend is an embedded static HTML (`admin_page.html`).
- **API Key encryption**: User-provided LLM API keys are AES-encrypted before storage (`pycryptodome`). Decryption helper `_decrypt()` in `user.py`.

### AI Pipeline (PDF → Knowledge Base)

The core flow lives in `backend/app/api/papers.py:_run_parse_pipeline()`:

1. **PDF Parsing** (`ai/pdf_parser.py`): PyMuPDF-based extraction. Handles dual-column layout, section detection via regex, figure/table detection, header/footer filtering. Returns `{full_text, sections, figures_tables}`.
2. **Structured Extraction** (`ai/info_extractor.py`): Sends first 5000 chars of text + section summary to LLM, expects JSON response with research background, questions, method, innovations, limitations, etc.
3. **Knowledge Base** (`ai/knowledge_base.py`): Chunks text (600 chars, 100 overlap), encodes with `BAAI/bge-large-zh-v1.5` via `sentence-transformers`, indexes with FAISS L2 distance. Index saved to `data/vectors/{paper_id}.index`. Chunks stored in DB for retrieval. **Hybrid retrieval (功能 B)**: `search_chunks()` fuses FAISS vector ranking with a `rank_bm25` BM25 keyword ranking (jieba-tokenized) via **RRF (Reciprocal Rank Fusion)**. Controlled by `SEARCH_CONFIG` in `ai/config.py` — `use_hybrid` (default true; false = pure-vector fallback for ablation), `fetch_k` (per-channel candidate pool), `rrf_k` (fusion constant), plus a `use_rerank` placeholder switch for a future cross-encoder (档位 2, not wired). The function signature is unchanged, so QA/report callers need no edits; if `jieba`/`rank_bm25` are missing it degrades to pure vector. Ablation harness: `backend/eval_hybrid.py`.
4. **QA** (`ai/qa_generator.py`): Multi-turn with question rewriting. Retrieves top-k chunks via `search_chunks()` (hybrid vector+BM25, see step 3), builds context prompt, calls LLM.
5. **Reports** (`ai/report_generator.py`): `quick`/`method`/`experiment` types. Queries knowledge base with bilingual terms depending on paper language detection.

### LLM Integration

- `LLMClient` (`ai/llm_client.py`): Supports DeepSeek and Qwen (DashScope) APIs. API key is per-user, stored encrypted in DB. The `_call_deepseek()` and `_call_qwen()` methods have different request formats — note Qwen uses `input.messages` while DeepSeek uses `messages` directly.

### Frontend

- **Stack**: Vue 3 (Composition API, `<script setup>`), Pinia stores, Vue Router (hash-free history mode), Axios.
- **Auth flow**: On mount, creates anonymous session if no token/session_id exists. Login/register replaces session with token. Logout destroys token and creates fresh anonymous session.
- **Stores**: `auth` (session/token management), `papers` (paper CRUD + polling), `user` (API key config), `ui` (modal visibility).

### MCP Module (Internal Tool System)

Located at `backend/mcp/`, this is a separate abstraction layer for tool management:
- `server.py`: Tool registry and execution dispatcher.
- `file_system.py`, `terminal.py`, `git.py`, `model.py`: Individual tool implementations.
- Each tool extends `MCPBase` (ABC with `name()`, `description()`, `commands()`, `execute()`).
- Exposed via `/api/mcp` routes. Used for system-level operations, not the core AI pipeline.

## API Conventions

See `md/API.md` for the full contract. Key conventions:
- All routes prefixed `/api/`
- `snake_case` field naming everywhere
- Pagination: `?page=1&size=20` → `{items, total, page, size}`
- Errors: `{"error": {"code": "ERROR_CODE", "message": "描述"}}`
- Auth: anonymous via `X-Session-ID`, logged-in via `Authorization: Bearer`

## Important Notes

- The `backend/data/` directory (uploads, vectors, *.db) is gitignored — it's runtime data.
- API keys were encrypted starting 6/25. Old database entries with plaintext keys need regeneration.
- The `chunks_data` parameter in `search_chunks()` was added to decouple the knowledge_base module from the database — callers from outside the app context should pass chunk data explicitly rather than relying on the DB import fallback.
- The admin page is a standalone HTML file (`admin_page.html`) served directly by FastAPI, not part of the Vue frontend.
- **User config endpoints auto-provision** (`api/user.py`): `get_current_user()` returns the raw `X-Session-ID` without checking the `users` table, but `GET/PUT /api/user/config` query that table. After the MySQL migration, old session IDs in browser `localStorage` no longer exist in the DB, which made the test endpoint pass (it never reads the user row) while save 404'd. Fix: `GET /config` now returns an empty config instead of 404, and `PUT /config` auto-creates an anonymous `User` row when missing.
- **Windows port 8000 / `WinError 10013`**: uvicorn may fail to bind 8000 even when nothing is using it — Hyper-V/WSL2/Docker (`winnat`) dynamically reserves port ranges that can cover 8000. Check with `netsh interface ipv4 show excludedportrange protocol=tcp`. Fix (admin shell): `net stop winnat && net start winnat`, or permanently reserve it: `netsh int ipv4 add excludedportrange protocol=tcp startport=8000 numberofports=1`. The frontend hardcodes `http://localhost:8000` in `frontend/src/api/index.js`, so changing the backend port also requires editing that file.
