"""Example content pack providers.

This minimal pack uses a baked answerer (facts compiled in via {{FACTS}}), so it
registers no runtime providers. To inject volatile facts at inference time (course
deadlines, a roster, retrieved documents - the RAG seam), set a domain's
`facts_mode: runtime` and `context: <key>` in config.yaml, then register that key:

    CONTEXT_PROVIDERS = {"news": lambda query: latest_news_text()}
    CONTEXT_LABELS = {"news": "News"}

A resource router (rule-based candidate list + a fuzzy PAW selector) registers:

    RESOURCE_PROVIDERS = {"docs": (render_candidates, select_from_selector_output)}
"""

CONTEXT_PROVIDERS = {}
CONTEXT_LABELS = {}
RESOURCE_PROVIDERS = {}
