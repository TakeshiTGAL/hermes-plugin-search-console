"""One error type with a plain-language next step, so every failure tells the user what to do."""

from __future__ import annotations

import os


class GscError(Exception):
    """A failure the user can act on.

    ``code`` is a stable machine-readable id (tests and the LLM key off it), ``message`` says what
    went wrong, ``fix`` says what to do next, in the words of the Search Console / Google Cloud UI.
    ``ja`` optionally carries the same two sentences in Japanese for Japanese reports and alerts.
    """

    def __init__(self, code: str, message: str, fix: str = "", details: dict | None = None,
                 ja: tuple[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix
        self.details = details or {}
        self.ja = ja

    def parts(self, lang: str = "en") -> tuple[str, str]:
        if lang == "ja" and self.ja:
            return self.ja
        return self.message, self.fix

    def to_dict(self, lang: str = "en") -> dict:
        message, fix = self.parts(lang)
        out = {"error": self.code, "message": message}
        if fix:
            out["fix"] = fix
        if self.details:
            out["details"] = self.details
        return out

    def text(self, lang: str = "en") -> str:
        message, fix = self.parts(lang)
        if not fix:
            return message
        return f"{message}\n{'対処' if lang == 'ja' and self.ja else 'What to do'}: {fix}"

    def __str__(self) -> str:
        return self.text("en")


def message_language(requested: str | None, site: str | None = None) -> str:
    """Language for errors and alerts, where no search data is available to decide from.

    'ja'/'en' when asked; for 'auto', Japanese when the property is a .jp site or the system
    locale is Japanese, else English.
    """
    lang = (requested or "auto").lower()
    if lang in ("ja", "en"):
        return lang
    host = (site or "").lower().replace("sc-domain:", "").split("://")[-1].strip("/")
    locale = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    return "ja" if host.endswith(".jp") or host.split("/")[0].endswith(".jp") or locale.startswith("ja") else "en"
