# ADR 0004: Gate real metrics on the finetuned compiler

Status: accepted

## Context
PAW offers multiple compilers. The fast/default compiler is convenient but its
behavior is unstable across recompiles (a classifier can swing 30+ points,
degenerate, or over-decline). The finetuned compiler (`paw-ft-bs48`) is slow but
stable and higher quality.

## Decision
Pin and ship programs compiled with `paw-ft-bs48`. Treat fast-compiler numbers as
only directional. `programs.json` records the compiler and pins every program ID,
committed, so the server runs exactly what was evaluated (no compile on the server).

## Consequences
- Finetuned compiles can exceed the 120s gateway timeout; `compile.py` retries and
  relies on server-side caching, and saves `programs.json` after each success.
- Recompiling a finetuned program still has some variance, so every recompile is
  gated on the eval suite + the golden snapshot, and we avoid recompiling the
  flagship answerer for niche fixes (it reshuffles other answers).
