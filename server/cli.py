"""Record real fixtures from a live run (do this after the M0 smoke test passes).

  python -m server.cli smoke                         # M0: one call to CPSC, You.com Search/Extract/Research, and Claude
  python -m server.cli record check "AirClub Convertible Bassinet"
  python -m server.cli record followup "AirClub Convertible Bassinet"
  python -m server.cli record search "bassinet"
Needs YDC_API_KEY and ANTHROPIC_API_KEY in the environment (Replit Secrets). Recorded checks carry "_recorded": true,
which switches the demo banner from "SAMPLE DATA" to "Replaying a saved live run".
"""
import json
import os
import sys

os.environ.setdefault("RW_NO_AUTOAPP", "1")

from . import checks, config, cpsc, db, demo, drafts, llm, products, youcom  # noqa: E402


def _write(sub, name, payload):
    path = os.path.join(config.FIXTURES, sub, f"{demo.slug(name)}.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print("wrote", path)


def smoke():
    ok = True

    def step(label, fn):
        nonlocal ok
        try:
            print(f"[ OK ] {label}: {fn()}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[FAIL] {label}: {type(e).__name__}: {e}")

    step("CPSC recalls (bassinet)", lambda: f"{len(cpsc.search_recalls(['bassinet']))} records")
    step("You.com Search", lambda: f"{len(youcom.search('AirClub bassinet recall', 3, None, ['cpsc.gov']))} results")
    step("You.com Extract", lambda: f"{len(youcom.extract('https://www.cpsc.gov/Recalls'))} chars")
    step("You.com Research (lite)", lambda: f"{len(youcom.research('Was the AirClub convertible bassinet recalled?')[0])} chars")
    step("Claude JSON", lambda: llm.claude_json('Return {"ok": true}', 50))
    print("ALL OK" if ok else "SOME CHECKS FAILED: fix before the demo")
    return 0 if ok else 1


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "smoke":
        return smoke()
    if argv[0] != "record" or len(argv) < 3:
        print(__doc__)
        return 1
    kind, name = argv[1], " ".join(argv[2:])
    db.init()
    config.set_demo(False)
    if not config.keys_ready():
        print("Set YDC_API_KEY and ANTHROPIC_API_KEY first.")
        return 1
    if kind == "check":
        result, ident = checks.run_check({"name": name, "brand": None, "url": None}, force=True)
        _write("checks", name, {"_recorded": True, "_match": sorted(demo._tokens(name))[:2], "_ident": ident, "result": result})
    elif kind == "followup":
        result, _ = checks.run_check({"name": name, "brand": None, "url": None})
        fu = drafts.follow_up({"name": name, "posts_count": 3}, result)
        _write("followups", name, {"_match": sorted(demo._tokens(name))[:2], "result": fu})
    elif kind == "search":
        results, _ = products.search(name)
        _write("search", name, {"results": results})
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
