"""Environment, constants and demo-mode switch."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DATA_DIR = os.getenv("DATA_DIR", os.path.join(ROOT, "data"))
DB_PATH = os.path.join(DATA_DIR, "recallwatch.db")
FIXTURES = os.path.join(BASE, "fixtures")
WEB_DIST = os.path.join(ROOT, "web", "dist")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
RESEARCH_EFFORT = os.getenv("RESEARCH_EFFORT", "lite")  # lite | standard | deep
PRODUCT_SEARCH_SUFFIX = os.getenv("PRODUCT_SEARCH_SUFFIX", "baby product")
ENABLE_DEMO = os.getenv("ENABLE_DEMO", "1") == "1"
DEMO_CLEAN_PRODUCT = os.getenv("DEMO_CLEAN_PRODUCT", "Graco Pack 'n Play Playard")

# Timeouts (seconds). Research is capped at 60 in checks so the demo never waits on it.
T_SEARCH = 30
T_EXTRACT = 35
T_RESEARCH = int(os.getenv("RESEARCH_TIMEOUT", "60"))
T_CPSC = 25
T_CHECK = 90

CHECK_CACHE_HOURS = 6
SEARCH_CACHE_HOURS = 1
OUTER_WORKERS = 3   # concurrent checks
INNER_WORKERS = 8   # parallel source gathers inside a check (separate pool: never share with outer)

DEMO_DELAY = (float(os.getenv("DEMO_DELAY_MIN", "3")), float(os.getenv("DEMO_DELAY_MAX", "6")))

_state = {"demo_override": None}


def ydc_key() -> str:
    return os.getenv("YDC_API_KEY", "")


def keys_ready() -> bool:
    return bool(os.getenv("YDC_API_KEY") and os.getenv("ANTHROPIC_API_KEY"))


def set_demo(on):
    """Runtime override from POST /api/demo/mode. None clears it."""
    _state["demo_override"] = on


def demo_active() -> bool:
    if not ENABLE_DEMO:
        return False
    if _state["demo_override"] is not None:
        return bool(_state["demo_override"])
    mode = os.getenv("DEMO_MODE", "auto").lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    return not keys_ready()
