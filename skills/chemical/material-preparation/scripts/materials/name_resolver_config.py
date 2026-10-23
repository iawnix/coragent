"""Pure name-resolver configuration shared by installation and scientific Jobs."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_ENDPOINTS = {
    "pubchem": "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
    "opsin": "https://opsin.ch.cam.ac.uk/opsin",
}
_BACKEND_FIELDS = {"enabled", "endpoint", "timeout_seconds", "cache", "cache_dir", "user_agent"}


def parse_name_resolver_config(raw: Mapping) -> dict:
    """Normalize resolver settings without loading chemistry or making requests."""
    if not isinstance(raw, Mapping) or set(raw) - {"default_resolver", "backends"}:
        raise ValueError("name-resolver configuration requires supported settings")
    default = raw.get("default_resolver", "auto")
    if not isinstance(default, str) or default not in {"auto", *DEFAULT_ENDPOINTS}:
        raise ValueError("default_resolver must be auto, pubchem, or opsin")
    backends = raw.get("backends", {})
    if not isinstance(backends, Mapping):
        raise ValueError("backends must be a TOML table")
    normalized = {"default_resolver": default, "backends": {}}
    for name, value in backends.items():
        if name not in DEFAULT_ENDPOINTS or not isinstance(value, Mapping):
            raise ValueError("unsupported resolver backend")
        if set(value) - _BACKEND_FIELDS:
            raise ValueError(f"unsupported backends.{name} setting")
        enabled = value.get("enabled", True)
        if type(enabled) is not bool:
            raise ValueError(f"backends.{name}.enabled must be boolean")
        endpoint = value.get("endpoint", DEFAULT_ENDPOINTS[name])
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError(f"backends.{name}.endpoint must be a URL")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError(f"backends.{name}.endpoint must be an absolute HTTP(S) URL")
        timeout = value.get("timeout_seconds", 10)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 60:
            raise ValueError(f"backends.{name}.timeout_seconds must be between 1 and 60")
        cache = value.get("cache", True)
        if type(cache) is not bool:
            raise ValueError(f"backends.{name}.cache must be boolean")
        cache_dir = value.get("cache_dir")
        if cache_dir is not None and (not isinstance(cache_dir, str) or not Path(cache_dir).is_absolute()):
            raise ValueError(f"backends.{name}.cache_dir must be an absolute path")
        user_agent = value.get("user_agent", "CoRAgent-chemical-name-resolver/1")
        if not isinstance(user_agent, str) or not user_agent.strip() or len(user_agent) > 256:
            raise ValueError(f"backends.{name}.user_agent must be a non-empty string")
        normalized["backends"][name] = {
            "enabled": enabled, "endpoint": endpoint.rstrip("/"), "timeout_seconds": float(timeout),
            "cache": cache, "cache_dir": cache_dir, "user_agent": user_agent,
        }
    return normalized
