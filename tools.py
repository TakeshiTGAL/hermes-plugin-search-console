"""Tool handlers. Each returns a JSON string and never raises (Hermes plugin contract)."""

from __future__ import annotations

import json
import logging
from typing import Callable

from .gsc_core import service
from .gsc_core.api import Client
from .gsc_core.errors import GscError, message_language

logger = logging.getLogger(__name__)

# Replaced in register() with a reader of plugins.entries.search-console-checkup.settings.
_settings: Callable[[], dict] = lambda: {}
# Replaced in tests with a factory that returns a client on recorded responses.
client_factory: Callable[[], Client] = Client


def set_settings_reader(reader: Callable[[], dict]) -> None:
    global _settings
    _settings = reader


def _run(fn, args: dict | None = None) -> str:
    settings = {}
    try:
        settings = _settings()
        return json.dumps(fn(client_factory(), settings), ensure_ascii=False)
    except GscError as exc:
        args = args or {}
        lang = message_language(args.get("language") or settings.get("language"),
                                args.get("site_url") or settings.get("default_site"))
        return json.dumps(exc.to_dict(lang), ensure_ascii=False)
    except Exception as exc:  # last resort: never crash the agent turn
        logger.exception("search-console-checkup tool failed")
        return json.dumps({"error": "unexpected_error", "message": f"{type(exc).__name__}: {exc}",
                           "fix": "Run `hermes search-console-checkup doctor` to check the setup."}, ensure_ascii=False)


def gsc_weekly_report(args: dict, **kwargs) -> str:
    return _run(lambda c, s: service.weekly(c, args.get("site_url"), s, args.get("language")), args)


def gsc_audit(args: dict, **kwargs) -> str:
    return _run(lambda c, s: service.audit(c, args.get("site_url"), s, args.get("language"), args.get("days", 28)),
                args)


def gsc_rank_changes(args: dict, **kwargs) -> str:
    return _run(lambda c, s: service.rank_changes(
        c, args.get("site_url"), s, args.get("days", 28), args.get("dimension", "query"),
        args.get("current_start"), args.get("current_end"), args.get("previous_start"), args.get("previous_end"),
        args.get("limit", 10)), args)


def gsc_query(args: dict, **kwargs) -> str:
    return _run(lambda c, s: service.query(
        c, args.get("site_url"), s, args.get("start_date"), args.get("end_date"), args.get("days", 28),
        args.get("dimensions"), args.get("filters"), args.get("row_limit", 100), args.get("data_state", "final"),
        args.get("search_type", "web")), args)


def gsc_inspect_url(args: dict, **kwargs) -> str:
    return _run(lambda c, s: service.inspect_url(c, args.get("url", ""), args.get("site_url"), s,
                                                 args.get("language")), args)


def gsc_sites(args: dict, **kwargs) -> str:
    return _run(lambda c, s: service.sites(c))


HANDLERS = {
    "gsc_weekly_report": gsc_weekly_report,
    "gsc_audit": gsc_audit,
    "gsc_rank_changes": gsc_rank_changes,
    "gsc_query": gsc_query,
    "gsc_inspect_url": gsc_inspect_url,
    "gsc_sites": gsc_sites,
}
