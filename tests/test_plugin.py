"""Registration matches the declarations, and the weekly cron script works on its own."""

import os
import re
import subprocess
import sys
from pathlib import Path

import search_console_plugin as plugin
from helpers import ROOT
from search_console_plugin import cli
from search_console_plugin.gsc_core import schedule


class FakeCtx:
    def __init__(self):
        self.tools, self.cli, self.commands, self.skills, self.hooks = [], [], [], [], []

    def register_tool(self, name, toolset, schema, handler, **kw):
        assert schema["name"] == name and callable(handler)
        self.tools.append(name)

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli.append(name)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands.append(name)

    def register_skill(self, name, path, description=""):
        assert Path(path).is_file()
        self.skills.append(name)

    def register_hook(self, *a, **k):
        self.hooks.append(a[0])

    def get_config(self, key, default=None):
        return {"default_site": "sc-domain:example.jp"}.get(key, default)


def _yaml_list(text, key):
    block = re.search(rf"^\s*{key}:\s*\n((?:\s+- .+\n)+)", text, re.M)
    if not block:
        return [] if re.search(rf"^\s*{key}:\s*\[\]", text, re.M) else None
    return [re.sub(r"^\s+- (name: )?", "", line).strip() for line in block.group(1).splitlines()]


def test_registration_matches_manifest():
    ctx = FakeCtx()
    plugin.register(ctx)
    manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert re.search(r"^name: search-console-checkup$", manifest, re.M)
    assert sorted(ctx.tools) == sorted(_yaml_list(manifest, "provides_tools"))
    assert ctx.hooks == [] and "provides_hooks" not in manifest and "middleware" not in manifest
    assert _yaml_list(manifest, "requires_env") == ["GSC_CREDENTIALS_FILE"]
    # The CLI command carries the plugin's name; the chat command stays short.
    assert ctx.cli == ["search-console-checkup"] and ctx.commands == ["gsc"]
    assert sorted(ctx.skills) == ["rank-tracking", "seo-audit"]


def test_settings_reach_the_tools():
    plugin.register(FakeCtx())
    assert plugin.tools._settings() == {"default_site": "sc-domain:example.jp"}


def test_weekly_script_runs_standalone_and_fails_loudly_without_key(tmp_path):
    missing = tmp_path / "nowhere" / "key.json"
    script = schedule.write_script(tmp_path, ROOT, "sc-domain:example.jp", str(missing), "auto")
    assert script.parent == tmp_path / "scripts" and script.name == "search-console-weekly-domain-example-jp.py"
    text = script.read_text(encoding="utf-8")
    assert "private_key" not in text and str(missing) in text
    env = {k: v for k, v in os.environ.items() if k != "GSC_CREDENTIALS_FILE"}
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 1
    # .jp property → the alert is in Japanese, with the screen names to open
    assert "Search Console の週次点検（sc-domain:example.jp）に失敗しました" in proc.stdout
    assert "ファイルがありません" in proc.stdout and "対処:" in proc.stdout and "「サービス アカウント」" in proc.stdout


def test_cron_command_is_script_only():
    cmd = schedule.cron_command(Path("/h/scripts/search-console-weekly-domain-example-jp.py"), "sc-domain:example.jp",
                                "telegram", "0 9 * * 1")
    assert cmd == ("hermes cron create '0 9 * * 1' --no-agent --script search-console-weekly-domain-example-jp.py "
                   "--deliver telegram --name 'Search Console weekly: sc-domain:example.jp'")
    assert schedule.script_name("https://www.example.jp/") != schedule.script_name("sc-domain:www.example.jp")


def test_slash_command_argument_parsing(monkeypatch):
    seen = {}

    def fake(fn_name):
        def run(client, site, settings, *a, **k):
            seen[fn_name] = site
            return {"message": fn_name}
        return run

    monkeypatch.setattr(cli.service, "weekly", fake("weekly"))
    monkeypatch.setattr(cli.service, "audit", fake("audit"))
    monkeypatch.setattr(cli, "Client", lambda: None)
    assert cli.slash("") == "weekly" and seen["weekly"] is None
    assert cli.slash("example.jp") == "weekly" and seen["weekly"] == "example.jp"
    assert cli.slash("audit example.jp") == "audit" and seen["audit"] == "example.jp"
