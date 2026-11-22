"""Safety check pipeline: identify -> gather (parallel) -> synthesize -> validate -> compute verdict.

Safety properties (PRD section 12):
  * every citation is validated against the pool of URLs actually retrieved
  * the verdict is computed HERE from validated evidence; any verdict the model returns is ignored
  * if the official sources (CPSC database AND cpsc.gov search) are both unavailable, the result is
    'unverified', never 'no_issues_found'
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date

from . import config, cpsc, db, llm, youcom

# Inner pool: parallel source gathers within ONE check. Separate from the outer job pool (jobs.py) on purpose:
# running inner tasks on the outer pool could deadlock when all outer workers wait on inner tasks.
INNER = ThreadPoolExecutor(max_workers=config.INNER_WORKERS, thread_name_prefix="gather")

RANK = {"no_issues_found": 0, "unverified": 0, "caution": 1, "do_not_recommend": 2}
SOURCE_NAMES = {"cpsc": "CPSC recall database", "gov": "cpsc.gov search", "web": "web search", "research": "research"}


# ------------------------------------------------------------------ helpers
def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def cache_key(brand, product, model):
    return "check:" + "|".join(norm(x) for x in (brand, product, model))


def _slim(results, limit=10):
    seen, out = set(), []
    for r in results:
        u = r.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        hl = ((r.get("contents") or {}).get("highlights")) or r.get("snippets") or []
        out.append({"url": u, "title": r.get("title"), "description": (r.get("description") or "")[:300],
                    "highlights": [h[:400] for h in hl[:3]], "page_age": r.get("page_age")})
    return out[:limit]


def build_pool(*groups):
    seen, pool = set(), []
    for g in groups:
        for s in g:
            u = s.get("url")
            if u and u not in seen:
                seen.add(u)
                pool.append({"url": u, "title": s.get("title") or u})
    return pool


def _pool_prompt(pool):
    return "\n".join(f"[{i + 1}] {p['title']} - {p['url']}" for i, p in enumerate(pool))


def _src(idx, pool):
    try:
        i = int(idx) - 1
    except (TypeError, ValueError):
        return None
    return pool[i] if 0 <= i < len(pool) else None


def validate(data, pool):
    """Keep only evidence whose cited source number exists in the retrieved pool."""
    actions = []
    for a in data.get("official_actions") or []:
        s = _src(a.get("source"), pool)
        if s and a.get("type") in ("recall", "warning"):
            actions.append({
                "type": a["type"], "title": a.get("title", ""), "date": a.get("date"), "hazard": a.get("hazard", ""),
                "remedy": a.get("remedy"), "match": "confirmed" if a.get("match") == "confirmed" else "possible",
                "url": s["url"], "source_title": s["title"]})
    allegations = []
    for a in data.get("allegations") or []:
        s = _src(a.get("source"), pool)
        if s and a.get("text"):
            kind = a.get("kind") if a.get("kind") in ("lawsuit", "complaint", "report") else "report"
            allegations.append({"kind": kind, "text": a["text"], "url": s["url"], "source_title": s["title"]})
    return actions, allegations[:5]


def compute_verdict(actions, allegations, official_down):
    if any(a["match"] == "confirmed" for a in actions):
        return "do_not_recommend"
    if actions or allegations:
        return "caution"
    if official_down:
        return "unverified"  # never reassure when the official sources were unavailable
    return "no_issues_found"


# ------------------------------------------------------------------ stages
def identify(product):
    page = ""
    if product.get("url"):
        try:
            page = youcom.extract(product["url"], timeout=15)[:2500]
        except Exception:  # noqa: BLE001
            page = ""
    prompt = f"""A parenting creator links this product: name="{product['name']}" brand="{product.get('brand') or ''}" url={product.get('url') or 'none'}
PAGE TEXT (may be empty):
<retrieved_data>
{page or '(none)'}
</retrieved_data>

Return JSON: {{"brand": str, "product": str (product line, e.g. 'Convertible Bassinet'), "model": str or null,
"category": str (1-2 words, e.g. 'bassinet'), "cpsc_terms": [up to 3 short strings for searching a recall database by product name, most specific first]}}"""
    try:
        d = llm.claude_json(prompt, 600)
    except Exception:  # noqa: BLE001
        d = {}
    terms = [t.strip() for t in (d.get("cpsc_terms") or []) if isinstance(t, str) and t.strip()][:3]
    return {
        "brand": d.get("brand") or product.get("brand") or "",
        "product": d.get("product") or product["name"],
        "model": d.get("model"),
        "category": d.get("category") or "",
        "cpsc_terms": terms or [product["name"]],
    }


def run_check(product, force=False):
    """Returns (CheckResult dict, ident dict). Raises if every source failed or synthesis failed."""
    ident = identify(product)
    key = cache_key(ident["brand"], ident["product"], ident["model"])
    if not force:
        cached = db.cache_get(key, config.CHECK_CACHE_HOURS)
        if cached:
            return cached, ident

    who = f"{ident['brand']} {ident['product']}".strip()
    question = (
        f"Safety history of the {who}{' (model ' + ident['model'] + ')' if ident.get('model') else ''}: official recalls, "
        f"CPSC safety warnings, lawsuits, and recurring parent complaints about safety. Cite sources and clearly separate "
        f"confirmed official actions from allegations. Under 300 words."
    )
    futs = {
        "cpsc": INNER.submit(cpsc.search_recalls, ident["cpsc_terms"]),
        "gov": INNER.submit(youcom.search, f"{who} recall OR warning", 6, None, ["cpsc.gov"]),
        "web": INNER.submit(youcom.search, f"{who} lawsuit OR injury OR safety complaints parents", 8, "year"),
        "research": INNER.submit(youcom.research, question),
    }
    wait(list(futs.values()), timeout=config.T_CHECK - 20)
    out, gaps, failed = {}, [], set()
    for name, f in futs.items():
        if not f.done():
            gaps.append(f"{SOURCE_NAMES[name]} timed out")
            failed.add(name)
            continue
        try:
            out[name] = f.result()
        except Exception:  # noqa: BLE001
            gaps.append(f"{SOURCE_NAMES[name]} unavailable")
            failed.add(name)
    if len(failed) == 4:
        raise RuntimeError("All sources failed. " + "; ".join(gaps))

    records = out.get("cpsc") or []
    gov = out.get("gov") or []
    web = out.get("web") or []
    research_md, research_sources = out.get("research") or ("", [])
    official_down = "cpsc" in failed and "gov" in failed

    pool = build_pool(
        [{"url": r["url"], "title": f"CPSC recall {r['recall_number']}: {r['title']}"} for r in records if r.get("url")],
        [{"url": h["url"], "title": h.get("title")} for h in gov],
        research_sources,
        [{"url": h["url"], "title": h.get("title")} for h in web],
    )
    prompt = f"""Pre-post safety check for a parenting creator who earns affiliate commission on this product.
Product: {who}; model: {ident.get('model') or 'unknown'}; category: {ident['category']}. Today: {date.today().isoformat()}.

<retrieved_data>
OFFICIAL CPSC RECALL DATABASE RECORDS (may be empty or about other products):
{json.dumps(records[:10], indent=1)[:5000]}

CPSC.GOV SEARCH RESULTS (recalls and unilateral warnings):
{json.dumps(_slim(gov, 6), indent=1)[:3500]}

OTHER WEB RESULTS:
{json.dumps(_slim(web, 8), indent=1)[:3500]}

RESEARCH:
{research_md[:5000] or '(none)'}
</retrieved_data>

SOURCE POOL (cite by number):
{_pool_prompt(pool) or '(empty)'}

Rules:
- An official action (recall or CPSC warning) counts only if it plausibly concerns THIS brand and product line. match="confirmed" if brand and product type clearly match (and model, if known); otherwise "possible".
- Lawsuits, complaints and reports are ALLEGATIONS: label them as such, cite one source number each, never state them as fact.
- Never invent anything. If nothing relevant is found, return empty lists.
Return JSON:
{{"headline": str (max 18 words, plain and factual),
 "official_actions": [{{"type": "recall"|"warning", "title": str, "date": "YYYY-MM-DD" or null, "hazard": str, "remedy": str or null, "match": "confirmed"|"possible", "source": int}}],
 "allegations": [{{"kind": "lawsuit"|"complaint"|"report", "text": str, "source": int}}],
 "safety_note": str (3-4 plain sentences addressed to the creator),
 "what_to_do": [str] (2-4 short actions)}}"""
    data = llm.claude_json(prompt, 2000)
    actions, allegations = validate(data, pool)
    verdict = compute_verdict(actions, allegations, official_down)

    one_official_down = ("cpsc" in failed) != ("gov" in failed)
    if verdict == "no_issues_found" and one_official_down:
        which = SOURCE_NAMES["cpsc" if "cpsc" in failed else "gov"]
        gaps.append(f"Partial check: {which} was unavailable")
    headline = data.get("headline") or ""
    if verdict == "unverified":
        headline = "We couldn't reach the official recall sources, so this check is incomplete."
    result = {
        "verdict": verdict,
        "headline": headline,
        "safety_note": data.get("safety_note", ""),
        "what_to_do": [str(x) for x in (data.get("what_to_do") or [])][:4],
        "official_actions": actions,
        "allegations": allegations,
        "sources": pool[:10],
        "gaps": gaps,
        "checked_on": date.today().isoformat(),
    }
    if verdict != "unverified":  # never cache an incomplete check
        db.cache_set(key, result)
    return result, ident
