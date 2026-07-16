# Phase 8 — Deployment + CI/CD

> Draft.

## Goal
Ship the whole stack to a public URL with CI enforcing quality gates.

## Features (planned)
52. `production-dockerfile` — multi-stage, non-root user, small image
53. `production-compose` — app + Qdrant + Postgres + Redis + Langfuse
54. `secrets-management` — `.env` strategy, no secrets in repo
55. `ci-lint-and-test` — GitHub Actions on every PR
56. `ci-eval-gate` — evals run on PR, block merge on regression
57. `cd-deploy-on-merge` — auto-deploy main to Fly.io
58. `flyio-config` — `fly.toml`, volumes for Qdrant + Postgres
59. `https-and-domain` — Fly.io TLS + optional custom domain
60. `public-readme` — architecture diagram, live URL, demo screenshots

## What you'll learn
- Multi-stage Docker builds and why image size matters
- Managing secrets across dev / CI / prod
- Deploying stateful services (Qdrant, Postgres) on Fly.io
- CI/CD patterns that catch quality regressions, not just syntax errors

## Exit checklist
- [ ] Public URL responds to `POST /ask`
- [ ] CI blocks a PR that degrades eval scores
- [ ] All secrets read from environment, none in git history
- [ ] `README.md` has architecture diagram + live demo link
- [ ] `LEARNINGS.md` closes with a project retrospective