# ADR 0001: One shared backend + CORS, not a backend per site

Status: accepted

## Context
The helper should run on several of Yuntian's sites (yuntiandeng.com,
neural-os.com, programasweights.com). Each runs different software (Jekyll, a
proxied Gradio app, a static site).

## Decision
Run ONE backend (helper.yuntiandeng.com) that serves a self-contained
`widget.js`. Each site embeds the script and is added to `HELPER_ALLOWED_ORIGINS`;
the browser talks to the backend cross-origin. `/widget.js` is public; `/ask`,
`/feedback`, `/health` are restricted to the allow-list.

## Consequences
- One model instance / one place to deploy and review logs across sites.
- The widget must be framework-agnostic (Shadow DOM, CSS-var theming with
  fallbacks) and embeddable even on apps whose HTML we don't control (nginx
  `sub_filter`).
- Others (the open-source case) run their OWN backend with their own content pack.
