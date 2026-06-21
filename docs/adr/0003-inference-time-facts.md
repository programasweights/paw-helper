# ADR 0003: Inject facts at inference time, don't bake them in

Status: accepted

## Context
Some facts are volatile (course deadlines, office hours, student roster, "today's
date", "next assignment"). Baking them into a compiled program means recompiling
on every edit, and a stateless PAW function can't know the current date.

## Decision
Domains may set `facts_mode: runtime`. The framework injects facts from the
content pack at inference (`CONTEXT_PROVIDERS[<context>](query)`), under a header
the spec expects. The flat site answerer keeps `facts_mode: baked` (stable, and
it is the backtrack fallback).

## Consequences
- Editing facts/data needs only a `git pull` + restart - no recompile.
- Date-relative answers ("next assignment due") are computed in Python and
  injected, since the model never sees the current date.
- The same injection point is the seam for future RAG (retrieve -> inject).
