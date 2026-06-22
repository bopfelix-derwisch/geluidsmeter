"""Basis-connector: HTTP met timeout, on-disk cache en nette degradatie."""
import json
import time
import hashlib
from pathlib import Path

import httpx


class ConnectorError(Exception):
    """Externe bron tijdelijk niet beschikbaar."""


class BaseConnector:
    def __init__(self, cache_dir: str, timeout: float = 10.0, cache_ttl: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.cache_ttl = cache_ttl

    def _cache_path(self, url: str, params: dict | None) -> Path:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.json"

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        cp = self._cache_path(url, params)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < self.cache_ttl:
            return json.loads(cp.read_text())
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            if cp.exists():
                return json.loads(cp.read_text())
            raise ConnectorError(f"Bron niet beschikbaar: {url}") from exc
        cp.write_text(json.dumps(data))
        return data

    def post_json(self, url: str, json_body: dict | None = None, headers: dict | None = None):
        cp = self._cache_path(url, json_body)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < self.cache_ttl:
            return json.loads(cp.read_text())
        try:
            resp = httpx.post(url, json=json_body, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            if cp.exists():
                return json.loads(cp.read_text())
            raise ConnectorError(f"Bron niet beschikbaar: {url}") from exc
        cp.write_text(json.dumps(data))
        return data
