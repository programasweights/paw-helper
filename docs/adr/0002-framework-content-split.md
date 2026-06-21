# ADR 0002: Framework + content-pack split (not config-only)

Status: accepted

## Context
To let others reuse the backend, the generic method must be separable from
Yuntian-specific content. Some content is pure data (specs, facts, links), but
some is *code* (course schedule rendering, student roster, the RAG seam).

## Decision
Split into a pip-installable framework (`paw_helper`) and a per-deployment content
pack. The pack is data + a single `providers.py` that registers fact/resource
providers against a documented contract. The framework loads a pack via
`--content <dir>` / `PAW_HELPER_CONTENT`.

Rejected: config-only packs (YAML/specs but no code). Volatile facts (course
deadlines, rosters, future Piazza RAG) need Python to render/retrieve, so a
code seam is required.

## Consequences
- A clear, versioned contract (`schema_version`, `paw-helper validate`).
- Content packs can ship arbitrary providers (extensible to RAG) without forking
  the framework.
- Slightly more surface than config-only, but matches how real content behaves.
