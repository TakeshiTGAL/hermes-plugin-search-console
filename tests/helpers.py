"""Shared test helpers: load the plugin as a package and replay recorded Search Console responses."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "example_jp.json").read_text(encoding="utf-8"))


def _load_plugin():
    name = "search_console_plugin"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


plugin = _load_plugin()
from search_console_plugin.gsc_core.auth import Identity  # noqa: E402

TODAY = dt.date.fromisoformat(FIXTURE["today"])


class Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


class FakeSession:
    """Answers like the Search Console API, from the recorded fixture.

    ``overrides`` maps a URL substring to a list of (status, payload) answers, consumed in order.
    """

    def __init__(self, fixture=FIXTURE, overrides=None):
        self.f = fixture
        self.overrides = {k: list(v) for k, v in (overrides or {}).items()}
        self.log = []

    def request(self, method, url, json=None, timeout=None):
        assert timeout, "every request must carry a timeout"
        self.log.append((method, url, json))
        for key, answers in self.overrides.items():
            if key in url and answers:
                return Resp(*answers.pop(0))
        if url.endswith("/sites"):
            return Resp(200, self.f["sites"])
        if url.endswith("/sitemaps"):
            return Resp(200, self.f["sitemaps"])
        if "urlInspection" in url:
            hit = self.f["inspections"].get(json["inspectionUrl"])
            return Resp(200, hit or {"inspectionResult": {"indexStatusResult": {"verdict": "PASS"}}})
        if "searchAnalytics" in url:
            if json.get("dataState") == "all" and json.get("dimensions") == ["date"]:
                return Resp(200, self.f["date_probe"])
            win = self.f["windows"].get(json["startDate"])
            if win is None:
                return Resp(200, {"responseAggregationType": "byProperty"})
            key = ",".join(json.get("dimensions") or []) or "totals"
            data = win.get(key, {"rows": []})
            start, limit = json.get("startRow", 0), json.get("rowLimit", 1000)
            if key == "totals":
                return Resp(200, data)
            return Resp(200, dict(data, rows=data["rows"][start:start + limit]))
        return Resp(404, {"error": {"code": 404, "message": "not found"}})


SA = Identity("service_account", "gsc-reader@demo-project.iam.gserviceaccount.com", "demo-project", None)

