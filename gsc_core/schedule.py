"""Writes the small script a script-only Hermes cron job runs every week.

Hermes cron only runs scripts that live in ``$HERMES_HOME/scripts/`` and starts them with a
cleaned environment, so the script records two absolute paths: where this plugin is installed and
where the key file is. It holds no secret itself.
"""

from __future__ import annotations

import datetime as dt
import re
import shlex
from pathlib import Path

TEMPLATE = '''# Written by `hermes search-console-checkup schedule` on {date}. Weekly Search Console check for {site}.
# Run that command again after moving the key file or the plugin. Safe to delete.
import os
import sys

sys.path.insert(0, {plugin_dir!r})
os.environ.setdefault("GSC_CREDENTIALS_FILE", {creds!r})

from gsc_core.cron_entry import main

sys.exit(main({site!r}, {language!r}, alert_language={alert_language!r}))
'''


def script_name(site: str) -> str:
    """One file per property; Domain and URL-prefix properties of one site get different names."""
    low = site.lower()
    kind = "domain" if low.startswith("sc-domain:") else ("http" if low.startswith("http://") else "url")
    body = low.replace("sc-domain:", "").replace("https://", "").replace("http://", "")
    slug = re.sub(r"[^a-z0-9]+", "-", body).strip("-")
    return f"search-console-weekly-{kind}-{slug or 'site'}.py"


def write_script(hermes_home: Path, plugin_dir: Path, site: str, creds_path: str, language: str = "auto",
                 alert_language: str = "auto") -> Path:
    """``language`` is the report language (auto = decided from the site's searches each week).
    ``alert_language`` is fixed now, at schedule time: a failed run has no search data to decide from,
    and cron starts the script without the user's locale."""
    scripts = hermes_home / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    path = scripts / script_name(site)
    path.write_text(TEMPLATE.format(date=dt.date.today().isoformat(), site=site, plugin_dir=str(plugin_dir),
                                    creds=str(creds_path), language=language,
                                    alert_language=alert_language), encoding="utf-8")
    return path


def cron_command(script: Path, site: str, deliver: str, when: str) -> str:
    return " ".join([
        "hermes cron create", shlex.quote(when), "--no-agent", "--script", shlex.quote(script.name),
        "--deliver", shlex.quote(deliver), "--name", shlex.quote(f"Search Console weekly: {site}"),
    ])
