"""Credentials: a service-account JSON key (recommended) or an OAuth ``authorized_user`` file.

Both are read from the file named by ``GSC_CREDENTIALS_FILE``. Nothing here opens a browser,
prompts, or writes a token back to disk, so scheduled and gateway runs never wait for a person
(catalog rule 12). The plugin only ever sends read requests.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from .errors import GscError

ENV_VAR = "GSC_CREDENTIALS_FILE"
READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SETUP_DOC = "https://github.com/TakeshiTGAL/hermes-plugin-search-console#setup"
# gcloud's built-in OAuth clients, as defined in the Cloud SDK's own code:
# - DEFAULT_CREDENTIALS_DEFAULT_CLIENT_ID (googlecloudsdk/api_lib/auth/util.py), used by
#   `gcloud auth application-default login` without --client-id-file;
# - CLOUDSDK_CLIENT_ID (googlecloudsdk/core/config.py), used by `gcloud auth login`, whose adc.json
#   under ~/.config/gcloud/legacy_credentials/ is an authorized_user file too.
# Refreshing tokens as either client would mean presenting this plugin as Google's own CLI (catalog rule 11).
GCLOUD_DEFAULT_CLIENT_IDS = frozenset({
    "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com",
    "32555940559.apps.googleusercontent.com",
})
KEY_STEPS_JA = ("Google Cloud コンソール →「IAM と管理」→「サービス アカウント」→ 対象のアカウント →「鍵」→"
                "「鍵を追加」→「新しい鍵を作成」→「JSON」")

_lock = threading.Lock()
_cache: dict[tuple[str, float], "Identity"] = {}


@dataclass
class Identity:
    """Who the plugin is talking to Google as."""

    kind: str  # "service_account" | "authorized_user"
    email: str  # service account address; "" for an OAuth user file
    project_id: str
    credentials: object  # google.auth credentials

    def describe(self, lang: str = "en") -> str:
        if self.kind == "service_account":
            return f"サービスアカウント {self.email}" if lang == "ja" else f"service account {self.email}"
        return "OAuth のユーザーログイン（authorized_user ファイル）" if lang == "ja" else \
            "an OAuth user login (authorized_user file)"


def credentials_path() -> Path:
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        raise GscError(
            "not_configured",
            f"{ENV_VAR} is not set, so there is no key to read Search Console with.",
            f"Create a service-account JSON key, then run: hermes config set {ENV_VAR} <full path to the key>. "
            f"Steps: {SETUP_DOC}",
            ja=(f"{ENV_VAR} が設定されていないため、Search Console を読む鍵がありません。",
                f"サービスアカウントの JSON 鍵を作り、hermes config set {ENV_VAR} <鍵ファイルのフルパス> を実行してください。"
                f"手順: {SETUP_DOC}"),
        )
    return Path(os.path.expanduser(raw))


def _read_key_file(path: Path) -> dict:
    # exists() rather than is_file(): a key handed over through a pipe or a secrets mount is fine.
    if not path.exists() or path.is_dir():
        raise GscError(
            "key_file_missing",
            f"{ENV_VAR} points to {path}, but no file is there.",
            "Check the path (it must be the full path to the downloaded .json key), or download a new "
            "key: Google Cloud console → IAM & Admin → Service accounts → your account → Keys → "
            "Add key → Create new key → JSON.",
            ja=(f"{ENV_VAR} の指す {path} にファイルがありません。",
                f"パス（ダウンロードした .json 鍵のフルパス）を確かめてください。鍵を作り直すなら: {KEY_STEPS_JA}。"),
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _unreadable(path, type(exc).__name__) from None
    if not isinstance(data, dict):
        raise _unreadable(path, "not a key object")
    return data


def _unreadable(path: Path, why: str) -> GscError:
    return GscError(
        "key_file_unreadable",
        f"Could not read {path} as a JSON key ({why}).",
        "Use the .json file exactly as Google Cloud downloaded it (do not copy its text into another file), "
        "or create a new key.",
        ja=(f"{path} を JSON の鍵として読めませんでした（{why}）。",
            f"Google Cloud からダウンロードした .json ファイルをそのまま使ってください。読めなければ鍵を作り直してください: "
            f"{KEY_STEPS_JA}。"),
    )


def load_identity() -> Identity:
    """Load (and cache per file version) the credentials named by ``GSC_CREDENTIALS_FILE``."""
    path = credentials_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    key = (str(path), mtime)
    with _lock:
        if key in _cache:
            return _cache[key]
    data = _read_key_file(path)
    identity = _identity_from_info(data, path)
    with _lock:
        _cache.clear()
        _cache[key] = identity
    return identity


def _identity_from_info(data: dict, path: Path) -> Identity:
    kind = data.get("type")
    if kind == "service_account":
        missing = [k for k in ("client_email", "private_key", "token_uri") if not data.get(k)]
        if missing:
            raise GscError("key_file_incomplete", f"{path} is a service-account key but lacks {', '.join(missing)}.",
                           "Download a fresh JSON key for the service account.",
                           ja=(f"{path} はサービスアカウントの鍵ですが、{', '.join(missing)} がありません。",
                               f"鍵を作り直してください: {KEY_STEPS_JA}。"))
        from google.oauth2 import service_account

        try:
            creds = service_account.Credentials.from_service_account_info(data, scopes=[READONLY_SCOPE])
        except (ValueError, TypeError, IndexError) as exc:  # damaged private_key
            raise _unreadable(path, f"the private key is damaged: {type(exc).__name__}") from None
        return Identity("service_account", data["client_email"], data.get("project_id", ""), creds)
    if kind == "authorized_user":
        missing = [k for k in ("client_id", "client_secret", "refresh_token") if not data.get(k)]
        if missing:
            raise GscError("key_file_incomplete", f"{path} is an OAuth user file but lacks {', '.join(missing)}.",
                           "Create the file again (README → Optional: OAuth instead of a service account).",
                           ja=(f"{path} は OAuth のユーザーファイルですが、{', '.join(missing)} がありません。",
                               "ファイルを作り直すか、サービスアカウントの鍵を使ってください。"))
        if data.get("client_id") in GCLOUD_DEFAULT_CLIENT_IDS:
            raise GscError(
                "oauth_shared_client",
                f"{path} was created with gcloud's built-in OAuth client; the plugin does not sign in as Google's CLI.",
                "Use a service-account key (recommended), or create the file with your own OAuth client: "
                "gcloud auth application-default login --client-id-file=<your client_secret.json> "
                f"--scopes={READONLY_SCOPE}",
                ja=(f"{path} は gcloud に組み込みの OAuth クライアントで作られています。このプラグインは Google の CLI になりすまして"
                    "サインインしません。",
                    "サービスアカウントの鍵を使ってください（おすすめ）。OAuth を使うなら、自分の OAuth クライアントで作り直してください。"),
            )
        from google.oauth2 import credentials as oauth_credentials

        # No scopes are passed on purpose: a refresh token granted for the broader `webmasters`
        # scope cannot be narrowed at refresh time (Google answers invalid_scope). The plugin
        # still only sends read requests.
        creds = oauth_credentials.Credentials.from_authorized_user_info(data)
        return Identity("authorized_user", "", data.get("quota_project_id", ""), creds)
    if "installed" in data or "web" in data:
        raise GscError(
            "oauth_client_file",
            f"{path} is an OAuth *client* file (client_secret_*.json), not a key the plugin can sign in with.",
            "Use a service-account JSON key instead (README → Setup). If you prefer OAuth, turn the client "
            "file into an authorized_user file first (README → Optional: OAuth).",
            ja=(f"{path} は OAuth の「クライアント」ファイル（client_secret_*.json）で、サインインに使う鍵ではありません。",
                "サービスアカウントの JSON 鍵を使ってください（README の導入手順）。"),
        )
    raise GscError(
        "key_type_unsupported",
        f"{path} has type {kind!r}; supported types are service_account and authorized_user.",
        f"Point {ENV_VAR} at a service-account JSON key.",
        ja=(f"{path} の種類（{kind!r}）には対応していません。使えるのは service_account と authorized_user です。",
            f"{ENV_VAR} にサービスアカウントの JSON 鍵を指定してください。"),
    )


def reset_cache() -> None:
    with _lock:
        _cache.clear()
