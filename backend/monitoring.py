"""Operator-owned usage limits and per-vehicle advisory monitoring preferences."""

import json
import math
import os
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Monitoring(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = 0
    periodic_enabled: bool = True
    interval_s: int | None = Field(default=None, ge=10, le=86400)
    watch_advice_enabled: bool = True
    focus: str = Field(default="", max_length=2000)


def monitor_config(v):
    return getattr(
        v, "monitoring", Monitoring(periodic_enabled=getattr(v, "monitor_enabled", True))
    )


def effective_monitoring(v, prefs):
    c = monitor_config(v)
    return {
        **c.model_dump(),
        "periodic_effective": c.periodic_enabled and prefs.monitor_enabled,
        "watch_advice_effective": c.watch_advice_enabled and prefs.watch_inference_enabled,
        "effective_interval_s": max(
            c.interval_s or prefs.monitor_interval, prefs.automatic_min_interval
        ),
        "hard_min_interval_s": prefs.automatic_min_interval,
        "periodic_allowed_in_settings": prefs.monitor_enabled,
        "watch_advice_allowed_in_settings": prefs.watch_inference_enabled,
    }


class AutomaticRateLimited(RuntimeError):
    def __init__(self, retry_at):
        self.retry_at = retry_at
        super().__init__("Waiting for the automatic inference usage limit")


class AutomaticBudget:
    """One installation-wide start spacing, including repairs and all vehicles.

    Reservations happen synchronously immediately before a provider request.
    Failed/cancelled requests count too. Persist the last reservation across restart.
    """

    def __init__(self, path: Path | None = None):
        self.path = path
        self.last = -1e30
        if path and path.exists():
            value = json.loads(path.read_text())["last_started_at"]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Invalid automatic usage record")
            self.last = value

    def ready(self, interval, now=None):
        return (time.time() if now is None else now) >= self.last + interval

    def reserve(self, interval, now=None):
        now = time.time() if now is None else now
        if not self.ready(interval, now):
            raise AutomaticRateLimited(self.last + interval)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"last_started_at": now}, f)
                f.flush()
                os.fsync(f.fileno())
            temporary.replace(self.path)
        self.last = now
