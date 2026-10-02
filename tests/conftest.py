"""pytest fixtures. Helpers live in helpers.py (importable under --import-mode=importlib)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from helpers import SA, FakeSession  # noqa: E402  (also loads the plugin package)


@pytest.fixture
def client():
    from search_console_plugin.gsc_core.api import Client

    return Client(SA, FakeSession(), sleep=lambda s: None)


@pytest.fixture
def make_client():
    from search_console_plugin.gsc_core.api import Client

    def make(**overrides):
        return Client(SA, FakeSession(overrides=overrides), sleep=lambda s: None)

    return make
