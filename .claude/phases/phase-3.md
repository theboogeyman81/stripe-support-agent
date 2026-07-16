# Phase 3 — Agent with tool use

> Draft.

## Goal
Convert the single-turn RAG endpoint into an agent that can decide when to
retrieve docs, do a calculation, look up mock user info, or open a ticket.

## Features (planned)
14. `agent-scaffold` — Pydantic AI agent, Gemini model binding
15. `tool-search-docs` — wraps `retrieve()`
16. `tool-calculator` — safe arithmetic evaluator
17. `tool-create-ticket` — Postgres-backed ticket table + write path
18. `tool-lookup-user` — mock user DB (seeded fixtures)
19. `agent-system-prompt` — prompt design, tool selection guidance
20. `multi-turn-state` — conversation history persistence
21. `chat-endpoint` — `POST /chat` with session id

## What you'll learn
- Tool-use loops: when the model calls, when it stops
- System prompt patterns for reliable tool selection
- Conversation state design (what to keep, what to drop)
- Handling tool failures without breaking the conversation

## Exit checklist
- [ ] Agent chooses `search_docs` for factual questions
- [ ] Agent chooses `create_ticket` for account/billing complaints
- [ ] Ticket rows persist in Postgres
- [ ] Multi-turn: turn 2 references turn 1 correctly
- [ ] Tool errors surface as graceful assistant messages, not 500s
- [ ] `LEARNINGS.md` updated with Phase 3 notes