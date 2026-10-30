# S.A.G.E

**S.A.G.E** (Smart AI Gateway Engine) is a multi-model LLM gateway that provides a unified API for routing requests across multiple AI providers, with a React chat client on top.

## Features

- One chat API in front of **OpenAI** (or any OpenAI-compatible API such as Groq or OpenRouter) and **Google Gemini**
- Token-by-token streaming over **Server-Sent Events**
- **Retries** with exponential backoff and jitter on rate limits, timeouts and 5xx errors
- **Fallback models**: if the requested model fails before replying, the next one in `FALLBACK_MODELS` is tried
- Per-provider **circuit breaker**, so a provider that keeps failing is skipped for a cooldown period
- **Timeouts**: per HTTP call, an idle timeout between chunks, and a total deadline per request
- **Automatic model router**: model `auto` scores each prompt (length, code, reasoning keywords, multiple questions, multi-step instructions, conversation length) against configurable rules and sends it to a cheap or a strong model. Every decision is stored with its score and reasons
- **Usage tracking**: prompt and completion tokens (as reported by the provider, estimated when not), total latency and time to first token, per request
- **Per-user daily quotas** on requests and tokens (HTTP 429 when exceeded)
- JWT auth (argon2 password hashing), per-user conversations with full message history
- Stopping a reply mid-stream keeps the partial text, saved as `cancelled`
- Offline `sage-echo` model so you can run everything without API keys

## Project layout

```
server/   FastAPI app (Python 3.14, uv)
  app/api/routes/   auth, conversations, chat (SSE), models
  app/llm/          providers, gateway (retry, timeouts, fallback, circuit breaker), router
  app/services/     usage totals and quota checks
  app/models/       SQLAlchemy models: User, Conversation, Message, UsageRecord
client/   React + Vite + TypeScript chat UI
docs/     decision log
```

## Quick Start

### 1. Server

```bash
cd server
cp .env.example .env      # fill in DATABASE_URL, JWT_SECRET and at least one API key
uv sync
uv run uvicorn app.main:app --reload
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Without any API key, only the offline `sage-echo` model (plus `auto`, which routes to it) is available. Set `OPENAI_API_KEY` and/or `GEMINI_API_KEY` to enable real models. The model lists can be changed with `OPENAI_MODELS` / `GEMINI_MODELS`.

### 2. Client

```bash
cd client
cp .env.example .env      # VITE_API_URL, defaults to http://localhost:8000
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173), create an account and start chatting.

### Run the tests

```bash
cd server && uv run pytest
```

Tests need `TEST_DATABASE_URL` (a separate database, it is wiped after every test). A local Postgres is much faster than a remote one:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user@localhost:5432/sage_test uv run pytest
```

## API

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create an account |
| POST | `/auth/login` | Get a bearer token |
| GET | `/auth/me` | Current user |
| GET | `/models` | Available models (including `auto` when routing is set up) and the default |
| GET | `/usage` | Today's requests, tokens, limits and per-model breakdown |
| GET | `/conversations` | List your conversations (newest first) |
| POST | `/conversations` | Create a conversation |
| GET | `/conversations/{id}` | Conversation with all messages |
| PATCH | `/conversations/{id}` | Rename |
| DELETE | `/conversations/{id}` | Delete with its messages |
| POST | `/conversations/{id}/messages` | Send a message, streams the reply as SSE |

### Streaming events

`POST /conversations/{id}/messages` with `{"content": "...", "model": "gpt-4o-mini"}` (`model` is optional) returns `text/event-stream`:

| Event | Data |
|---|---|
| `start` | `{user_message, model, requested_model, routing, title}`; `routing` is `{tier, score, reason}` when `auto` was used |
| `delta` | `{text, model}`, one per chunk; `model` shows which model answered if a fallback was used |
| `done` | `{message}`, the saved assistant message, with `usage` (tokens, latency, routing) |
| `error` | `{detail, message}`, the reply saved with status `error` |

### Auto routing

Send `"model": "auto"`. Points are added for: a long prompt (+1) or a very long one (+2), code (+2), reasoning keywords (+1 each, max +2), 3 or more questions (+1), 3 or more numbered steps (+1), and a long conversation (+1). A score at or above `ROUTER_THRESHOLD` goes to `ROUTER_COMPLEX_MODEL`, anything lower to `ROUTER_SIMPLE_MODEL`. All of these are set in `.env`.
