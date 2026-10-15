"""Wikimedia へのアクセス。

- 応答を .cache/http/ に保存し、同じ URL には二度アクセスしない
- リクエストの間隔を最低 min_interval 秒あける
- 429（アクセス過多）と 5xx は Retry-After に従って待ち、指数的に間隔を広げて再試行する
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "http"
USER_AGENT = "Pedigree_JPG1horses/0.1 (https://github.com/u-10bei/Pedigree_JPG1horses)"


class FetchError(Exception):
    pass


class Client:
    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        min_interval: float = 1.0,
        max_retries: int = 8,
        max_wait: float = 120.0,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.max_wait = max_wait
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep = sleep
        self._last = 0.0

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / digest[:2] / digest

    def get_text(self, url: str, params: dict[str, str] | None = None) -> str:
        if params:
            url = f"{url}?{urllib.parse.urlencode(sorted(params.items()))}"
        path = self._cache_path(url)
        if path.exists():
            return path.read_text(encoding="utf-8")

        for attempt in range(self.max_retries + 1):
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            response = self.session.get(url, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After", "")
                delay = max(float(retry_after) if retry_after.isdigit() else 0, 2.0**attempt)
                self._sleep(min(delay, self.max_wait))
                continue
            if response.status_code == 404:
                text = ""
            elif not response.ok:
                raise FetchError(f"{response.status_code} {url}")
            else:
                text = response.text
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return text
        raise FetchError(f"再試行の上限に達しました: {url}")

    def get_json(self, url: str, params: dict[str, str] | None = None) -> dict:
        text = self.get_text(url, params)
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError as e:
            self._cache_path(url if not params else f"{url}?{urllib.parse.urlencode(sorted(params.items()))}").unlink(
                missing_ok=True
            )
            raise FetchError(f"JSON ではない応答です: {url}") from e

    def wikipedia_html(self, title: str, lang: str = "ja") -> str:
        """記事の HTML。存在しない記事は空文字列。"""
        quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")
        return self.get_text(f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{quoted}")
