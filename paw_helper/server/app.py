"""FastAPI inference service for the yuntiandeng.com "Ask about Yuntian" helper.

Runs the 3-program PAW pipeline server-side and exposes a single high-level
/ask endpoint to the browser widget, plus /feedback and /health.

Pipeline:
  1. page_classifier(query) -> a link label (from links.yaml) or "question"
  2. if a link label   -> return a link result (feedback label opens the form)
  3. if "question"     -> answerer(query) -> validator("Q: .. A: ..")
                          -> yes: return the answer; no/empty: fallback

All PAW inference runs locally via the SDK. Inference is serialized with a lock
(one shared model instance; low-traffic personal site).

Env:
  HELPER_ALLOWED_ORIGINS  comma-separated CORS origins
                          (default: https://yuntiandeng.com,https://www.yuntiandeng.com)
  HELPER_FEEDBACK_LOG     path to append feedback JSONL
                          (default: <helper>/feedback.jsonl)
  HELPER_QUERY_LOG        path to append per-question JSONL for review
                          (default: <helper>/queries.jsonl)
"""

import datetime
import json
import os
import pathlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import common, pipeline

# Content pack dir comes from PAW_HELPER_CONTENT (common resolves it). Single shared
# executor (one model instance; inference is serialized inside it).
PIPE = pipeline.Pipeline()
PROGRAMS = PIPE.programs


app = FastAPI(title="paw-helper", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.environ.get(
            "HELPER_ALLOWED_ORIGINS",
            "https://yuntiandeng.com,https://www.yuntiandeng.com",
        ).split(",")
        if o.strip()
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

QUERY_LOG = os.environ.get("HELPER_QUERY_LOG", str(common.CONTENT_DIR / "queries.jsonl"))


@app.get("/widget.js")
def widget_js() -> FileResponse:
    # Public, embeddable JS: a <script src> load is not CORS-gated, but we mark it
    # Access-Control-Allow-Origin:* so any site can also fetch/inspect it. The
    # data endpoints (/ask,/feedback,/health) stay restricted to the allow-list.
    # A content pack may ship its own widget.js (its own labels/email/presets); if
    # present it overrides the packaged default.
    override = common.CONTENT_DIR / "widget.js"
    path = override if override.exists() else (STATIC_DIR / "widget.js")
    return FileResponse(
        path,
        media_type="application/javascript",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=300",
        },
    )


def _log_query(query: str, page: str, meta: dict, origin: str | None = None) -> None:
    """Append one JSONL line per question so we can review and polish on real usage.

    Deliberately stores no IP/identifier (public site, minimize PII). The query
    text is logged because that is the whole point of the review loop; keep the
    file private on the server. Never raises.

    `origin` is the HTTP Origin header (the embedding site, e.g. https://neural-os.com).
    Now that one backend serves multiple sites, this is the authoritative source
    of where a question came from - the `page` key is client-supplied - so we can
    later improve each site's helper from its own real traffic.
    """
    result = meta.get("result", {})
    rtype = result.get("type")
    record = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "query": query,
        "page": page,                                    # client-supplied page key (data-page)
        "origin": origin,                                # HTTP Origin: which site embedded the widget
        "domain": meta.get("domain"),                    # site / course (after routing)
        "route": meta.get("route"),                      # classifier label or "question"
        "result_type": rtype,                            # link / answer / feedback / none
        "answer": result.get("text") or result.get("label"),
        "validator": meta.get("verdict"),                # yes/no for the freeform path
        "fallback": rtype == "none",                     # the polish targets
    }
    try:
        with open(QUERY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    # Page key the widget sends so the router can apply a page prior. Defaults to
    # the personal site when absent (backward compatible).
    page: str = Field("site", max_length=100)


@app.post("/ask")
def ask(req: AskRequest, request: Request) -> dict:
    query = req.query.strip()
    if len(query) < 3:
        return {"type": "none"}
    meta = PIPE.run(query, page=req.page or "site")
    _log_query(query, req.page or "site", meta, origin=request.headers.get("origin"))
    return meta["result"]


class FeedbackRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    email: str | None = Field(None, max_length=200)
    page_url: str | None = Field(None, max_length=500)


@app.post("/feedback")
def feedback(req: FeedbackRequest, request: Request) -> dict:
    log_path = os.environ.get(
        "HELPER_FEEDBACK_LOG", str(common.CONTENT_DIR / "feedback.jsonl")
    )
    fwd = request.headers.get("X-Forwarded-For")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    record = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "text": req.text,
        "email": req.email,
        "page_url": req.page_url,                         # full URL from the widget (location.href)
        "origin": request.headers.get("origin"),         # which site the feedback came from
        "ip": ip,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Never fail the request because logging failed.
        pass
    return {"message": "Thank you for your feedback!"}


@app.get("/health")
def health() -> dict:
    # n_serving = programs that actually run when serving (exclude offline tools
    # like the benchmark rubric grader); the widget shows this count.
    tools = set(PIPE.cfg.get("tools", []))
    n_serving = sum(1 for name in PROGRAMS if name not in tools)
    return {"status": "ok", "programs": PROGRAMS, "n_serving": n_serving}
