"""Generic, config-driven PAW pipeline executor (shared by server + eval).

Reads pipeline.yaml (the graph) and programs.json (compiled IDs) and runs:

    domain_router (page prior + PAW) -> <domain>.classifier
        -> link label  -> link / feedback result
        -> "question"  -> <domain>.answerer -> validator -> answer / fallback

Course answers inject facts at inference time via course_facts.retrieve (the same
seam a future Piazza RAG retriever plugs into). Resilience knobs (backtrack /
reconsider / multi) live in pipeline.yaml so the eval ablation runner picks them.

Keeping one executor for both the server and the benchmark means they can never
score differently from what ships.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

import yaml

from . import common, inference

log = logging.getLogger("paw_helper")


def _parse_index_list(raw: str, n: int) -> list[int]:
    """Parse a selector's output ("2, 1" or "none") into 0-based indices in [0, n),
    in the model's order, de-duplicated. Non-numeric output (e.g. "none") -> []."""
    out, seen = [], set()
    for tok in re.findall(r"\d+", raw or ""):
        i = int(tok) - 1
        if 0 <= i < n and i not in seen:
            seen.add(i)
            out.append(i)
    return out


_DECLINE_RE = re.compile(
    r"don'?t have|do not have|not sure|don'?t know|do not know|no information|"
    r"can'?t answer|cannot answer|couldn'?t find|could not find",
    re.IGNORECASE,
)


def _looks_like_decline(text: str) -> bool:
    """Heuristic: did an answerer effectively decline? Used so a branch's
    synthesized answer is only promoted when it actually answers."""
    return not text.strip() or bool(_DECLINE_RE.search(text))

# Conservative chars-per-token estimate used only to derive a safe input cap from
# the token budget. Intentionally on the high side so the cap stays comfortably
# under the real context window.
_CHARS_PER_TOKEN = 4


def load_config(path=None) -> dict:
    if path:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return common.load_config()


def _load_links(filename: str) -> dict:
    """label -> info dict, for a domain's links file in the content pack."""
    return common.load_links_file(filename)


def normalize_label(raw: str, valid: set[str]) -> str:
    """First token of the model output, mapped to a known label or 'question'.

    Unknown/malformed output -> 'question' (safer than a wrong link). Shared by
    every domain so the server and benchmark score identically.
    """
    s = raw.strip().lower().strip("\"'").strip(".")
    parts = s.split()
    s = parts[0] if parts else ""
    return s if (s in valid or s == "question") else "question"


def _is_decline(answer: str) -> bool:
    a = answer.lower()
    return (not answer.strip() or "don't have that" in a or "do not have that" in a
            or "i'm not sure" in a or "i don't know" in a)


class Pipeline:
    def __init__(
        self,
        programs: dict | None = None,
        config: dict | None = None,
        inference_backend: inference.InferenceBackend | None = None,
    ):
        self.cfg = config or load_config()
        if programs is not None:
            self.programs = programs
        elif inference.is_mock_mode():
            # Offline/demo mode (PAW_HELPER_INFERENCE_BACKEND=mock): no compiled
            # programs.json required. Synthesize identity IDs from the config's
            # program names so the pipeline boots AND the `available` filter below is
            # populated (it keys off names being in self.programs); the mock backend
            # ignores the IDs. This is what lets `init -> validate -> serve` answer
            # before the adopter has a PAW key or has run `compile`.
            from .validate import _program_names
            self.programs = {n: n for n in _program_names(self.cfg)}
        else:
            self.programs = common.load_programs()["programs"]
        self.mt = self.cfg["max_tokens"]
        self.resilience = self.cfg.get("resilience", {})
        # Content-pack providers (the only content-specific Python): how to render
        # the runtime-injected facts and resource lists this config refers to.
        prov = common.load_providers()
        self.context_providers = prov.CONTEXT_PROVIDERS
        self.context_labels = getattr(prov, "CONTEXT_LABELS", {})
        self.resource_providers = getattr(prov, "RESOURCE_PROVIDERS", {})
        # Parallel-branch search providers: name -> search(query) -> [{label,url,
        # description,score}]. An optional content-pack `aggregate(query, main,
        # branches)` overrides the built-in merge policy.
        self.search_providers = getattr(prov, "SEARCH_PROVIDERS", {})
        self._aggregate_fn = getattr(prov, "aggregate", None)
        self.links = {d: _load_links(spec["links"]) for d, spec in self.cfg["domains"].items()}
        # (domain, classifier label) -> resource-router config (e.g. course/slides).
        self.resource_routers = {(rr["domain"], rr["label"]): rr for rr in self.cfg.get("resource_routers", [])}
        # A domain is usable only if its classifier + answerer are compiled.
        self.available = [
            d for d, spec in self.cfg["domains"].items()
            if spec["classifier"] in self.programs and spec["answerer"] in self.programs
        ]
        self.inference_backend = inference_backend or inference.get_backend(self.programs)
        self.timings: list[tuple[str, float]] = []  # (node, seconds); eval reads/clears

    # --- inference ---------------------------------------------------------
    def _cap_input(self, name: str, text: str, max_tokens: int) -> str:
        """Cap the input so input+output fit the shared context window, reserving
        room for the output. Unlike a bare `text[:N]`, this is budget-derived and
        WARNS when it actually truncates, so an over-large injected facts slice (or
        a huge user query) is surfaced instead of silently losing its tail."""
        budget = self.cfg.get("token_budget", 2048)
        char_cap = max(0, (budget - int(max_tokens)) * _CHARS_PER_TOKEN)
        if len(text) > char_cap:
            log.warning(
                "paw_helper.input_truncated program=%s input_chars=%d cap_chars=%d "
                "(shrink the injected facts slice or raise token_budget)",
                name, len(text), char_cap,
            )
            return text[:char_cap]
        return text

    def _infer(self, name: str, text: str, max_tokens: int) -> str:
        """Error-swallowing inference. Returns "" on any backend failure."""
        t = time.time()
        try:
            out = self.inference_backend.infer(name, self._cap_input(name, text, max_tokens), max_tokens)
        except Exception:
            out = ""
        self.timings.append((name, time.time() - t))
        return out

    # --- routing -----------------------------------------------------------
    def resolve_domain(self, query: str, page: str) -> str:
        default = self.cfg["page_defaults"].get(page, self.cfg["default_domain"])
        if default not in self.available:
            default = self.cfg["default_domain"] if self.cfg["default_domain"] in self.available else (
                self.available[0] if self.available else self.cfg["default_domain"])
        router = self.cfg.get("domain_router")
        if router and router in self.programs and len(self.available) > 1:
            # Page-aware routing: the router sees WHICH page the visitor is on, so an
            # ambiguous/unnamed-subject question ("who are the authors") stays on the
            # current page, and the same question yields a page-appropriate answer
            # across sites. Only a clearly-named other subject escapes the page.
            label = self.cfg.get("router_page_labels", {}).get(default, default)
            router_input = f"Page: {label}\nMessage: {query}"
            r = normalize_label(self._infer(router, router_input, self.mt["router"]), set(self.available))
            if r in self.available:
                return r
        return default

    # --- node-level helpers (reused by the executor and the benchmark) -----
    def classify(self, domain: str, query: str) -> str:
        """Run a domain's classifier; returns a link label or 'question'."""
        spec = self.cfg["domains"][domain]
        raw = self._infer(spec["classifier"], query, self.mt["classifier"])
        return normalize_label(raw, set(self.links[domain]))

    def _inject(self, provider: str, query: str) -> str:
        """Build a facts-injected answerer input under the provider's header label."""
        ctx = self.context_providers[provider](query)
        return f"{self.context_labels.get(provider, 'Facts')}:\n{ctx}\n\nQuestion: {query}"

    def _answer_input(self, spec: dict, query: str) -> str:
        """Flat-domain answerer input: bare query (baked) or facts+question (runtime)."""
        if spec.get("facts_mode") == "runtime":
            return self._inject(spec["context"], query)
        return query

    def freeform(self, domain: str, query: str) -> tuple[str, str]:
        """Run a domain's answerer + validator; returns (answer, verdict).

        If the domain has a topic_router, route to a specialized sub-answerer with
        detailed injected facts (single-best). If the sub-answerer declines or is
        empty, BACKTRACK to the flat answerer (redundancy). The validator gates.
        """
        spec = self.cfg["domains"][domain]
        flat = spec["answerer"]
        answerer_name, sub_provider = flat, None

        tr = spec.get("topic_router")
        if tr and tr in self.programs:
            # Take the first token and strip surrounding quotes/punctuation. Small
            # compilers (esp. the fast compiler) often emit `"install"` / `compile.`;
            # without this the topic never matches and EVERY question silently falls
            # back to the flat answerer, defeating the hierarchy.
            raw = self._infer(tr, query, self.mt["router"]).strip().lower().split()
            topic = raw[0].strip("\"'.") if raw else ""
            sub = spec.get("topics", {}).get(topic)
            if isinstance(sub, dict) and sub.get("answerer") in self.programs:
                answerer_name, sub_provider = sub["answerer"], sub.get("context")

        inp = self._inject(sub_provider, query) if sub_provider else self._answer_input(spec, query)
        answer = self._infer(answerer_name, inp, self.mt["answerer"])

        # Backtrack to the flat answerer only if the sub-answerer produced nothing.
        # We deliberately do NOT backtrack on a decline: the sub-answerer has the
        # detailed facts, so its honest "I don't have that detail" is better than
        # the flat answerer's tendency to hallucinate on out-of-facts questions.
        if answerer_name != flat and len(answer) < 2:
            answer = self._infer(flat, self._answer_input(spec, query), self.mt["answerer"])

        verdict = ""
        if len(answer) >= 2:
            verdict = self._infer(self.cfg["validator"], f"Q: {query} A: {answer}", self.mt["validator"]).lower()
        return answer, verdict

    @staticmethod
    def _resource_item_view(it: dict, rr: dict) -> dict:
        """Render one resource item for the result. A provider may supply its own
        `label`/`description` (generic case, e.g. code repos); otherwise fall back
        to the legacy slide shape (`num`/`topic` -> "L{num}: {topic}")."""
        label = it.get("label") or f"L{it['num']}: {it['topic']}"
        return {"label": label, "url": it["url"],
                "description": it.get("description") or rr.get("item_description", "")}

    def resource_items(self, rr: dict, query: str) -> list[dict]:
        """Rule+fuzzy resource lookup: inject candidate list, run the fuzzy selector,
        let the provider turn its output into items."""
        render, select = self.resource_providers[rr["provider"]]
        candidates = render()
        raw = self._infer(rr["program"], f"{rr.get('candidate_label', 'Items')}:\n{candidates}\n\nRequest: {query}",
                          self.mt.get("selector", 16))
        return select(raw)[: rr.get("max_items", 4)]

    def _apply_redundancy(self, domain: str, query: str, label: str) -> str:
        """Optional, config-declared classifier safety net. If the classifier picks
        a `from` label but the query clearly signals a stronger `to` label (keyword
        evidence), prefer `to`. This is deterministic redundancy for clusters the
        small classifier is shaky on (e.g. bare "python sdk" -> code), NOT a
        replacement for the model. Each rule:
            {to, from: [...], any_keywords: [...], unless_keywords: [...]}
        """
        q = query.lower()
        for r in self.cfg["domains"][domain].get("classifier_redundancy", []):
            if label not in r.get("from", []):
                continue
            if any(k in q for k in r.get("unless_keywords", [])):
                continue
            if any(k in q for k in r.get("any_keywords", [])):
                return r["to"]
        return label

    # --- per-domain classify -> resource | link | answer -> validate -------
    def _run_domain(self, domain: str, query: str) -> dict:
        links = self.links[domain]
        label = self._apply_redundancy(domain, query, self.classify(domain, query))

        # Hierarchical resource router (e.g. course/slides -> specific decks).
        rr = self.resource_routers.get((domain, label))
        if rr and rr["program"] in self.programs:
            items = self.resource_items(rr, query)
            if items:
                res = {"type": "links", "label": rr.get("result_label", "Links"),
                       "items": [self._resource_item_view(it, rr) for it in items]}
                return {"result": res, "domain": domain, "route": label, "verdict": None}
            # No match -> fall through to the plain link (fallback, e.g. the schedule).

        if label != "question" and label in links:
            info = links[label]
            if info.get("kind") == "feedback":
                res = {"type": "feedback", "label": info["label"], "description": info.get("description", "")}
            else:
                res = {"type": "link", "label": info["label"], "url": info["url"],
                       "description": info.get("description", "")}
            return {"result": res, "domain": domain, "route": label, "verdict": None}

        # Freeform answer path.
        answer, verdict = self.freeform(domain, query)
        if len(answer) < 2:
            res = {"type": "none"}
        elif not self.resilience.get("backtrack", True):
            res = {"type": "answer", "text": answer}
        else:
            res = {"type": "answer", "text": answer} if verdict.startswith("yes") else {"type": "none"}
        return {"result": res, "domain": domain, "route": "question", "verdict": verdict or None}

    # --- parallel branches (multi-path: a side branch that augments the main) ---
    def _branches(self, page: str) -> list[dict]:
        """Enabled parallel branches for this request, keyed off the PAGE's home
        domain (so a branch fires by ORIGIN, e.g. only on the course page) and only
        when its gate program + search provider are actually available."""
        page_domain = self.cfg["page_defaults"].get(page, self.cfg["default_domain"])
        out = []
        for b in self.cfg["domains"].get(page_domain, {}).get("parallel_branches", []):
            wp = b.get("when_page")
            if wp and not (page == wp or page.startswith(wp)):
                continue
            if b.get("provider") not in self.search_providers:
                continue
            if b.get("gate") and b["gate"] not in self.programs:
                continue
            out.append(b)
        return out

    def _run_branch(self, branch: dict, query: str) -> dict | None:
        """gate? (cheap yes/no early-exit) -> provider.search (RECALL) -> selector?
        (a PAW reranker that keeps only genuinely relevant candidates) -> answerer?
        (a PAW program that SYNTHESIZES a grounded answer from the kept items'
        `context`, e.g. the endorsed instructor reply). Items the provider marks
        `keep` bypass the reranker (already qualified, e.g. a recency list). Search
        recalls, the PAW stages decide relevance + compose the answer, so the merge
        is robust to retriever false positives. Returns {name, label, items,
        answer?} or None (skip)."""
        gate = branch.get("gate")
        if gate:
            verdict = self._infer(gate, query, self.mt.get("gate", self.mt.get("classifier", 8)))
            if not verdict.strip().lower().startswith("yes"):
                return None
        try:
            items = self.search_providers[branch["provider"]](query) or []
        except Exception:
            return None
        # Recall floor only: drop pure-noise candidates, then keep the top select_k
        # for the precision stage. With a selector this stays LOW (the retriever just
        # needs recall); without one it is the sole precision gate (a hard threshold).
        items = [it for it in items if it.get("score", 0) >= branch.get("min_score", 0)]
        items = items[: branch.get("select_k", branch.get("max_items", 3))]
        if not items:
            return None
        # Provider-prequalified items (keep=True, e.g. a recency list) bypass the
        # reranker; the rest go through the selector for precision.
        kept = [it for it in items if it.get("keep")]
        to_rank = [it for it in items if not it.get("keep")]
        selector = branch.get("selector")
        if selector and selector in self.programs and to_rank:
            to_rank = self._select_candidates(selector, query, to_rank)
        items = (kept + to_rank)[: branch.get("max_items", 3)]
        if not items:
            return None
        out = {"name": branch["name"], "label": branch.get("result_label", "Related"),
               "merge": branch.get("merge"),  # optional merge-judge program (decides main/branch/augment)
               "items": [{"label": it["label"], "url": it["url"], "description": it.get("description", "")}
                         for it in items]}
        answerer = branch.get("answerer")
        if answerer and answerer in self.programs:
            answer = self._answer_branch(answerer, query, items).strip()
            if answer and not _looks_like_decline(answer):
                out["answer"] = answer
            else:
                # The answerer is the grounding judge: if it cannot answer from the
                # kept threads (declines), those threads do NOT address the question,
                # so the branch contributes NOTHING - not even a citation. (Citing a
                # source you couldn't answer from is the core RAG faithfulness bug,
                # e.g. surfacing the Assignment 2 post for "is assignment 3 released".)
                return None
        return out

    def _answer_branch(self, program: str, query: str, items: list[dict]) -> str:
        """Synthesize a concise answer from the kept items' `context` (e.g. the
        endorsed instructor reply). Grounded RAG: the answerer sees ONLY these
        threads, so it answers from them or declines."""
        ctx = "\n\n".join(
            f"[{i + 1}] {it.get('label', '')}\n{it.get('context') or it.get('description', '')}"
            for i, it in enumerate(items))
        return self._infer(program, f"Question: {query}\n\nPiazza threads:\n{ctx}",
                           self.mt.get("answerer", 200))

    def _select_candidates(self, program: str, query: str, items: list[dict]) -> list[dict]:
        """Question-aware precision rerank. Shows the selector the ORIGINAL question
        and the numbered candidate labels; it returns the numbers that genuinely
        answer the question (most relevant first) or "none". Robust to retriever
        false positives because the model sees the question, not just a score."""
        lines = "\n".join(f"{i + 1}. {it['label']}" for i, it in enumerate(items))
        raw = self._infer(program, f"Question: {query}\n\nThreads:\n{lines}",
                          self.mt.get("selector", 16))
        return [items[i] for i in _parse_index_list(raw, len(items))]

    def _aggregate(self, query: str, main_out: dict, branch_results: list[dict]) -> dict:
        """Merge branch results into the main result. When a branch synthesized an
        answer AND declares a `merge` program, a QUESTION-AWARE judge decides, from
        the question + the main answer + the branch answer, whether to keep `main`,
        promote the branch (`branch`), or `augment` (main answer + branch citation).
        This is more robust than a blanket promote: it has both answers in hand.
        Without a merge program it falls back to promote-on-answer. Other policy:
        nothing relevant -> main unchanged; main declined -> branch links rescue it;
        branch links but no answer -> augment. `out["merge"]` records the decision
        (main | piazza | augment) so the outcome benchmark can grade it. A content
        pack may export `aggregate(query, main, branches)` to override."""
        if not branch_results:
            main_out["merge"] = "main"
            return main_out
        if self._aggregate_fn:
            return self._aggregate_fn(query, main_out, branch_results)
        items, label, answer, merge_prog = [], None, None, None
        for br in branch_results:
            items += br["items"]
            label = label or br.get("label")
            if br.get("answer") and not answer:
                answer = br["answer"]
            merge_prog = merge_prog or br.get("merge")
        res = main_out["result"]

        if answer:
            decision = "branch"
            if merge_prog and merge_prog in self.programs:
                main_text = res.get("text") or res.get("label") or ""
                decision = self._merge(merge_prog, query, main_text, answer, items)
            if decision == "main":
                main_out["merge"] = "main"
                return main_out  # branch discarded; the course's own answer stands
            if decision == "augment" and res.get("type") not in (None, "none"):
                res["related"] = items
                res["related_label"] = label or "Related"
                main_out["merge"] = "augment"
            else:  # promote the branch answer to primary, with citations
                main_out["result"] = {"type": "answer", "text": answer,
                                      "related": items, "related_label": label or "Related"}
                main_out["merge"] = "piazza"
        elif res.get("type") == "none":
            main_out["result"] = {"type": "links", "label": label or "Related", "items": items}
            main_out["merge"] = "piazza"
        else:
            res["related"] = items
            res["related_label"] = label or "Related"
            main_out["merge"] = "augment"
        main_out["branches"] = [br["name"] for br in branch_results]
        return main_out

    def _merge(self, program: str, query: str, main_text: str, branch_answer: str,
               items: list[dict]) -> str:
        """Question-aware merge judge: given the question, the main answer, and the
        branch answer (+ source titles), return 'main' | 'augment' | 'branch'.
        Defaults to 'branch' when the output is unclear (back-compat with promote)."""
        titles = "; ".join(it.get("label", "") for it in items)
        prompt = (f"Question: {query}\n\n"
                  f"Course answer: {main_text or '(none)'}\n\n"
                  f"Piazza answer: {branch_answer}\n"
                  f"Piazza source(s): {titles}")
        out = self._infer(program, prompt,
                          self.mt.get("merge", self.mt.get("classifier", 8))).strip().lower()
        if out.startswith("main"):
            return "main"
        if out.startswith("augment"):
            return "augment"
        return "branch"

    # --- public API --------------------------------------------------------
    def _main(self, query: str, page: str) -> dict:
        return self._run_domain(self.resolve_domain(query, page), query)

    def run(self, query: str, page: str = "site") -> dict:
        """Full result with meta: {result, domain, route, verdict}.

        On a page with parallel branches (e.g. the course page's Piazza branch),
        the main pipeline and each branch run CONCURRENTLY (cheap on the remote
        backend), then the aggregator merges the branch results into the main one.
        """
        q = (query or "").strip()
        if len(q) < 3:
            return {"result": {"type": "none"}, "domain": None, "route": None, "verdict": None}

        branches = self._branches(page)
        if branches:
            with ThreadPoolExecutor(max_workers=1 + len(branches)) as ex:
                main_fut = ex.submit(self._main, q, page)
                branch_futs = [ex.submit(self._run_branch, b, q) for b in branches]
                out = main_fut.result()
                results = [bf.result() for bf in branch_futs]
            out = self._aggregate(q, out, [r for r in results if r])
        else:
            out = self._main(q, page)
        out.setdefault("merge", "main")  # outcome: which source the result came from

        domain = out.get("domain")
        # Reconsider: if the routed domain declined (and no branch rescued it), try
        # the page-default domain once.
        if out["result"].get("type") == "none" and self.resilience.get("reconsider"):
            default = self.cfg["page_defaults"].get(page, self.cfg["default_domain"])
            if default in self.available and default != domain:
                alt = self._run_domain(default, q)
                if alt["result"].get("type") != "none":
                    alt["reconsidered_from"] = domain
                    out = alt
        return out
