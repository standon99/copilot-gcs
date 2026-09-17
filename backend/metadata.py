import json
from functools import lru_cache

from .config import ROOT

FIRMWARE_COMMIT = "dbe792162d06cab66c3475fd5556bf7a120f119e"


@lru_cache
def metadata(profile):
    path = ROOT / "runtime/metadata" / profile / "apm.pdef.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {
        key: value
        for group, items in raw.items()
        if group != "json"
        for key, value in items.items()
    }


def validate_parameter(profile, name, value):
    meta = metadata(profile).get(name, {})
    if str(meta.get("ReadOnly", "")).lower() == "true":
        raise ValueError("Parameter metadata marks this value read-only")
    if "Range" in meta:
        low, high = meta["Range"].get("low"), meta["Range"].get("high")
        try:
            bounds = float(low), float(high)
        except (TypeError, ValueError):
            bounds = None
        if bounds and not bounds[0] <= value <= bounds[1]:
            raise ValueError(f"Value outside documented range {low}..{high}")
    if "Values" in meta and not any(float(k) == value for k in meta["Values"]):
        raise ValueError("Value is not in the documented enum")
    if "Bitmask" in meta:
        mask = sum(1 << int(k) for k in meta["Bitmask"])
        if value < 0 or int(value) != value or int(value) & ~mask:
            raise ValueError("Value includes undocumented bitmask bits")
    return meta
