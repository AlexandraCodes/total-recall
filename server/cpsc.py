"""CPSC recall database lookups through the public SaferProducts web service."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

from . import config

CPSC_URL = "https://www.saferproducts.gov/RestWebServices/Recall"
USER_AGENT = "RecallWatch/1.0"


def _names(items, key="Name"):
    out = []
    for i in items or []:
        v = i.get(key) if isinstance(i, dict) else None
        if v and v not in out:
            out.append(v)
    return out


def normalize(r: dict) -> dict:
    products = r.get("Products") or []
    return {
        "recall_number": r.get("RecallNumber"),
        "date": (r.get("RecallDate") or "")[:10],
        "title": r.get("Title"),
        "url": r.get("URL"),
        "description": (r.get("Description") or "")[:600],
        "products": _names(products)[:5],
        "models": _names(products, "Model")[:5],
        "units": _names(products, "NumberOfUnits")[:2],
        "hazards": _names(r.get("Hazards"))[:3],
        "remedies": _names(r.get("Remedies"))[:3],
        "manufacturers": _names(r.get("Manufacturers"))[:3],
        "retailers": _names(r.get("Retailers"))[:4],
    }


def _get(params):
    resp = requests.get(
        CPSC_URL,
        params={**params, "format": "json"},
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=config.T_CPSC,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def search_recalls(terms, since_days=None, cap=15):
    """Search by ProductName per term; deduped, newest first. Raises only if every request failed."""
    base = {}
    if since_days:
        base["RecallDateStart"] = (date.today() - timedelta(days=since_days)).isoformat()

    def one(t):
        try:
            return _get({**base, "ProductName": t})
        except Exception as e:  # noqa: BLE001
            return e

    with ThreadPoolExecutor(max_workers=max(1, len(terms))) as ex:
        results = list(ex.map(one, terms))
    ok = [r for r in results if not isinstance(r, Exception)]
    if not ok:
        raise results[0]
    seen, out = set(), []
    for batch in ok:
        for r in batch:
            key = r.get("RecallNumber") or r.get("RecallID")
            if key in seen:
                continue
            seen.add(key)
            out.append(normalize(r))
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:cap]
