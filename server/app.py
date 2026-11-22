"""Flask app: JSON API under /api, React build served for everything else."""
import logging
import os
import threading
import time
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import config, db, demo, jobs, products, store

log = logging.getLogger("recallwatch")

MAX_ITEMS = 25
KINDS = ("review_post", "sponsor_pitch")
MODES = ("review", "sponsored")


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def _err(status, code, message):
    return jsonify({"error": {"code": code, "message": message}}), status


# ------------------------------------------------------------------ validation
def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Expected a JSON object body.")
    return data


def _text(data, key, lo=0, hi=200, required=False):
    v = data.get(key)
    if v is None or v == "":
        if required:
            raise ApiError(400, "validation", f"'{key}' is required.")
        return None
    if not isinstance(v, str):
        raise ApiError(400, "validation", f"'{key}' must be a string.")
    v = v.strip()
    if not (lo <= len(v) <= hi):
        raise ApiError(400, "validation", f"'{key}' must be {lo} to {hi} characters.")
    return v


def _url(data, key):
    v = _text(data, key, 0, 2000)
    if v is None:
        return None
    p = urlparse(v)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ApiError(400, "validation", f"'{key}' must be an http(s) URL.")
    return v


def _int(data, key, lo, hi):
    v = data.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        raise ApiError(400, "validation", f"'{key}' must be an integer from {lo} to {hi}.")
    return v


def _mode(data):
    m = data.get("mode", "review")
    if m not in MODES:
        raise ApiError(400, "validation", "'mode' must be 'review' or 'sponsored'.")
    return m


# ------------------------------------------------------------------ rate limit (per IP, in memory)
_hits, _lock = {}, threading.Lock()


def _limited(ip, limit=120, window=60):
    now = time.time()
    with _lock:
        q = [t for t in _hits.get(ip, []) if now - t < window]
        q.append(now)
        _hits[ip] = q
        return len(q) > limit


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    logging.basicConfig(level=logging.INFO)
    db.init()

    @app.before_request
    def guard():
        if request.path.startswith("/api/") and request.method != "GET":
            if _limited(request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()):
                raise ApiError(429, "rate_limited", "Too many requests. Slow down a little.")

    @app.errorhandler(ApiError)
    def on_api_error(e):
        return _err(e.status, e.code, e.message)

    @app.errorhandler(HTTPException)
    def on_http(e):
        return _err(e.code or 500, (e.name or "error").lower().replace(" ", "_"), e.description or e.name)

    @app.errorhandler(Exception)
    def on_exc(e):
        log.exception("unhandled")
        return _err(500, "internal", "Something went wrong on our side.")

    # -------------------------------------------------------------- health / demo
    def health():
        demo_on = config.demo_active()
        return {"live_ready": config.keys_ready(), "model": config.CLAUDE_MODEL,
                "mode": demo.mode_label() if demo_on else "live", "cpsc_index_size": 0}

    @app.get("/api/health")
    def api_health():
        return jsonify(health())

    def _need_demo():
        if not config.ENABLE_DEMO:
            raise ApiError(404, "demo_disabled", "Demo controls are disabled.")

    @app.post("/api/demo/mode")
    def demo_mode():
        _need_demo()
        on = _body().get("on")
        if on is not None and not isinstance(on, bool):
            raise ApiError(400, "validation", "'on' must be true, false or null.")
        config.set_demo(on)
        return jsonify(health())

    @app.post("/api/demo/reset")
    def demo_reset():
        _need_demo()
        with db.conn() as c:
            for t in ("alerts", "drafts", "link_posts", "checks", "items", "cache", "profile"):
                c.execute(f"DELETE FROM {t}")
        return jsonify({"ok": True})

    @app.post("/api/demo/seed")
    def demo_seed():
        _need_demo()
        seeds = [("AirClub Convertible Bassinet", "AirClub", 4, ["Nursery tour reel", "Newborn essentials carousel"]),
                 ("CooCooBaby Baby Lounger", "CooCooBaby", 2, []),
                 (config.DEMO_CLEAN_PRODUCT, "", 3, [])]
        out = []
        for name, brand, posts, labels in seeds:
            iid, created = store.create_item({"name": name, "brand": brand, "posts_count": posts})
            if created:
                for lbl in labels:
                    db.run("INSERT INTO link_posts(item_id, label) VALUES(?,?)", (iid, lbl))
                jobs.enqueue_check(iid)
            out.append(iid)
        return jsonify([store.get_item(i) for i in out])

    # -------------------------------------------------------------- profile
    @app.get("/api/profile")
    def profile_get():
        return jsonify(store.profile_get())

    @app.put("/api/profile")
    def profile_put():
        d = _body()
        eng = d.get("engagement")
        if eng is not None and (isinstance(eng, bool) or not isinstance(eng, (int, float)) or not (0 <= eng <= 100)):
            raise ApiError(400, "validation", "'engagement' must be a number from 0 to 100.")
        p = {"handle": _text(d, "handle", 0, 60), "platform": _text(d, "platform", 2, 30, True),
             "niche": _text(d, "niche", 0, 120) or "", "followers": _int(d, "followers", 0, 500_000_000), "engagement": eng}
        return jsonify(store.profile_put(p))

    # -------------------------------------------------------------- search
    @app.post("/api/products/search")
    def product_search():
        q = _text(_body(), "q", 2, 200, True)
        try:
            results, live = products.search(q)
        except Exception:  # noqa: BLE001
            log.exception("search failed")
            raise ApiError(502, "search_failed", "Search is unavailable. You can still add the product as typed.")
        return jsonify({"mode": "live" if live else ("demo-cached" if demo.mode_label() == "demo-cached" else "demo-sample"),
                        "results": results})

    # -------------------------------------------------------------- items
    def _item_or_404(item_id):
        it = db.one("SELECT * FROM items WHERE id=?", (item_id,))
        if not it:
            raise ApiError(404, "not_found", "Item not found.")
        return it

    @app.get("/api/items")
    def items_list():
        return jsonify(store.list_items())

    @app.post("/api/items")
    def items_create():
        d = _body()
        f = {"name": _text(d, "name", 2, 140, True), "brand": _text(d, "brand", 0, 80), "url": _url(d, "url"),
             "image_url": _url(d, "image_url"), "retailer": _text(d, "retailer", 0, 80), "mode": _mode(d)}
        if db.one("SELECT COUNT(*) n FROM items")["n"] >= MAX_ITEMS and not db.one(
                "SELECT id FROM items WHERE lower(name)=lower(?) AND lower(coalesce(brand,''))=lower(?)", (f["name"], f["brand"] or "")):
            raise ApiError(409, "limit", f"The list is limited to {MAX_ITEMS} products.")
        iid, created = store.create_item(f)
        if created:
            jobs.enqueue_check(iid)
        return jsonify(store.get_item(iid)), (201 if created else 200)

    @app.patch("/api/items/<int:item_id>")
    def items_patch(item_id):
        it = _item_or_404(item_id)
        d = _body()
        sets, args = [], []
        if "mode" in d:
            sets.append("mode=?")
            args.append(_mode(d))
        became_watching = False
        if "posts_count" in d:
            n = _int(d, "posts_count", 0, 999)
            became_watching = it["posts_count"] == 0 and n > 0
            sets.append("posts_count=?")
            args.append(n)
        if not sets:
            raise ApiError(400, "validation", "Nothing to update.")
        db.run(f"UPDATE items SET {', '.join(sets)}, updated_at=? WHERE id=?", (*args, db.now(), item_id))
        if became_watching:
            jobs.evaluate_alert(item_id)
        return jsonify(store.get_item(item_id))

    @app.delete("/api/items/<int:item_id>")
    def items_delete(item_id):
        _item_or_404(item_id)
        db.run("DELETE FROM items WHERE id=?", (item_id,))
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/check")
    def items_check(item_id):
        it = _item_or_404(item_id)
        if it["phase"] in ("queued", "checking"):
            return jsonify(store.get_item(item_id)), 202
        jobs.enqueue_check(item_id, force=True)
        return jsonify(store.get_item(item_id)), 202

    @app.post("/api/items/<int:item_id>/drafts")
    def items_draft(item_id):
        it = _item_or_404(item_id)
        d = _body()
        kind = d.get("kind")
        if kind not in KINDS:
            raise ApiError(400, "validation", "'kind' must be 'review_post' or 'sponsor_pitch'.")
        if it["phase"] in ("queued", "checking"):
            raise ApiError(409, "check_pending", "The safety check is still running.")
        check = store.latest_check(item_id)
        if not check:
            raise ApiError(409, "no_check", "Run a safety check before drafting.")
        if check["verdict"] == "do_not_recommend":
            raise ApiError(409, "flagged", "This product is flagged. We don't draft promotional content for flagged products.")
        if check["verdict"] in ("caution", "unverified") and d.get("ack") is not True:
            raise ApiError(409, "needs_ack", "Read the safety note and confirm before drafting.")
        try:
            jobs.make_draft(store.item_dict(it), check, kind)
        except Exception:  # noqa: BLE001
            log.exception("draft failed")
            raise ApiError(502, "draft_failed", "Couldn't generate the draft. Try again.")
        return jsonify(store.get_item(item_id)), 201

    # -------------------------------------------------------------- link posts
    @app.post("/api/items/<int:item_id>/link-posts")
    def link_post_create(item_id):
        _item_or_404(item_id)
        d = _body()
        pid = db.run("INSERT INTO link_posts(item_id, label, url, posted_on) VALUES(?,?,?,?)",
                     (item_id, _text(d, "label", 1, 120, True), _url(d, "url"), _text(d, "posted_on", 0, 10)))
        return jsonify(store.get_item(db.one("SELECT item_id FROM link_posts WHERE id=?", (pid,))["item_id"])), 201

    def _lp_or_404(pid):
        lp = db.one("SELECT * FROM link_posts WHERE id=?", (pid,))
        if not lp:
            raise ApiError(404, "not_found", "Link post not found.")
        return lp

    @app.patch("/api/link-posts/<int:pid>")
    def link_post_patch(pid):
        lp = _lp_or_404(pid)
        d = _body()
        if "link_removed" in d:
            if not isinstance(d["link_removed"], bool):
                raise ApiError(400, "validation", "'link_removed' must be a boolean.")
            db.run("UPDATE link_posts SET link_removed=? WHERE id=?", (int(d["link_removed"]), pid))
        if "label" in d:
            db.run("UPDATE link_posts SET label=? WHERE id=?", (_text(d, "label", 1, 120, True), pid))
        return jsonify(store.get_item(lp["item_id"]))

    @app.delete("/api/link-posts/<int:pid>")
    def link_post_delete(pid):
        lp = _lp_or_404(pid)
        db.run("DELETE FROM link_posts WHERE id=?", (pid,))
        return jsonify(store.get_item(lp["item_id"]))

    # -------------------------------------------------------------- watch / alerts
    @app.post("/api/watch/run")
    def watch_run():
        return jsonify({"queued": jobs.watch_run()}), 202

    @app.get("/api/alerts")
    def alerts_list():
        sql = "SELECT * FROM alerts" + (" WHERE handled_at IS NULL" if request.args.get("open") == "1" else "") + " ORDER BY id DESC"
        out = []
        for a in db.all(sql):
            item = db.one("SELECT * FROM items WHERE id=?", (a["item_id"],))
            if item:
                out.append(store.alert_dict(a, item))
        return jsonify(out)

    def _alert_or_404(aid):
        a = db.one("SELECT * FROM alerts WHERE id=?", (aid,))
        if not a:
            raise ApiError(404, "not_found", "Alert not found.")
        return a

    @app.post("/api/alerts/<int:aid>/follow-up")
    def alert_follow_up(aid):
        a = _alert_or_404(aid)
        jobs.enqueue_follow_up(aid)
        return jsonify(store.alert_dict(db.one("SELECT * FROM alerts WHERE id=?", (aid,)),
                                        db.one("SELECT * FROM items WHERE id=?", (a["item_id"],)))), 202

    @app.post("/api/alerts/<int:aid>/handled")
    def alert_handled(aid):
        a = _alert_or_404(aid)
        db.run("UPDATE alerts SET handled_at=? WHERE id=?", (db.now(), aid))
        return jsonify(store.alert_dict(db.one("SELECT * FROM alerts WHERE id=?", (aid,)),
                                        db.one("SELECT * FROM items WHERE id=?", (a["item_id"],))))

    # -------------------------------------------------------------- React build
    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path):
        if path.startswith("api/"):
            raise ApiError(404, "not_found", "No such endpoint.")
        full = os.path.join(config.WEB_DIST, path)
        if path and os.path.isfile(full):
            return send_from_directory(config.WEB_DIST, path)
        if os.path.isfile(os.path.join(config.WEB_DIST, "index.html")):
            return send_from_directory(config.WEB_DIST, "index.html")
        return _err(404, "no_frontend", "Frontend not built. Run: cd web && npm install && npm run build")

    jobs.recover()
    return app


app = create_app() if os.getenv("RW_NO_AUTOAPP") != "1" else None
