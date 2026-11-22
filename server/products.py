"""Product search for the registry-style Add flow. Runs on submit, cached 1 h. `pre_flag` is a P1 feature (left None)."""
import hashlib
import re
from urllib.parse import urlparse

from . import checks, config, db, demo, youcom

BOOST = ["amazon.com", "target.com", "walmart.com", "babylist.com"]


def _pid(name, brand, url):
    raw = f"{checks.norm(name)}|{checks.norm(brand)}|{url or ''}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _retailer(url):
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return host or None


def _clean_title(t):
    t = re.sub(r"\s*[|\-:]\s*(Amazon|Target|Walmart|Babylist|Buy Buy Baby)[^|]*$", "", t or "", flags=re.I)
    return t.strip()[:140]


def search(q):
    """Returns (results, live). Demo mode serves fixtures or clearly bracketed sample rows."""
    if config.demo_active():
        results, _ = demo.search(q)
        return results[:6], False
    key = "search:" + checks.norm(q)
    cached = db.cache_get(key, config.SEARCH_CACHE_HOURS)
    if cached is not None:
        return cached, True
    hits = youcom.search(f"{q} {config.PRODUCT_SEARCH_SUFFIX}", count=10, boost_domains=BOOST)
    out, seen = [], set()
    for h in hits:
        url = h.get("url")
        name = _clean_title(h.get("title"))
        if not url or not name or url in seen:
            continue
        seen.add(url)
        out.append({"id": _pid(name, "", url), "name": name, "brand": "", "retailer": _retailer(url), "price_text": None,
                    "url": url, "image_url": h.get("thumbnail_url"), "pre_flag": None})
        if len(out) == 6:
            break
    db.cache_set(key, out)
    return out, True
