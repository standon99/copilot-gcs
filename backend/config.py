import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
RUNTIME = ROOT / "runtime" / "copilot"
RUNTIME.mkdir(parents=True, exist_ok=True)
PROFILES = {
    "copter": {
        "binary": "arducopter",
        "model": "+",
        "defaults": "Tools/autotest/default_params/copter.parm",
        "type": 2,
        "modes": ["STABILIZE", "ALT_HOLD", "LOITER", "GUIDED", "AUTO", "RTL", "LAND", "BRAKE"],
        "commands": [16, 17, 19, 20, 21, 22, 178],
    },
    "plane": {
        "binary": "arduplane",
        "model": "plane",
        "defaults": "Tools/autotest/models/plane.parm",
        "type": 1,
        "modes": ["MANUAL", "FBWA", "LOITER", "GUIDED", "AUTO", "RTL"],
        "commands": [16, 17, 19, 20, 21, 22, 178],
    },
    "rover": {
        "binary": "ardurover",
        "model": "rover",
        "defaults": "Tools/autotest/default_params/rover.parm",
        "type": 10,
        "modes": ["MANUAL", "HOLD", "GUIDED", "AUTO", "RTL", "LOITER"],
        "commands": [16, 17, 19, 20, 178],
    },
}
HOME = {"lat": -35.363261, "lon": 149.165230, "alt": 584.0}
MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1").rstrip("/")
API_KEY = os.getenv("OLLAMA_API_KEY", "")
MONITOR_INTERVAL = max(10, float(os.getenv("MONITOR_INTERVAL", "20")))
INFERENCE_TIMEOUT = min(120, max(10, float(os.getenv("INFERENCE_TIMEOUT", "45"))))
