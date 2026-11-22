"""Higher-level reads/writes: items with their latest check, link posts, open alert and drafts."""
import json

from . import db

DEFAULT_PROFILE = {"handle": None, "platform": "instagram", "niche": "", "followers": 0, "engagement": None}


def profile_get():
    row = db.one("SELECT handle, platform, niche, followers, engagement FROM profile WHERE id=1")
    return row or dict(DEFAULT_PROFILE)


def profile_put(p):
    db.run(
        "INSERT INTO profile(id, handle, platform, niche, followers, engagement, updated_at) VALUES(1,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET handle=excluded.handle, platform=excluded.platform, niche=excluded.niche, "
        "followers=excluded.followers, engagement=excluded.engagement, updated_at=excluded.updated_at",
        (p.get("handle"), p["platform"], p["niche"], p["followers"], p.get("engagement"), db.now()),
    )
    return profile_get()


def latest_check(item_id):
    row = db.one("SELECT result_json FROM checks WHERE item_id=? ORDER BY id DESC LIMIT 1", (item_id,))
    return json.loads(row["result_json"]) if row else None


def alert_dict(a, item):
    n = item["posts_count"]
    return {
        "id": a["id"], "item_id": a["item_id"], "verdict": a["verdict"],
        # a["headline"] holds the raw check headline; the user-facing pattern is built from the CURRENT post count
        "headline": f"You linked {item['name']} in {n} post{'' if n == 1 else 's'}. {a['headline']}",
        "follow_up": json.loads(a["follow_up_json"]) if a["follow_up_json"] else None,
        "follow_up_status": a["follow_up_status"], "created_at": a["created_at"], "handled_at": a["handled_at"],
    }


def draft_dict(d):
    content = json.loads(d["content_json"]) if d["content_json"] else {}
    return {"id": d["id"], "kind": d["kind"], "status": d["status"], "created_at": d["created_at"], **content}


def item_dict(item):
    iid = item["id"]
    alert = db.one("SELECT * FROM alerts WHERE item_id=? AND handled_at IS NULL ORDER BY id DESC LIMIT 1", (iid,))
    posts = db.all("SELECT id, label, url, posted_on, link_removed FROM link_posts WHERE item_id=? ORDER BY id", (iid,))
    for p in posts:
        p["link_removed"] = bool(p["link_removed"])
    return {
        "id": iid, "name": item["name"], "brand": item["brand"], "product": item["product"], "model": item["model"],
        "url": item["url"], "image_url": item["image_url"], "retailer": item["retailer"], "mode": item["mode"],
        "posts_count": item["posts_count"], "phase": item["phase"], "error": item["error"],
        "check": latest_check(iid), "link_posts": posts,
        "alert": alert_dict(alert, item) if alert else None,
        "drafts": [draft_dict(d) for d in db.all("SELECT * FROM drafts WHERE item_id=? ORDER BY id DESC", (iid,))],
    }


def get_item(item_id):
    row = db.one("SELECT * FROM items WHERE id=?", (item_id,))
    return item_dict(row) if row else None


def list_items():
    return [item_dict(r) for r in db.all("SELECT * FROM items ORDER BY id DESC")]


def create_item(f):
    """Dedupe by name+brand (case-insensitive): return the existing row instead of creating a duplicate."""
    existing = db.one(
        "SELECT id FROM items WHERE lower(name)=lower(?) AND lower(coalesce(brand,''))=lower(?)",
        (f["name"], f.get("brand") or ""),
    )
    if existing:
        return existing["id"], False
    iid = db.run(
        "INSERT INTO items(name, brand, url, image_url, retailer, mode, posts_count, phase, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,'queued',?,?)",
        (f["name"], f.get("brand"), f.get("url"), f.get("image_url"), f.get("retailer"), f.get("mode", "review"),
         f.get("posts_count", 0), db.now(), db.now()),
    )
    return iid, True
