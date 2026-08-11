"""
Tests for #319: device-aware model resolution in SettingsService (ADR-0033).

Pure unit tests - no live Ollama or database connections. Model config and
settings are injected directly into the service's internal caches to avoid
depending on the real data/model_config.json / settings.json contents.
"""

import pytest

from app.settings import SettingsService, _get_platform_key

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MODEL_CONFIG = {
    "version": "2.1",
    "device_profiles": {
        "windows": {
            "fast": "llama3.1:8b",
            "balanced": "qwen3:14b",
            "quality": "deepseek-r1:14b",
        },
        "darwin": {
            "fast": "qwen3:4b",
            "balanced": "qwen3:14b",
            "quality": "qwen3.6:35b",
        },
    },
    "profiles": {
        "fast": {"model": "mistral:7b"},
        "balanced": {"model": "qwen2.5:14b"},
        "quality": {"model": "qwen2.5:32b"},
    },
}

SAMPLE_MODEL_CONFIG_NO_DEVICE_PROFILES = {
    "version": "2.0",
    "profiles": {
        "fast": {"model": "mistral:7b"},
        "balanced": {"model": "qwen2.5:14b"},
        "quality": {"model": "qwen2.5:32b"},
    },
}


def _service(model_config, active_profile="balanced", model_override=None):
    """Build a SettingsService with injected config, bypassing disk reads."""
    svc = SettingsService()
    svc._model_config = model_config
    svc._settings = {
        "active_profile": active_profile,
        "model_override": model_override,
    }
    return svc


@pytest.fixture(autouse=True)
def _clear_device_type_env(monkeypatch):
    """Ensure NEWSBRIEF_DEVICE_TYPE never leaks between tests."""
    monkeypatch.delenv("NEWSBRIEF_DEVICE_TYPE", raising=False)


# ---------------------------------------------------------------------------
# Platform key mapping
# ---------------------------------------------------------------------------


class TestPlatformKeyMapping:
    def test_win32_maps_to_windows(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        assert _get_platform_key() == "windows"

    def test_darwin_maps_to_darwin(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        assert _get_platform_key() == "darwin"

    def test_linux_maps_to_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        assert _get_platform_key() == "linux"

    def test_unrecognised_platform_falls_back_to_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "freebsd13")
        assert _get_platform_key() == "linux"

    def test_device_type_env_var_takes_precedence_over_sys_platform(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "darwin")
        assert _get_platform_key() == "darwin"

    def test_device_type_env_var_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "Windows")
        assert _get_platform_key() == "windows"


# ---------------------------------------------------------------------------
# get_active_model() - device-aware resolution (#319)
# ---------------------------------------------------------------------------


class TestDeviceAwareModelResolution:
    def test_windows_platform_returns_windows_models(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "windows")
        for profile, expected in [
            ("fast", "llama3.1:8b"),
            ("balanced", "qwen3:14b"),
            ("quality", "deepseek-r1:14b"),
        ]:
            svc = _service(SAMPLE_MODEL_CONFIG, active_profile=profile)
            assert svc.get_active_model() == expected

    def test_darwin_platform_returns_macos_models(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "darwin")
        for profile, expected in [
            ("fast", "qwen3:4b"),
            ("balanced", "qwen3:14b"),
            ("quality", "qwen3.6:35b"),
        ]:
            svc = _service(SAMPLE_MODEL_CONFIG, active_profile=profile)
            assert svc.get_active_model() == expected

    def test_model_override_wins_over_device_profile(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "windows")
        svc = _service(
            SAMPLE_MODEL_CONFIG,
            active_profile="balanced",
            model_override="my-custom-model:latest",
        )
        assert svc.get_active_model() == "my-custom-model:latest"

    def test_device_type_env_var_overrides_sys_platform(self, monkeypatch):
        # Real host is darwin (this Mac / most dev machines), but we simulate
        # a container claiming to run the Windows device profile.
        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "windows")
        svc = _service(SAMPLE_MODEL_CONFIG, active_profile="fast")
        assert svc.get_active_model() == "llama3.1:8b"

    def test_fallback_when_device_profiles_absent(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "darwin")
        svc = _service(
            SAMPLE_MODEL_CONFIG_NO_DEVICE_PROFILES, active_profile="balanced"
        )
        assert svc.get_active_model() == "qwen2.5:14b"

    def test_fallback_when_platform_not_in_device_profiles(self, monkeypatch):
        # "linux" has no entry in SAMPLE_MODEL_CONFIG's device_profiles
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "linux")
        svc = _service(SAMPLE_MODEL_CONFIG, active_profile="balanced")
        assert svc.get_active_model() == "qwen2.5:14b"

    def test_fallback_when_profile_not_in_platform_block(self, monkeypatch):
        # device_profiles.windows has no "custom" key -> falls back to generic
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "windows")
        config = {
            **SAMPLE_MODEL_CONFIG,
            "profiles": {
                **SAMPLE_MODEL_CONFIG["profiles"],
                "custom": {"model": "generic-custom-model"},
            },
        }
        svc = _service(config, active_profile="custom")
        assert svc.get_active_model() == "generic-custom-model"

    def test_env_var_default_when_nothing_configured(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "linux")
        monkeypatch.setenv("NEWSBRIEF_LLM_MODEL", "env-fallback-model")
        svc = _service({"profiles": {}}, active_profile="balanced")
        assert svc.get_active_model() == "env-fallback-model"


# ---------------------------------------------------------------------------
# get_device_platform()
# ---------------------------------------------------------------------------


class TestGetDevicePlatform:
    def test_returns_resolved_platform_key(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "darwin")
        svc = _service(SAMPLE_MODEL_CONFIG)
        assert svc.get_device_platform() == "darwin"


# ---------------------------------------------------------------------------
# get_model_resolution_info() - resolution source reporting (#320)
# ---------------------------------------------------------------------------


class TestModelResolutionInfo:
    def test_source_is_override_when_set(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "windows")
        svc = _service(
            SAMPLE_MODEL_CONFIG, active_profile="balanced", model_override="custom"
        )
        info = svc.get_model_resolution_info()
        assert info.model == "custom"
        assert info.source == "override"
        assert info.platform == "windows"

    def test_source_is_device_profile_when_matched(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "darwin")
        svc = _service(SAMPLE_MODEL_CONFIG, active_profile="balanced")
        info = svc.get_model_resolution_info()
        assert info.model == "qwen3:14b"
        assert info.source == "device_profile"
        assert info.platform == "darwin"

    def test_source_is_generic_profile_when_no_device_match(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "linux")
        svc = _service(SAMPLE_MODEL_CONFIG, active_profile="balanced")
        info = svc.get_model_resolution_info()
        assert info.model == "qwen2.5:14b"
        assert info.source == "generic_profile"
        assert info.platform == "linux"

    def test_source_is_env_default_when_nothing_configured(self, monkeypatch):
        monkeypatch.setenv("NEWSBRIEF_DEVICE_TYPE", "linux")
        svc = _service({"profiles": {}}, active_profile="balanced")
        info = svc.get_model_resolution_info()
        assert info.source == "env_default"
