import json

import pytest

from server import checks, config, cpsc, db, jobs, llm, store, youcom

POOL = [{"url": "https://cpsc.gov/r1", "title": "CPSC recall r1"}, {"url": "https://news.example/a", "title": "News A"}]


# ------------------------------------------------------------------ verdict rules
def act(match="confirmed", typ="recall"):
    return {"type": typ, "match": match}


def test_verdict_rules():
    cv = checks.compute_verdict
    assert cv([act()], [], False) == "do_not_recommend"
    assert cv([act("possible")], [], False) == "caution"
    assert cv([], [{"kind": "lawsuit"}], False) == "caution"      # allegations alone never reach do_not_recommend
    assert cv([], [], False) == "no_issues_found"
    assert cv([], [], True) == "unverified"                        # official sources down: never reassure
    assert cv([act()], [], True) == "do_not_recommend"             # evidence still wins when found elsewhere
    assert cv([], [{"kind": "complaint"}], True) == "caution"


def test_validate_drops_uncited_and_invented_sources():
    data = {"official_actions": [
        {"type": "recall", "title": "ok", "match": "confirmed", "source": 1},
        {"type": "recall", "title": "invented", "match": "confirmed", "source": 7},
        {"type": "recall", "title": "no source", "match": "confirmed"},
        {"type": "banana", "title": "bad type", "match": "confirmed", "source": 1}],
        "allegations": [{"kind": "lawsuit", "text": "claim", "source": 2}, {"kind": "lawsuit", "text": "x", "source": 0}]}
    actions, alleg = checks.validate(data, POOL)
    assert [a["title"] for a in actions] == ["ok"] and actions[0]["url"] == "https://cpsc.gov/r1"
    assert len(alleg) == 1 and alleg[0]["url"] == "https://news.example/a"


# ------------------------------------------------------------------ run_check with fakes
def fake_world(monkeypatch, *, cpsc_ok=True, gov_ok=True, model=None):
    def f_cpsc(terms, **k):
        if not cpsc_ok:
            raise RuntimeError("cpsc down")
        return []

    def f_search(query, count=8, freshness=None, include_domains=None, boost_domains=None, timeout=None):
        if include_domains:
            if not gov_ok:
                raise RuntimeError("gov down")
            return [{"url": "https://cpsc.gov/r1", "title": "CPSC recall r1", "description": "d", "snippets": ["s"]}]
        return [{"url": "https://news.example/a", "title": "News A", "snippets": ["s"]}]

    def f_claude(prompt, max_tokens=1800):
        if "cpsc_terms" in prompt:
            return {"brand": "AirClub", "product": "Convertible Bassinet", "model": "QX-831", "category": "bassinet", "cpsc_terms": ["bassinet"]}
        return model or {"headline": "h", "official_actions": [], "allegations": [], "safety_note": "n", "what_to_do": ["a"]}

    monkeypatch.setattr(cpsc, "search_recalls", f_cpsc)
    monkeypatch.setattr(youcom, "search", f_search)
    monkeypatch.setattr(youcom, "extract", lambda *a, **k: "")
    monkeypatch.setattr(youcom, "research", lambda *a, **k: ("research text", []))
    monkeypatch.setattr(llm, "claude_json", f_claude)


PRODUCT = {"name": "AirClub Convertible Bassinet", "brand": "AirClub", "url": None}


def test_model_verdict_is_ignored(env, monkeypatch):
    fake_world(monkeypatch, model={"verdict": "do_not_recommend", "headline": "h", "official_actions": [], "allegations": [],
                                   "safety_note": "n", "what_to_do": []})
    res, _ = checks.run_check(PRODUCT, force=True)
    assert res["verdict"] == "no_issues_found"


def test_confirmed_action_with_valid_citation(env, monkeypatch):
    fake_world(monkeypatch, model={"headline": "h", "official_actions": [
        {"type": "recall", "title": "t", "match": "confirmed", "source": 1, "date": "2026-03-26", "hazard": "fall"}],
        "allegations": [], "safety_note": "n", "what_to_do": []})
    res, ident = checks.run_check(PRODUCT, force=True)
    assert res["verdict"] == "do_not_recommend" and res["official_actions"][0]["url"] == "https://cpsc.gov/r1"
    assert ident["model"] == "QX-831"


def test_both_official_sources_down_is_unverified_and_not_cached(env, monkeypatch):
    fake_world(monkeypatch, cpsc_ok=False, gov_ok=False)
    res, _ = checks.run_check(PRODUCT, force=True)
    assert res["verdict"] == "unverified" and "couldn't reach" in res["headline"].lower()
    assert any("unavailable" in g for g in res["gaps"])
    assert db.cache_get(checks.cache_key("AirClub", "Convertible Bassinet", "QX-831"), 6) is None


def test_one_official_source_down_adds_partial_gap(env, monkeypatch):
    fake_world(monkeypatch, cpsc_ok=False)
    res, _ = checks.run_check(PRODUCT, force=True)
    assert res["verdict"] == "no_issues_found" and any(g.startswith("Partial check") for g in res["gaps"])


def test_all_sources_failing_raises(env, monkeypatch):
    fake_world(monkeypatch, cpsc_ok=False, gov_ok=False)
    monkeypatch.setattr(youcom, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(youcom, "research", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        checks.run_check(PRODUCT, force=True)


def test_cache_hit_and_force_bypass(env, monkeypatch):
    fake_world(monkeypatch)
    checks.run_check(PRODUCT, force=True)
    calls = {"n": 0}
    orig = cpsc.search_recalls

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(cpsc, "search_recalls", counting)
    checks.run_check(PRODUCT)
    assert calls["n"] == 0
    checks.run_check(PRODUCT, force=True)
    assert calls["n"] == 1


# ------------------------------------------------------------------ alerts
def mk_item(posts=0, name="Thing One"):
    iid, _ = store.create_item({"name": name, "posts_count": posts})
    return iid


def put_check(iid, verdict, headline="Headline."):
    res = {"verdict": verdict, "headline": headline, "safety_note": "", "what_to_do": [], "official_actions": [],
           "allegations": [], "sources": [], "gaps": [], "checked_on": "2026-11-22"}
    db.run("INSERT INTO checks(item_id, verdict, result_json, checked_at) VALUES(?,?,?,?)", (iid, verdict, json.dumps(res), db.now()))


def test_alert_only_for_watching_items(env):
    iid = mk_item(posts=0)
    put_check(iid, "do_not_recommend")
    assert jobs.evaluate_alert(iid) is None


def test_alert_when_posts_count_goes_zero_to_n(client):
    iid = mk_item(posts=0)
    put_check(iid, "do_not_recommend")
    r = client.patch(f"/api/items/{iid}", json={"posts_count": 3})
    assert r.status_code == 200
    a = r.json["alert"]
    assert a["headline"].startswith("You linked Thing One in 3 posts. Headline.") and a["follow_up_status"] == "done"


def test_alert_headline_singular_and_live_count(client):
    iid = mk_item(posts=1)
    put_check(iid, "caution")
    jobs.evaluate_alert(iid)
    assert store.get_item(iid)["alert"]["headline"].startswith("You linked Thing One in 1 post. ")
    client.patch(f"/api/items/{iid}", json={"posts_count": 4})
    assert store.get_item(iid)["alert"]["headline"].startswith("You linked Thing One in 4 posts. ")


def test_handled_not_reraised_unless_worse(env):
    iid = mk_item(posts=2)
    put_check(iid, "caution")
    a1 = jobs.evaluate_alert(iid)
    assert a1
    db.run("UPDATE alerts SET handled_at=? WHERE id=?", (db.now(), a1))
    assert jobs.evaluate_alert(iid) is None                       # same rank: stay quiet
    put_check(iid, "do_not_recommend")
    a2 = jobs.evaluate_alert(iid)
    assert a2 and a2 != a1                                        # worse: new alert
    assert jobs.evaluate_alert(iid) is None


def test_unverified_and_clean_never_alert(env):
    iid = mk_item(posts=2)
    for v in ("unverified", "no_issues_found"):
        put_check(iid, v)
        assert jobs.evaluate_alert(iid) is None


def test_new_alert_closes_older_open_alert(env):
    iid = mk_item(posts=2)
    put_check(iid, "caution")
    a1 = jobs.evaluate_alert(iid)
    put_check(iid, "do_not_recommend")
    jobs.evaluate_alert(iid)
    assert db.one("SELECT handled_at FROM alerts WHERE id=?", (a1,))["handled_at"]


def test_followup_failure_sets_failed(env, monkeypatch):
    from server import drafts
    config.set_demo(False)
    monkeypatch.setattr(drafts, "follow_up", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    iid = mk_item(posts=2)
    put_check(iid, "do_not_recommend")
    jobs.evaluate_alert(iid)
    assert store.get_item(iid)["alert"]["follow_up_status"] == "failed"


# ------------------------------------------------------------------ recovery and job failure
def test_recover_requeues_interrupted_items(env):
    iid = mk_item(posts=0, name="Recover Me")
    db.run("UPDATE items SET phase='checking' WHERE id=?", (iid,))
    jobs.recover()
    assert store.get_item(iid)["phase"] == "done"


def test_check_failure_keeps_previous_check_and_records_error(env, monkeypatch):
    iid = mk_item(posts=0, name="Fails Later")
    put_check(iid, "no_issues_found", "old")
    config.set_demo(False)
    monkeypatch.setattr(checks, "run_check", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    jobs._check_job(iid, True)
    it = store.get_item(iid)
    assert it["phase"] == "error" and "down" in it["error"] and it["check"]["headline"] == "old"


# ------------------------------------------------------------------ API
def test_api_validation(client):
    assert client.post("/api/items", json={}).status_code == 400
    assert client.post("/api/items", json={"name": "x"}).status_code == 400
    assert client.post("/api/items", json={"name": "Good Name", "url": "javascript:alert(1)"}).status_code == 400
    assert client.post("/api/items", json={"name": "Good Name", "mode": "weird"}).status_code == 400
    assert client.post("/api/items", data="notjson", content_type="text/plain").status_code == 400
    r = client.post("/api/items", json={"name": "Good Name"})
    assert r.status_code == 201 and r.json["phase"] in ("queued", "done")
    iid = r.json["id"]
    assert client.patch(f"/api/items/{iid}", json={"posts_count": 1000}).status_code == 400
    assert client.patch(f"/api/items/{iid}", json={"posts_count": True}).status_code == 400
    assert client.patch(f"/api/items/{iid}", json={}).status_code == 400
    assert client.get("/api/nope").status_code == 404
    assert client.get("/api/nope").json["error"]["code"] == "not_found"


def test_dedupe_and_limit(client):
    a = client.post("/api/items", json={"name": "Same Thing", "brand": "B"})
    b = client.post("/api/items", json={"name": "same thing", "brand": "b"})
    assert a.status_code == 201 and b.status_code == 200 and a.json["id"] == b.json["id"]
    for i in range(24):
        assert client.post("/api/items", json={"name": f"Product number {i}"}).status_code == 201
    assert client.post("/api/items", json={"name": "One too many"}).json["error"]["code"] == "limit"
    assert client.post("/api/items", json={"name": "Same Thing", "brand": "B"}).status_code == 200  # dupes still allowed at the cap


def test_draft_gating(client):
    iid = client.post("/api/items", json={"name": "Gate Test"}).json["id"]
    code = lambda: client.post(f"/api/items/{iid}/drafts", json={"kind": "review_post"})  # noqa: E731
    db.run("UPDATE items SET phase='checking' WHERE id=?", (iid,))
    assert code().json["error"]["code"] == "check_pending"
    db.run("UPDATE items SET phase='done' WHERE id=?", (iid,))
    db.run("DELETE FROM checks WHERE item_id=?", (iid,))
    assert code().json["error"]["code"] == "no_check"
    put_check(iid, "do_not_recommend")
    assert code().json["error"]["code"] == "flagged"
    assert client.post(f"/api/items/{iid}/drafts", json={"kind": "review_post", "ack": True}).json["error"]["code"] == "flagged"
    put_check(iid, "caution")
    assert code().json["error"]["code"] == "needs_ack"
    assert client.post(f"/api/items/{iid}/drafts", json={"kind": "review_post", "ack": "yes"}).status_code == 409
    ok = client.post(f"/api/items/{iid}/drafts", json={"kind": "review_post", "ack": True})
    assert ok.status_code == 201 and ok.json["drafts"][0]["kind"] == "review_post"
    put_check(iid, "no_issues_found")
    assert client.post(f"/api/items/{iid}/drafts", json={"kind": "sponsor_pitch"}).status_code == 201
    assert client.post(f"/api/items/{iid}/drafts", json={"kind": "bogus"}).status_code == 400


def test_link_posts_and_delete_cascade(client):
    iid = client.post("/api/items", json={"name": "Link Test"}).json["id"]
    it = client.post(f"/api/items/{iid}/link-posts", json={"label": "Reel", "url": "https://x.com/p"}).json
    pid = it["link_posts"][0]["id"]
    assert client.patch(f"/api/link-posts/{pid}", json={"link_removed": True}).json["link_posts"][0]["link_removed"] is True
    assert client.patch(f"/api/link-posts/{pid}", json={"link_removed": "yes"}).status_code == 400
    assert client.post(f"/api/items/{iid}/link-posts", json={"label": "Bad", "url": "ftp://x"}).status_code == 400
    assert client.delete(f"/api/items/{iid}").status_code == 200
    assert db.all("SELECT * FROM link_posts") == [] and client.delete(f"/api/items/{iid}").status_code == 404


def test_profile_defaults_and_roundtrip(client):
    p = client.get("/api/profile").json
    assert p["platform"] == "instagram" and p["followers"] == 0
    r = client.put("/api/profile", json={"handle": "@mama", "platform": "tiktok", "niche": "newborn", "followers": 12000, "engagement": 4.2})
    assert r.json["followers"] == 12000
    assert client.put("/api/profile", json={"platform": "x", "followers": -1}).status_code == 400
    assert client.put("/api/profile", json={"platform": "tiktok", "followers": 1, "engagement": 101}).status_code == 400


def test_alert_endpoints(client):
    iid = client.post("/api/items", json={"name": "Alert Test"}).json["id"]
    put_check(iid, "do_not_recommend")
    client.patch(f"/api/items/{iid}", json={"posts_count": 2})
    alerts = client.get("/api/alerts?open=1").json
    assert len(alerts) == 1
    aid = alerts[0]["id"]
    assert client.post(f"/api/alerts/{aid}/follow-up").status_code == 202
    assert client.post(f"/api/alerts/{aid}/handled").json["handled_at"]
    assert client.get("/api/alerts?open=1").json == [] and len(client.get("/api/alerts").json) == 1
    assert client.post("/api/alerts/999/handled").status_code == 404


def test_watch_run_requeues_only_watching(client):
    a = client.post("/api/items", json={"name": "Watched One"}).json["id"]
    client.post("/api/items", json={"name": "Unwatched One"})
    client.patch(f"/api/items/{a}", json={"posts_count": 2})
    r = client.post("/api/watch/run")
    assert r.status_code == 202 and r.json["queued"] == 1


# ------------------------------------------------------------------ demo flow
def test_demo_flow_end_to_end(client):
    h = client.get("/api/health").json
    assert h["mode"] in ("demo-sample", "demo-cached") and h["live_ready"] is False
    seeded = client.post("/api/demo/seed").json
    assert len(seeded) == 3
    assert len(client.post("/api/demo/seed").json) == 3 and len(client.get("/api/items").json) == 3   # idempotent
    by_name = {i["name"]: i for i in client.get("/api/items").json}
    air = by_name["AirClub Convertible Bassinet"]
    assert air["check"]["verdict"] == "do_not_recommend" and air["alert"]["follow_up"]["post_caption"]
    assert air["alert"]["headline"].startswith("You linked AirClub Convertible Bassinet in 4 posts.")
    coo = by_name["CooCooBaby Baby Lounger"]
    assert len(coo["check"]["official_actions"]) == 2 and coo["alert"]
    clean = by_name[config.DEMO_CLEAN_PRODUCT]
    assert clean["check"]["verdict"] == "no_issues_found" and clean["alert"] is None
    res = client.post("/api/products/search", json={"q": "bassinet"}).json
    assert res["results"][0]["pre_flag"]["url"].startswith("https://cpsc.gov")
    assert client.post("/api/demo/reset").status_code == 200 and client.get("/api/items").json == []


def test_demo_mode_toggle(client):
    assert client.post("/api/demo/mode", json={"on": "maybe"}).status_code == 400
    assert client.post("/api/demo/mode", json={"on": False}).json["mode"] == "live"
    assert client.post("/api/demo/mode", json={"on": True}).json["mode"] != "live"
    assert client.post("/api/demo/mode", json={"on": None}).status_code == 200


def test_demo_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "ENABLE_DEMO", False)
    assert client.post("/api/demo/seed").status_code == 404
    assert config.demo_active() is False


def test_unknown_product_gets_labeled_sample(client):
    it = client.post("/api/items", json={"name": "Mystery Crib 3000"}).json
    chk = client.get("/api/items").json[0]["check"]
    assert chk["verdict"] == "no_issues_found" and "SAMPLE" in chk["headline"] and any("Demo" in g for g in chk["gaps"])
    assert it["name"] == "Mystery Crib 3000"


def test_spa_fallback_when_frontend_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nope"))
    r = client.get("/some/route")
    assert r.status_code == 404 and r.json["error"]["code"] == "no_frontend"


def test_cpsc_normalize_is_defensive():
    n = cpsc.normalize({"RecallNumber": "26-1", "RecallDate": "2026-03-26T00:00:00", "Title": "T", "Products": [{"Name": "Bassinet", "Model": "QX"}, "junk"],
                        "Hazards": None})
    assert n["date"] == "2026-03-26" and n["products"] == ["Bassinet"] and n["hazards"] == []
    assert cpsc.normalize({})["title"] is None


def test_parse_json_tolerant():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        llm.parse_json("no json here")
