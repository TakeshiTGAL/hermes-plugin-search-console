"""search-console-checkup for Hermes: registration."""

from __future__ import annotations

import logging
from pathlib import Path

# Hermes imports this directory as a package. pytest's collector also imports this file on its
# own (the repo root is the package), where relative imports cannot work.
if __package__:
    from . import cli, schemas, tools

logger = logging.getLogger(__name__)

TOOLSET = "search_console"
_SETTING_KEYS = ("default_site", "language")


def register(ctx) -> None:
    def read_settings() -> dict:
        out = {}
        for key in _SETTING_KEYS:
            try:
                value = ctx.get_config(key)
            except Exception:
                value = None
            if value not in (None, ""):
                out[key] = value
        return out

    tools.set_settings_reader(read_settings)
    cli.set_settings_reader(read_settings)

    for schema in schemas.ALL:
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema,
                          handler=tools.HANDLERS[schema["name"]], emoji="🔎")

    ctx.register_cli_command(
        name="search-console-checkup",
        help="Weekly SEO check from your Search Console data (doctor, weekly, audit, schedule)",
        setup_fn=cli.setup_parser,
        handler_fn=cli.handle,
        description="Read your own site's Search Console data: check setup, print the weekly check or audit, "
                    "and schedule the weekly check as a script-only cron job.",
    )
    ctx.register_command("gsc", cli.slash, description="Search Console weekly check or audit for your site",
                         args_hint="[weekly|audit] [site]")

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()) if skills_dir.is_dir() else []:
        if (child / "SKILL.md").is_file():
            ctx.register_skill(child.name, child / "SKILL.md")
