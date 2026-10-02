"""Entry point for the script-only (no LLM) weekly cron job written by ``hermes search-console-checkup schedule``.

stdout is delivered verbatim by Hermes cron. On failure the actionable message is printed and the
exit code is non-zero, so Hermes delivers it as a failed-run alert instead of staying silent.
"""

from __future__ import annotations

import sys

from .api import Client
from .errors import GscError, message_language
from .service import weekly


def main(site: str, language: str = "auto", alert_language: str | None = None) -> int:
    try:
        result = weekly(Client(), site=site, settings={"language": language})
    except GscError as exc:
        lang = alert_language if alert_language in ("en", "ja") else message_language(language, site)
        head = (f"Search Console の週次点検（{site}）に失敗しました。" if lang == "ja"
                else f"Search Console weekly check failed for {site}.")
        print(f"{head}\n{exc.text(lang)}")
        return 1
    print(result["message"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "auto"))
