"""`hermes search-console-checkup ...` commands and the `/gsc` chat command."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

from .gsc_core import schedule as sched
from .gsc_core import service
from .gsc_core.api import Client
from .gsc_core.auth import ENV_VAR, credentials_path, load_identity
from .gsc_core.errors import GscError, message_language
from .gsc_core.periods import find_last_final
from .gsc_core.textnorm import detect_language

logger = logging.getLogger(__name__)
PLUGIN_DIR = Path(__file__).resolve().parent
_settings: Callable[[], dict] = lambda: {}

DOCTOR = {
    "en": {
        "env": "✓ {var} = {path}",
        "key": "✓ Key file read: {who}",
        "project": " (project {id})",
        "perms": "⚠ Other users on this machine can read the key file (permissions {mode}). Run: chmod 600 {path}",
        "props": "✓ Properties this key can read: {sites}",
        "data": "✓ {site}: data readable. Last finished day {last}",
        "pending": "; {start} onward still being processed by Google",
        "done": "All good. Try: hermes search-console-checkup weekly {site}",
    },
    "ja": {
        "env": "✓ {var} = {path}",
        "key": "✓ 鍵ファイルを読めました: {who}",
        "project": "（プロジェクト {id}）",
        "perms": "⚠ このマシンのほかのユーザーも鍵ファイルを読めます（権限 {mode}）。次を実行してください: chmod 600 {path}",
        "props": "✓ この鍵で読めるプロパティ: {sites}",
        "data": "✓ {site}: データを読めました。確定している最新の日は {last}",
        "pending": "（{start} 以降は Google が集計中）",
        "done": "準備できました。次を試してください: hermes search-console-checkup weekly {site}",
    },
}


def set_settings_reader(reader: Callable[[], dict]) -> None:
    global _settings
    _settings = reader


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def setup_parser(sub) -> None:
    cmds = sub.add_subparsers(dest="gsc_command")
    d = cmds.add_parser("doctor", help="Check the key, list readable properties, and test one property")
    d.add_argument("site", nargs="?", help="Property to test, e.g. sc-domain:example.com")
    d.add_argument("--lang", choices=["auto", "en", "ja"])
    for name, helptext in (("weekly", "Print the weekly check"), ("audit", "Print the 28-day audit")):
        p = cmds.add_parser(name, help=helptext)
        p.add_argument("site", nargs="?")
        p.add_argument("--lang", choices=["auto", "en", "ja"])
        p.add_argument("--json", action="store_true", help="Print the full result as JSON")
        if name == "audit":
            p.add_argument("--days", type=int, default=28)
    s = cmds.add_parser("schedule", help="Write the weekly cron script and print the `hermes cron create` line")
    s.add_argument("site")
    s.add_argument("--deliver", default="local",
                   help="Where Hermes cron sends it: telegram, slack, discord, email, local… (default: local, "
                        "saved under ~/.hermes/cron/output/)")
    s.add_argument("--when", default="0 9 * * 1", help="Cron schedule (default: Mondays 09:00 in the Hermes time zone)")
    s.add_argument("--lang", choices=["auto", "en", "ja"], default="auto")
    sub.set_defaults(func=handle)


def handle(args) -> int:
    cmd = getattr(args, "gsc_command", None)
    settings = _settings()
    lang = message_language(getattr(args, "lang", None) or settings.get("language"),
                            getattr(args, "site", None) or settings.get("default_site"))
    try:
        if cmd == "doctor":
            return _doctor(args.site, lang)
        if cmd in ("weekly", "audit"):
            fn = service.weekly if cmd == "weekly" else service.audit
            kwargs = {"days": args.days} if cmd == "audit" else {}
            result = fn(Client(), args.site, settings, args.lang, **kwargs)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["message"])
            return 0
        if cmd == "schedule":
            return _schedule(args, message_language(getattr(args, "lang", None) or settings.get("language"),
                                                    args.site))
    except GscError as exc:
        print(f"✗ {exc.text(lang)}")
        return 1
    print("Usage: hermes search-console-checkup {doctor|weekly|audit|schedule} [site]")
    return 0


def _doctor(site: str | None, lang: str) -> int:
    t = DOCTOR[lang]
    path = credentials_path()
    print(t["env"].format(var=ENV_VAR, path=path))
    identity = load_identity()
    mode = _shared_mode(path)
    if mode:
        print(t["perms"].format(mode=mode, path=path))
    project = (t["project"].format(id=identity.project_id) if identity.project_id else "")
    print(t["key"].format(who=identity.describe(lang) + project))
    client = Client(identity)
    readable = client.readable_sites()
    if not readable:
        raise client.no_access_error(site or "(any property)")
    print(t["props"].format(sites=", ".join(readable)))
    target = client.resolve_site(site, _settings().get("default_site"))
    last_final, excluded, _ = find_last_final(client, target)
    print(t["data"].format(site=target, last=last_final.isoformat())
          + (t["pending"].format(start=excluded.start.isoformat()) if excluded else ""))
    print(t["done"].format(site=target))
    return 0


def _shared_mode(path: Path) -> str:
    """The key file's permissions as '0644' when its group or other users can read it, else ''.
    POSIX only: Windows has no such bits to check."""
    if os.name == "nt":
        return ""
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return ""
    return f"{mode:04o}" if mode & 0o044 else ""


def _schedule(args, lang: str) -> int:
    client = Client()
    site = client.resolve_site(args.site)
    report_lang = args.lang if args.lang in ("en", "ja") else (_settings().get("language") or "auto")
    alert_lang = report_lang if report_lang in ("en", "ja") else _site_language(client, site)
    script = sched.write_script(_hermes_home(), PLUGIN_DIR, site, str(credentials_path().resolve()), report_lang,
                                alert_language=alert_lang)
    cmd = sched.cron_command(script, site, args.deliver, args.when)
    if lang == "ja":
        print(f"✓ スクリプトを書きました: {script}")
        print("次の1行を実行すると、毎週の点検が登録されます:")
        print("  " + cmd)
        print("すぐ試すには: hermes cron run <上の行で表示されたジョブ ID>")
        print("※ 定期実行は Hermes の gateway（常駐プロセス）が動かします。届かない場合は hermes cron status で確かめてください。")
    else:
        print(f"✓ Wrote {script}")
        print("Run this line to register the weekly job:")
        print("  " + cmd)
        print("Test it right away with: hermes cron run <job id printed by that line>")
        print("Note: scheduled jobs are run by the Hermes gateway (background service). If nothing arrives, check "
              "hermes cron status.")
    return 0


def _site_language(client: Client, site: str) -> str:
    """Decide the alert language now, from the site's own searches (a .com site can be Japanese)."""
    try:
        rows = service.query(client, site, days=28, dimensions=["query"], row_limit=500)["rows"]
        return detect_language((r["query"], r["impressions"]) for r in rows) if rows else message_language("auto", site)
    except GscError:
        return message_language("auto", site)


def slash(raw: str) -> str:
    """`/gsc [weekly|audit] [site]` — the report without an LLM round trip."""
    parts = (raw or "").split()
    mode = parts[0] if parts and parts[0] in ("weekly", "audit") else "weekly"
    rest = parts[1:] if parts and parts[0] in ("weekly", "audit") else parts
    site = rest[0] if rest else None
    settings = _settings()
    try:
        fn = service.weekly if mode == "weekly" else service.audit
        return fn(Client(), site, settings)["message"]
    except GscError as exc:
        return exc.text(message_language(settings.get("language"), site or settings.get("default_site")))
    except Exception as exc:  # never break the chat turn
        logger.exception("/gsc failed")
        if message_language(settings.get("language"), site or settings.get("default_site")) == "ja":
            return "Search Console の点検に失敗しました。`hermes search-console-checkup doctor` で設定を確かめてください。"
        return f"Search Console check failed ({type(exc).__name__}). Run `hermes search-console-checkup doctor`."
