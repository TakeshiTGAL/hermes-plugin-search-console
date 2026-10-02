"""Failures must say what to do next, and never hang or crash the agent."""

import json

import pytest

from helpers import TODAY
from search_console_plugin import tools
from search_console_plugin.gsc_core import auth, service
from search_console_plugin.gsc_core.errors import GscError


@pytest.fixture(autouse=True)
def _fresh_auth_cache():
    auth.reset_cache()
    yield
    auth.reset_cache()


def test_no_key_configured(monkeypatch):
    monkeypatch.delenv("GSC_CREDENTIALS_FILE", raising=False)
    with pytest.raises(GscError) as e:
        auth.load_identity()
    assert e.value.code == "not_configured"
    assert "GSC_CREDENTIALS_FILE" in e.value.fix and "#setup" in e.value.fix


def test_key_path_points_nowhere(monkeypatch, tmp_path):
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(tmp_path / "missing.json"))
    with pytest.raises(GscError) as e:
        auth.load_identity()
    assert e.value.code == "key_file_missing"
    assert "Service accounts → your account → Keys" in e.value.fix


def test_oauth_client_file_is_explained(monkeypatch, tmp_path):
    f = tmp_path / "client_secret.json"
    f.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}))
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(f))
    with pytest.raises(GscError) as e:
        auth.load_identity()
    assert e.value.code == "oauth_client_file"


def test_not_json(monkeypatch, tmp_path):
    f = tmp_path / "key.json"
    f.write_text("not json")
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(f))
    with pytest.raises(GscError) as e:
        auth.load_identity()
    assert e.value.code == "key_file_unreadable"


def test_authorized_user_file_loads_without_forcing_scopes(monkeypatch, tmp_path):
    f = tmp_path / "user.json"
    f.write_text(json.dumps({"type": "authorized_user", "client_id": "cid", "client_secret": "cs",
                             "refresh_token": "rt"}))
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(f))
    ident = auth.load_identity()
    assert ident.kind == "authorized_user"
    # A token granted for `webmasters` cannot be narrowed at refresh time (invalid_scope), so none is set.
    assert not getattr(ident.credentials, "scopes", None)


def test_service_account_key_loads_with_readonly_scope(monkeypatch, tmp_path):
    rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    from cryptography.hazmat.primitives import serialization

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    f = tmp_path / "sa.json"
    f.write_text(json.dumps({"type": "service_account", "project_id": "demo", "private_key_id": "k1",
                             "private_key": pem, "client_email": "bot@demo.iam.gserviceaccount.com",
                             "client_id": "1", "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(f))
    ident = auth.load_identity()
    assert ident.email == "bot@demo.iam.gserviceaccount.com"
    assert ident.credentials.scopes == [auth.READONLY_SCOPE]


def test_property_without_permission_names_the_email_and_the_screen(make_client):
    c = make_client()
    with pytest.raises(GscError) as e:
        service.weekly(c, "sc-domain:not-shared.example", today=TODAY)
    err = e.value
    assert err.code == "no_access"
    assert "gsc-reader@demo-project.iam.gserviceaccount.com" in err.fix
    assert "Settings → Users and permissions → Add user" in err.fix
    assert "sc-domain:example.jp" in err.fix  # what it CAN read
    assert "other.example" not in err.fix  # unverified entries are not offered


def test_403_from_google_on_a_listed_property(make_client):
    body = {"error": {"code": 403, "message": "User does not have sufficient permission for site",
                      "errors": [{"reason": "forbidden"}], "status": "PERMISSION_DENIED"}}
    c = make_client(searchAnalytics=[(403, body)])
    with pytest.raises(GscError) as e:
        service.weekly(c, "example.jp", today=TODAY)
    assert e.value.code == "no_access" and "permission" in e.value.details["google_message"]


def test_api_not_enabled(make_client):
    body = {"error": {"code": 403, "message": "Google Search Console API has not been used in project 123",
                      "status": "PERMISSION_DENIED",
                      "details": [{"reason": "SERVICE_DISABLED",
                                   "metadata": {"activationUrl": "https://console.developers.google.com/apis/x"}}]}}
    c = make_client(**{"/sites": [(403, body)]})
    with pytest.raises(GscError) as e:
        service.sites(c)
    assert e.value.code == "api_disabled"
    assert "APIs & Services → Library" in e.value.fix and "activationUrl" not in e.value.fix
    assert "https://console.developers.google.com/apis/x" in e.value.fix


def test_retries_transient_errors_then_succeeds(make_client):
    c = make_client(**{"/sites": [(503, {}), (200, {"siteEntry": [{"siteUrl": "sc-domain:a.example",
                                                                   "permissionLevel": "siteOwner"}]})]})
    assert service.sites(c)["properties"] == [{"site_url": "sc-domain:a.example", "permission": "siteOwner"}]


def test_gives_up_after_two_retries(make_client):
    c = make_client(**{"/sites": [(503, {})] * 3})
    with pytest.raises(GscError) as e:
        service.sites(c)
    assert e.value.code == "google_unavailable" and c.calls == 3


def test_url_inspection_refused_does_not_break_the_report(make_client):
    c = make_client(urlInspection=[(403, {"error": {"code": 403, "message": "Forbidden"}})])
    r = service.weekly(c, "example.jp", today=TODAY)
    assert r["notes"][0]["code"] == "inspection_refused"
    assert "「フル」" in r["message"]


def test_tool_handlers_return_json_errors_never_raise(monkeypatch):
    monkeypatch.delenv("GSC_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr(tools, "client_factory", tools.Client)
    out = json.loads(tools.gsc_weekly_report({}))
    assert out["error"] == "not_configured" and out["fix"]

    def boom():
        raise RuntimeError("surprise")

    monkeypatch.setattr(tools, "client_factory", boom)
    out = json.loads(tools.gsc_sites({}))
    assert out["error"] == "unexpected_error" and "doctor" in out["fix"]


def test_bad_arguments_are_explained(client):
    with pytest.raises(GscError) as e:
        service.query(client, "example.jp", dimensions=["keyword"], today=TODAY)
    assert e.value.code == "bad_argument" and "searchAppearance" in e.value.fix
    with pytest.raises(GscError):
        service.inspect_url(client, "example.jp/no-scheme")


class _RaisingSession:
    def __init__(self, exc):
        self.exc = exc

    def request(self, *a, **k):
        raise self.exc


def test_revoked_or_deleted_key_is_explained():
    import google.auth.exceptions as gexc

    from helpers import SA
    from search_console_plugin.gsc_core.api import Client

    c = Client(SA, _RaisingSession(gexc.RefreshError("invalid_grant: Invalid JWT Signature.")), sleep=lambda s: None)
    with pytest.raises(GscError) as e:
        service.sites(c)
    assert e.value.code == "auth_failed" and "Keys" in e.value.fix and "clock" in e.value.fix


def test_network_down_is_explained_and_bugs_are_not_hidden():
    import requests

    from helpers import SA
    from search_console_plugin.gsc_core.api import Client

    c = Client(SA, _RaisingSession(requests.ConnectionError("dns")), sleep=lambda s: None)
    with pytest.raises(GscError) as e:
        service.sites(c)
    assert e.value.code == "network_error"
    c = Client(SA, _RaisingSession(TypeError("bug")), sleep=lambda s: None)
    with pytest.raises(TypeError):
        service.sites(c)
