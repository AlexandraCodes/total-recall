"""Background jobs: safety checks, alert evaluation, follow-up drafts, startup recovery.

Outer pool (OUTER_WORKERS) runs whole jobs. checks.INNER is a separate pool for the parallel source gathers inside a
check, so outer workers waiting on inner tasks can never deadlock.
"""
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor

from . import checks, config, db, demo, drafts, store

log = logging.getLogger("recallwatch.jobs")
OUTER = ThreadPoolExecutor(max_workers=config.OUTER_WORKERS, thread_name_prefix="job")

RANK = checks.RANK


def _sleep_demo():
    lo, hi = config.DEMO_DELAY
    if hi > 0:
        time.sleep(random.uniform(lo, hi))


def _set_phase(item_id, phase, error=None):
    db.run("UPDATE items SET phase=?, error=?, updated_at=? WHERE id=?", (phase, error, db.now(), item_id))


# ------------------------------------------------------------------ checks
def enqueue_check(item_id, force=False):
    _set_phase(item_id, "queued")
    OUTER.submit(_check_job, item_id, force)


def _check_job(item_id, force):
    item = db.one("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        return
    _set_phase(item_id, "checking")
    product = {"name": item["name"], "brand": item["brand"], "url": item["url"]}
    try:
        if config.demo_active():
            _sleep_demo()
            result, ident = demo.check(product)
        else:
            result, ident = checks.run_check(product, force=force)
    except Exception as e:  # noqa: BLE001
        log.exception("check failed for item %s", item_id)
        # Keep the previous check (if any) visible; the error is shown beside it.
        _set_phase(item_id, "error", f"{type(e).__name__}: {str(e)[:200]}")
        return
    if not db.one("SELECT id FROM items WHERE id=?", (item_id,)):
        return  # removed while checking
    db.run("INSERT INTO checks(item_id, verdict, result_json, checked_at) VALUES(?,?,?,?)",
           (item_id, result["verdict"], json.dumps(result), db.now()))
    db.run("UPDATE items SET brand=coalesce(nullif(?,''), brand), product=?, model=?, phase='done', error=NULL, updated_at=? WHERE id=?",
           (ident.get("brand"), ident.get("product"), ident.get("model"), db.now(), item_id))
    evaluate_alert(item_id)


# ------------------------------------------------------------------ alerts
def evaluate_alert(item_id):
    """Create an alert when the latest check outranks what was already alerted, for watching items (posts_count > 0).
    Called after a check completes and when posts_count goes 0 -> N."""
    item = db.one("SELECT * FROM items WHERE id=?", (item_id,))
    if not item or item["posts_count"] <= 0:
        return None
    check = store.latest_check(item_id)
    if not check:
        return None
    rank = RANK.get(check["verdict"], 0)
    if rank < 1 or rank <= item["last_alerted_rank"]:
        return None
    # Close older open alerts for this item: the new one supersedes them.
    db.run("UPDATE alerts SET handled_at=? WHERE item_id=? AND handled_at IS NULL", (db.now(), item_id))
    aid = db.run("INSERT INTO alerts(item_id, verdict, headline, follow_up_status, created_at) VALUES(?,?,?,'generating',?)",
                 (item_id, check["verdict"], check["headline"], db.now()))
    db.run("UPDATE items SET last_alerted_rank=? WHERE id=?", (rank, item_id))
    OUTER.submit(_follow_up_job, aid)
    return aid


def enqueue_follow_up(alert_id):
    db.run("UPDATE alerts SET follow_up_status='generating' WHERE id=?", (alert_id,))
    OUTER.submit(_follow_up_job, alert_id)


def _follow_up_job(alert_id):
    alert = db.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    if not alert:
        return
    item = db.one("SELECT * FROM items WHERE id=?", (alert["item_id"],))
    check = store.latest_check(alert["item_id"]) if item else None
    if not item or not check:
        return
    try:
        if config.demo_active():
            _sleep_demo()
            content = demo.follow_up(item, check)
        else:
            content = drafts.follow_up(item, check)
    except Exception:  # noqa: BLE001
        log.exception("follow-up failed for alert %s", alert_id)
        db.run("UPDATE alerts SET follow_up_status='failed' WHERE id=?", (alert_id,))
        return
    db.run("UPDATE alerts SET follow_up_json=?, follow_up_status='done' WHERE id=?", (json.dumps(content), alert_id))


# ------------------------------------------------------------------ drafts (synchronous, called from the API)
def make_draft(item, check, kind):
    profile = store.profile_get()
    demo_on = config.demo_active()
    if kind == "review_post":
        content = demo.review_post(item, check, profile) if demo_on else drafts.review_post(item, check, profile)
    else:
        content = demo.sponsor_pitch(item, check, profile) if demo_on else drafts.sponsor_pitch(item, check, profile)
    did = db.run("INSERT INTO drafts(item_id, kind, content_json, status, created_at) VALUES(?,?,?,'done',?)",
                 (item["id"], kind, json.dumps({"kind": kind, **content}), db.now()))
    return did


# ------------------------------------------------------------------ recovery / watch
def recover():
    """After a restart: re-run interrupted checks and follow-ups."""
    for r in db.all("SELECT id FROM items WHERE phase IN ('queued','checking')"):
        enqueue_check(r["id"])
    for a in db.all("SELECT id FROM alerts WHERE follow_up_status='generating'"):
        OUTER.submit(_follow_up_job, a["id"])


def watch_run():
    ids = [r["id"] for r in db.all("SELECT id FROM items WHERE posts_count > 0")]
    for i in ids:
        enqueue_check(i, force=True)
    return len(ids)
