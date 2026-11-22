"""You.com Search / Extract / Research (sync). Endpoint shapes VERIFIED from You.com's published OpenAPI specs,
but not yet called live from the build sandbox: run the M0 smoke test first."""
import requests

from . import config

SEARCH_URL = "https://ydc-index.io/v1/search"
EXTRACT_URL = "https://ydc-index.io/v1/extract"
RESEARCH_URL = "https://api.you.com/v1/research"


def _headers():
    return {"X-API-Key": config.ydc_key(), "Content-Type": "application/json"}


def search(query, count=8, freshness=None, include_domains=None, boost_domains=None, timeout=None):
    body = {"query": query, "count": count, "extraction": {"extraction_mode": "highlights"}}
    if freshness:
        body["freshness"] = freshness
    if include_domains:
        body["include_domains"] = include_domains
    elif boost_domains:  # include and boost cannot be combined
        body["boost_domains"] = boost_domains
    r = requests.post(SEARCH_URL, headers=_headers(), json=body, timeout=timeout or config.T_SEARCH)
    r.raise_for_status()
    return (r.json().get("results") or {}).get("web") or []


def extract(url, timeout=20):
    body = {"url": url, "full_page": {"extraction_formats": ["markdown"]}, "timeout": timeout}
    r = requests.post(EXTRACT_URL, headers=_headers(), json=body, timeout=timeout + 15)
    r.raise_for_status()
    full = ((r.json().get("contents") or {}).get("full_page")) or {}
    return full.get("markdown") or ""


def research(question, effort=None, timeout=None):
    body = {"input": question, "research_effort": effort or config.RESEARCH_EFFORT}
    r = requests.post(RESEARCH_URL, headers=_headers(), json=body, timeout=timeout or config.T_RESEARCH)
    r.raise_for_status()
    out = r.json().get("output") or {}
    return out.get("content") or "", out.get("sources") or []
