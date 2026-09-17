"""Installation-local, atomic preferences. Credentials remain exclusively in .env."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import API_KEY, BASE_URL, INFERENCE_TIMEOUT, MODEL, MONITOR_INTERVAL, RUNTIME
from .prompts import INTENT_SYSTEM, INTERACTION_SYSTEM, MONITOR_SYSTEM, PLANNER_SYSTEM

DEFAULT_PROMPTS = {
    "monitor": MONITOR_SYSTEM,
    "planner": PLANNER_SYSTEM,
    "intent": INTENT_SYSTEM,
    "interaction": INTERACTION_SYSTEM,
}


def normalize_endpoint(value):
    url = urlsplit(value.strip())
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("Use an http(s) API base URL without embedded credentials")
    if url.query or url.fragment:
        raise ValueError("API base URL cannot contain a query or fragment")
    port = url.port or (443 if url.scheme == "https" else 80)
    if port == int(os.getenv("COPILOT_PORT", "8080")):
        raise ValueError("The model endpoint cannot use the ground station's port")
    path = url.path.rstrip("/")
    if path.endswith(("/chat/completions", "/api/chat", "/models")):
        raise ValueError("Enter the API base URL, for example http://localhost:11434/v1")
    if not path:
        path = "/v1"
    return urlunsplit((url.scheme, url.netloc, path, "", ""))


def local_port(base_url):
    url = urlsplit(base_url)
    if url.hostname in ("localhost", "127.0.0.1", "::1"):
        return url.port or (443 if url.scheme == "https" else 80)
    return None


def credential_for(base_url):
    # Never forward the cloud credential when the operator switches providers.
    target, original = urlsplit(base_url), urlsplit(BASE_URL)
    if target.scheme == "https" and (target.scheme, target.netloc) == (
        original.scheme,
        original.netloc,
    ):
        return API_KEY
    return ""


class Prompts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monitor: str = Field(default=MONITOR_SYSTEM, min_length=20, max_length=24000)
    planner: str = Field(default=PLANNER_SYSTEM, min_length=20, max_length=24000)
    intent: str = Field(default=INTENT_SYSTEM, min_length=20, max_length=24000)
    interaction: str = Field(default=INTERACTION_SYSTEM, min_length=20, max_length=24000)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(default=0, ge=0)
    base_url: str = Field(default=BASE_URL, max_length=500)
    model: str = Field(default=MODEL, min_length=1, max_length=160)
    monitor_enabled: bool = True
    monitor_interval: int = Field(default=int(MONITOR_INTERVAL), ge=10, le=86400)
    inference_timeout: int = Field(default=int(INFERENCE_TIMEOUT), ge=10, le=120)
    prompts: Prompts = Field(default_factory=Prompts)

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value):
        return normalize_endpoint(value)

    @field_validator("model")
    @classmethod
    def model_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Enter a model ID")
        return value.strip()


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.value = (
            Preferences.model_validate_json(path.read_text()) if path.exists() else Preferences()
        )

    def get(self):
        return self.value.model_dump()

    def save(self, value: Preferences):
        if value.revision != self.value.revision:
            raise ValueError("Settings changed in another window; reload before saving")
        revised = value.model_copy(update={"revision": value.revision + 1})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(revised.model_dump(), indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(self.path)
        self.value = revised
        return self.get()


settings = SettingsStore(RUNTIME / "settings.json")
