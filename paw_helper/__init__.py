"""paw-helper: a small, reusable "ask about this site" helper backend.

A pipeline of ProgramAsWeights (PAW) programs (a page-aware domain router, per-domain
classifiers, answerers with runtime-injected facts, and a validator). Point it at a
content pack (config + specs + facts + links + data + providers.py) and serve, so one
backend can answer about your site, and an embeddable widget.js drops onto any page.

See README.md for the quickstart and docs/ for the design.
"""

__version__ = "0.1.1"

from .common import set_content_dir  # noqa: E402
from .pipeline import Pipeline  # noqa: E402

__all__ = ["Pipeline", "set_content_dir", "__version__"]
