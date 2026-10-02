"""Thin read-only client for the Search Console API (Search Analytics, Sites, Sitemaps, URL Inspection).

Every request has a timeout and at most two short retries, so an unattended run cannot hang.
Google's errors are turned into :class:`GscError` with the next step spelled out in the words of
the Search Console and Google Cloud screens.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Callable, Iterable

from .auth import Identity, load_identity
from .errors import GscError

API = "https://www.googleapis.com/webmasters/v3"
INSPECT_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
TIMEOUT = 30
MAX_ROWS_PER_PAGE = 25000
RETRY_STATUS = {429, 500, 502, 503, 504}

ADD_USER_STEPS = (
    "In Search Console open the property → Settings → Users and permissions → Add user, paste {who}, "
    "and choose the permission Full (needed for URL Inspection; the plugin itself only reads). "
    "Changes can take a few minutes to apply."
)
ADD_USER_STEPS_JA = (
    "Search Console で対象のプロパティを開き、「設定」→「ユーザーと権限」→「ユーザーを追加」で {who} を貼り、"
    "権限は「フル」を選んでください（URL 検査に必要。このプラグインは読み取りしかしません）。反映まで数分かかることがあります。"
)


def _who(identity: Identity) -> str:
    return identity.email if identity.email else "the Google account in your OAuth file"


def _who_ja(identity: Identity) -> str:
    return identity.email if identity.email else "OAuth ファイルの Google アカウント"


class Client:
    def __init__(self, identity: Identity | None = None, session=None, sleep: Callable[[float], None] = time.sleep):
        self.identity = identity or load_identity()
        if session is None:
            from google.auth.transport.requests import AuthorizedSession

            session = AuthorizedSession(self.identity.credentials, refresh_timeout=TIMEOUT)
        self.session = session
        self._sleep = sleep
        self._sites_cache: list[dict] | None = None
        self.calls = 0  # request counter, reported so users can see quota use

    # ------------------------------------------------------------------ transport
    def _request(self, method: str, url: str, body: dict | None = None, site: str | None = None) -> dict:
        delays = (1.0, 3.0)
        attempt = 0
        while True:
            self.calls += 1
            try:
                resp = self.session.request(method, url, json=body, timeout=TIMEOUT)
            except Exception as exc:
                if not _is_transport_error(exc):
                    raise  # a bug, not a network problem: let it surface as one
                raise self._transport_error(exc) from None
            status = getattr(resp, "status_code", 0)
            if 200 <= status < 300:
                try:
                    return resp.json() if getattr(resp, "content", b"x") else {}
                except ValueError:
                    return {}
            if status in RETRY_STATUS and attempt < len(delays):
                self._sleep(delays[attempt])
                attempt += 1
                continue
            raise self._http_error(status, _json_or_empty(resp), site)

    def _transport_error(self, exc: Exception) -> GscError:
        name = type(exc).__name__
        text = str(exc)
        if name == "RefreshError" or "invalid_grant" in text or "invalid_scope" in text:
            if "invalid_scope" in text:
                return GscError("auth_failed", "Google refused the requested access scope for this login.",
                                "Create the authorized_user file again with the webmasters or webmasters.readonly scope.",
                                ja=("この OAuth ログインでは、要求した権限の範囲を Google が拒否しました。",
                                    "webmasters か webmasters.readonly の範囲で authorized_user ファイルを作り直してください。"))
            if self.identity.kind == "service_account":
                fix = ("The key may have been deleted or disabled, or this computer's clock is wrong. "
                       "Check Google Cloud console → IAM & Admin → Service accounts → Keys, create a new JSON key "
                       "if needed, and make sure the system clock is set automatically.")
                fix_ja = ("鍵が削除・無効化されたか、このコンピューターの時計がずれています。Google Cloud コンソールの「IAM と管理」→"
                          "「サービス アカウント」→「鍵」を確かめ、必要なら新しい JSON 鍵を作ってください。時計は自動設定にしてください。")
            else:
                fix = ("The OAuth refresh token was revoked or expired (apps left in 'Testing' publishing status "
                       "expire tokens after 7 days). Create the authorized_user file again, or switch to a "
                       "service-account key, which does not expire.")
                fix_ja = ("OAuth の更新トークンが取り消されたか期限切れです（公開ステータスが「テスト」のアプリは7日で切れます）。"
                          "ファイルを作り直すか、期限のないサービスアカウントの鍵に切り替えてください。")
            return GscError("auth_failed", "Google did not accept the stored credentials.", fix,
                            ja=("保存されている資格情報を Google が受け付けませんでした。", fix_ja))
        if "Timeout" in name or "timed out" in text.lower():
            return GscError("network_timeout", f"Search Console did not answer within {TIMEOUT}s.",
                            "Try again later; if it keeps happening, check this machine's internet connection or proxy.",
                            ja=(f"Search Console が {TIMEOUT} 秒以内に応答しませんでした。",
                                "時間をおいて再実行してください。続く場合はこのマシンのネット接続やプロキシを確かめてください。"))
        return GscError("network_error", f"Could not reach Google ({name}).",
                        "Check this machine's internet connection, proxy or firewall, then try again.",
                        details={"exception": name},
                        ja=("Google に接続できませんでした。",
                            "このマシンのネット接続・プロキシ・ファイアウォールを確かめて、再実行してください。"))

    def _http_error(self, status: int, payload: dict, site: str | None) -> GscError:
        err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        message = str(err.get("message") or payload.get("error_description") or f"HTTP {status}")
        reasons = {str(e.get("reason", "")) for e in err.get("errors", []) if isinstance(e, dict)}
        activation = ""
        for d in err.get("details", []) or []:
            if isinstance(d, dict):
                reasons.add(str(d.get("reason", "")))
                activation = activation or (d.get("metadata") or {}).get("activationUrl", "")
        if status == 403 and (reasons & {"SERVICE_DISABLED", "accessNotConfigured"} or "has not been used" in message):
            project = self.identity.project_id or "the key's project"
            project_ja = self.identity.project_id or "鍵のプロジェクト"
            fix = (f"Turn on the API for {project}: Google Cloud console → APIs & Services → Library → "
                   "search 'Google Search Console API' → Enable. Wait a few minutes, then run again.")
            fix_ja = (f"{project_ja} で API を有効にしてください: Google Cloud コンソール →「API とサービス」→「ライブラリ」→"
                      "「Google Search Console API」→「有効にする」。数分待ってから再実行してください。")
            if activation:
                fix += f" Direct link: {activation}"
                fix_ja += f" 直接のリンク: {activation}"
            return GscError("api_disabled", "The Google Search Console API is not enabled for this key's project.", fix,
                            ja=("この鍵のプロジェクトで Google Search Console API が有効になっていません。", fix_ja))
        if status in (403, 404) and site:
            return self.no_access_error(site, google_message=message)
        if status == 401:
            return GscError("auth_failed", "Google rejected the credentials (401).",
                            "Create a new JSON key for the service account and point GSC_CREDENTIALS_FILE at it.",
                            ja=("Google が資格情報を拒否しました（401）。",
                                "サービスアカウントの JSON 鍵を作り直し、GSC_CREDENTIALS_FILE をそのファイルに向けてください。"))
        if status == 429:
            return GscError("quota_exceeded", "Search Console's request quota was hit.",
                            "Wait a few minutes and run again. The weekly check uses about 13 requests per site.",
                            ja=("Search Console の利用上限に達しました。",
                                "数分おいて再実行してください。週次点検は1サイトあたり約13回の問い合わせを使います。"))
        if status >= 500:
            return GscError("google_unavailable", f"Search Console returned an error ({status}).", "Try again later.",
                            ja=(f"Search Console がエラーを返しました（{status}）。", "時間をおいて再実行してください。"))
        # Google's own wording stays in details (and in the English message), so a Japanese report or
        # alert does not carry an untranslated fragment.
        return GscError("bad_request", f"Search Console refused the request: {message}",
                        "Check the dates (YYYY-MM-DD, within the last 16 months) and the dimension names.",
                        details={"status": status, "google_message": message},
                        ja=(f"Search Console がこの問い合わせを受け付けませんでした（HTTP {status}）。",
                            "日付（YYYY-MM-DD の形で、過去16か月以内）と、集計の切り口（query・page などの名前）を確かめてください。"))

    def no_access_error(self, site: str, google_message: str = "") -> GscError:
        readable = []
        try:
            readable = [s["siteUrl"] for s in self.sites() if s.get("permissionLevel") != "siteUnverifiedUser"]
        except GscError:
            pass
        email = self.identity.email
        fix = ADD_USER_STEPS.format(who=email or "the e-mail of that Google account")
        fix_ja = ADD_USER_STEPS_JA.format(who=email or "その Google アカウントのメールアドレス")
        if readable:
            fix += " Properties this key can read now: " + ", ".join(readable) + "."
            fix_ja += "この鍵でいま読めるプロパティ: " + "、".join(readable) + "。"
        else:
            fix += " This key cannot read any property yet."
            fix_ja += "この鍵で読めるプロパティはまだありません。"
        if not site.startswith("sc-domain:"):
            fix += (" If the property is a Domain property, its name is sc-domain:example.com "
                    "(no https://, no trailing slash).")
            fix_ja += "ドメイン プロパティなら、名前は sc-domain:example.com の形です（https:// も末尾の / も付けません）。"
        details = {"site_url": site, "credential": self.identity.describe()}
        if google_message:
            details["google_message"] = google_message
        subject = email or "The Google account in your OAuth file"
        return GscError("no_access", f"{subject} has no access to the Search Console property {site}.", fix, details,
                         ja=(f"{_who_ja(self.identity)} には Search Console のプロパティ {site} を読む権限がありません。", fix_ja))

    # ------------------------------------------------------------------ endpoints
    def sites(self) -> list[dict]:
        if self._sites_cache is None:
            data = self._request("GET", f"{API}/sites")
            self._sites_cache = list(data.get("siteEntry") or [])
        return self._sites_cache

    def readable_sites(self) -> list[str]:
        return sorted(s["siteUrl"] for s in self.sites() if s.get("permissionLevel") != "siteUnverifiedUser")

    def resolve_site(self, wanted: str | None, default: str | None = None) -> str:
        """Turn 'example.com', 'https://example.com', or an exact property name into the property name."""
        wanted = (wanted or default or "").strip()
        readable = self.readable_sites()
        if not wanted:
            if len(readable) == 1:
                return readable[0]
            if not readable:
                raise self.no_access_error("(none given)")
            raise GscError("site_required", "This key can read several properties; say which one to use.",
                           "Pass site_url (or set the plugin setting default_site) to one of: " + ", ".join(readable),
                           ja=("この鍵では複数のプロパティが読めます。どれを使うか指定してください。",
                               "site_url（または設定の default_site）に次のどれかを指定してください: " + "、".join(readable)))
        if wanted in readable:
            return wanted
        for candidate in _candidates(wanted):
            if candidate in readable:
                return candidate
        raise self.no_access_error(wanted)

    def search_analytics(self, site: str, body: dict) -> dict:
        url = f"{API}/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query"
        return self._request("POST", url, body, site=site)

    def search_analytics_all(self, site: str, body: dict, max_rows: int = 100_000) -> tuple[list[dict], dict, bool]:
        """Page through results. Returns (rows, metadata, truncated)."""
        rows: list[dict] = []
        metadata: dict = {}
        start = 0
        page = min(MAX_ROWS_PER_PAGE, max_rows)
        while True:
            data = self.search_analytics(site, dict(body, rowLimit=page, startRow=start))
            metadata = data.get("metadata") or metadata
            chunk = data.get("rows") or []
            rows.extend(chunk)
            if len(chunk) < page:
                return rows, metadata, False
            start += len(chunk)
            if start >= max_rows:
                return rows, metadata, True

    def sitemaps(self, site: str) -> list[dict]:
        data = self._request("GET", f"{API}/sites/{urllib.parse.quote(site, safe='')}/sitemaps", site=site)
        return list(data.get("sitemap") or [])

    def inspect(self, site: str, url: str, language: str = "en") -> dict:
        body = {"inspectionUrl": url, "siteUrl": site, "languageCode": "ja" if language == "ja" else "en-US"}
        data = self._request("POST", INSPECT_API, body, site=site)
        return data.get("inspectionResult") or {}


def _is_transport_error(exc: Exception) -> bool:
    """Network, DNS, TLS, timeout or token-refresh failures (requests / urllib3 / google-auth)."""
    module = type(exc).__module__ or ""
    return isinstance(exc, (OSError, TimeoutError)) or module.startswith(("requests", "urllib3", "google.auth"))


def _json_or_empty(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _candidates(wanted: str) -> Iterable[str]:
    text = wanted.strip()
    if text.startswith("sc-domain:"):
        host = text[len("sc-domain:"):]
    else:
        parsed = urllib.parse.urlparse(text if "://" in text else "https://" + text)
        host = parsed.hostname or text
        path = parsed.path or "/"
        if "://" in text:
            yield f"{parsed.scheme}://{parsed.netloc}{path if path.endswith('/') else path + '/'}"
    host = host.lower().strip("/")
    bare = host[4:] if host.startswith("www.") else host
    yield f"sc-domain:{bare}"
    for scheme in ("https", "http"):
        yield f"{scheme}://{host}/"
        yield f"{scheme}://www.{bare}/"
        yield f"{scheme}://{bare}/"
