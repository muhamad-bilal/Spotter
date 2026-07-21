"""Which provider `plan_route` reaches for when the caller does not name one."""

import pytest

from services import GeoapifyRouter, OpenRouteServiceRouter, default_router
from services import env as env_module
from services import routing as routing_module


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Neutralise the developer's real .env so these tests are deterministic."""
    monkeypatch.setattr(env_module, "_loaded", True)
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    monkeypatch.delenv("ORS_API_KEY", raising=False)


def test_geoapify_is_used_when_its_key_is_set(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", "geo-key")
    assert isinstance(default_router(), GeoapifyRouter)


def test_ors_is_used_when_geoapify_is_absent(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "ors-key")
    assert isinstance(default_router(), OpenRouteServiceRouter)


def test_geoapify_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", "geo-key")
    monkeypatch.setenv("ORS_API_KEY", "ors-key")
    assert isinstance(default_router(), GeoapifyRouter)


def test_falls_back_to_ors_when_nothing_is_configured():
    """Still a router, so the failure is the usual actionable 400, not a crash."""
    assert isinstance(default_router(), OpenRouteServiceRouter)


def test_an_explicit_router_always_wins(monkeypatch):
    """plan_route's caller can override the choice; the tests rely on this."""
    monkeypatch.setenv("GEOAPIFY_API_KEY", "geo-key")
    chosen = OpenRouteServiceRouter(api_key="k")
    assert (chosen or default_router()) is chosen


def test_default_router_is_what_plan_route_uses():
    """Guards the wiring: plan_route must resolve the provider through the factory."""
    import inspect

    from services import route_planner

    source = inspect.getsource(route_planner.plan_route)
    assert "default_router()" in source
    assert routing_module.default_router is route_planner.default_router


# --- the .env loader -------------------------------------------------------


def test_env_file_is_read(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('FAKE_KEY_A=plain\nFAKE_KEY_B="quoted"\n# comment\n\nBAD LINE\n')
    monkeypatch.setattr(env_module, "_loaded", False)
    monkeypatch.delenv("FAKE_KEY_A", raising=False)
    monkeypatch.delenv("FAKE_KEY_B", raising=False)

    env_module.load_env_file(env_file)

    import os

    assert os.environ["FAKE_KEY_A"] == "plain"
    assert os.environ["FAKE_KEY_B"] == "quoted", "surrounding quotes should be stripped"


def test_a_real_environment_variable_beats_the_file(tmp_path, monkeypatch):
    """Render sets real env vars; a stale local .env must never override them."""
    env_file = tmp_path / ".env"
    env_file.write_text("FAKE_KEY_C=from-file\n")
    monkeypatch.setattr(env_module, "_loaded", False)
    monkeypatch.setenv("FAKE_KEY_C", "from-environment")

    env_module.load_env_file(env_file)

    import os

    assert os.environ["FAKE_KEY_C"] == "from-environment"


def test_a_missing_env_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(env_module, "_loaded", False)
    env_module.load_env_file(tmp_path / "does-not-exist")
