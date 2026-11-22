"""Demo mode: fixture-backed replacements for checks, follow-ups and search, so the UI behaves identically offline.

fixtures/checks/<name>.json    {"_recorded": bool, "_match": [tokens], "_ident": {...}, "result": CheckResult}
fixtures/followups/<name>.json {"_match": [tokens], "result": FollowUp}
fixtures/search/<slug>.json    {"results": [ProductResult...]}
`_recorded: true` is written by `python -m server.cli record ...` (a real live run). Hand-assembled fixtures keep
`_recorded: false` and the app shows "SAMPLE DATA" for them. Products with no fixture get a clearly fictional sample.
"""
import glob
import json
import os
import re
from datetime import date

from . import config


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _tokens(s):
    return set(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def _load_dir(sub):
    out = []
    for path in sorted(glob.glob(os.path.join(config.FIXTURES, sub, "*.json"))):
        try:
            with open(path) as f:
                out.append(json.load(f))
        except (OSError, ValueError):
            continue
    return out


def _match(sub, name):
    toks = _tokens(name)
    for fx in _load_dir(sub):
        need = set(fx.get("_match") or [])
        if need and need <= toks:
            return fx
    return None


def mode_label():
    return "demo-cached" if any(fx.get("_recorded") for fx in _load_dir("checks")) else "demo-sample"


def check(product):
    """Returns (CheckResult, ident) like checks.run_check."""
    fx = _match("checks", f"{product['name']} {product.get('brand') or ''}")
    if fx:
        res = dict(fx["result"])
        res["checked_on"] = date.today().isoformat()
        ident = fx.get("_ident") or {}
        return res, {"brand": ident.get("brand", ""), "product": ident.get("product", product["name"]), "model": ident.get("model")}
    res = {
        "verdict": "no_issues_found",
        "headline": "SAMPLE: no recalls or warnings found (fictional result, not a live check).",
        "safety_note": "This is sample data shown in demo mode. No live check was run for this product. "
                       "No recalls or warnings found is never a guarantee of safety.",
        "what_to_do": ["Run a live check before you post."],
        "official_actions": [], "allegations": [], "sources": [],
        "gaps": ["Demo mode: not a live check"], "checked_on": date.today().isoformat(),
    }
    return res, {"brand": product.get("brand") or "", "product": product["name"], "model": None}


def follow_up(item, check_result):
    fx = _match("followups", item["name"])
    if fx:
        return fx["result"]
    return {
        "post_caption": "SAMPLE follow-up draft (demo mode). In live mode this is written from the cited recall or warning, "
                        "says the affiliate link is being removed, and points followers to the official source.",
        "story_script": ["Sample line 1", "Sample line 2", "Sample line 3"],
        "comment_reply": "Sample reply to a worried follower.",
    }


def review_post(item, check_result, profile):
    return {"caption": "SAMPLE review post (demo mode). Live mode drafts this from the check result, with a safety line and a "
                       "disclosure line such as: Affiliate link, I may earn a commission. [what you liked]",
            "story_script": ["Sample line 1", "Sample line 2", "Sample line 3"]}


def sponsor_pitch(item, check_result, profile):
    return {"subject": "SAMPLE pitch subject", "partnership_page_url": None,
            "body": "Hi partnerships team,\n\nSAMPLE pitch (demo mode). Live mode drafts this from your profile, with no invented "
                    "names, emails or brand facts.\n\n[Your name]"}


def search(q):
    fx = os.path.join(config.FIXTURES, "search", f"{slug(q)}.json")
    if os.path.exists(fx):
        with open(fx) as f:
            return json.load(f)["results"], True
    results = []
    for i in range(1, 4):
        results.append({"id": f"sample{i}", "name": f"[Brand] [{q} model {i}]", "brand": "[Brand]", "retailer": "[Retailer]",
                        "price_text": None, "url": None, "image_url": None, "pre_flag": None})
    return results, False
