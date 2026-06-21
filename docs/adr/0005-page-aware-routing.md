# ADR 0005: Page-aware domain routing (site as routing context)

Status: accepted

## Context
A page-blind router classified ambiguous/unnamed-subject questions ("who are the
authors", "is there a paper") by keyword association - usually to the site -
regardless of which page the visitor was on. Patching keywords was whack-a-mole.

## Decision
Feed the page into the router: it receives `Page: <label>\nMessage: <query>` (the
label comes from `router_page_labels` keyed by the page's default domain). It keeps
generic/unnamed-subject questions on the CURRENT page and escapes only when a
different subject is clearly named.

## Consequences
- The same question is answered per page: "who are the authors" -> NeuralOS on
  neural-os.com, the site on the personal site, the course on the course site.
- Routing is decided by what the message *names*, not by topic words.
- Trade-off: a generic question on a page whose answerer lacks the facts declines
  gracefully rather than escaping (accepted; declines beat wrong answers).
