"""
Settings service for NewsBrief configuration management.

Manages application settings including LLM model profiles, stored in a JSON file
for simplicity and portability (no database dependency).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
MODEL_CONFIG_PATH = DATA_DIR / "model_config.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

# Default settings
DEFAULT_SETTINGS = {
    "active_profile": "balanced",
    "model_override": None,  # Optional: override profile model
}


@dataclass
class ModelInfo:
    """Information about a specific LLM model."""

    name: str
    context_window: int
    synthesis_budget: int
    output_reserved: int
    description: str
    family: str = "unknown"
    parameters: str = "unknown"
    vram_required_gb: float = 0


@dataclass
class ProfileInfo:
    """Information about a model profile."""

    id: str
    name: str
    description: str
    model: str
    expected_speed: str
    expected_time_per_story: str
    quality_level: str
    use_cases: List[str]


class SettingsService:
    """Service for managing application settings and model profiles."""

    def __init__(self):
        self._model_config: Optional[Dict[str, Any]] = None
        self._settings: Optional[Dict[str, Any]] = None

    def _load_model_config(self) -> Dict[str, Any]:
        """Load model configuration from JSON file."""
        if self._model_config is None:
            try:
                with open(MODEL_CONFIG_PATH, "r") as f:
                    self._model_config = json.load(f)
                logger.debug(
                    f"Loaded model config version {self._model_config.get('version', 'unknown')}"
                )
            except FileNotFoundError:
                logger.error(f"Model config not found at {MODEL_CONFIG_PATH}")
                self._model_config = {"models": {}, "profiles": {}}
            except json.JSONDecodeError as e:
                logger.error(f"Invalid model config JSON: {e}")
                self._model_config = {"models": {}, "profiles": {}}
        return self._model_config

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from JSON file, creating with defaults if not exists."""
        if self._settings is None:
            try:
                if SETTINGS_PATH.exists():
                    with open(SETTINGS_PATH, "r") as f:
                        self._settings = json.load(f)
                    # Merge with defaults for any missing keys
                    for key, value in DEFAULT_SETTINGS.items():
                        if key not in self._settings:
                            self._settings[key] = value
                else:
                    self._settings = DEFAULT_SETTINGS.copy()
                    self._save_settings()
                    logger.info(f"Created default settings at {SETTINGS_PATH}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid settings JSON: {e}, using defaults")
                self._settings = DEFAULT_SETTINGS.copy()
        return self._settings

    def _save_settings(self) -> bool:
        """Save current settings to JSON file."""
        try:
            # Ensure data directory exists
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_PATH, "w") as f:
                json.dump(self._settings, f, indent=2)
            logger.debug(f"Saved settings to {SETTINGS_PATH}")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    def reload(self) -> None:
        """Force reload of all configuration."""
        self._model_config = None
        self._settings = None
        logger.info("Settings and model config reloaded")

    # -------------------------------------------------------------------------
    # Profile Management
    # -------------------------------------------------------------------------

    def get_available_profiles(self) -> List[ProfileInfo]:
        """Get list of all available model profiles."""
        config = self._load_model_config()
        profiles = []
        for profile_id, profile_data in config.get("profiles", {}).items():
            profiles.append(
                ProfileInfo(
                    id=profile_id,
                    name=profile_data.get("name", profile_id),
                    description=profile_data.get("description", ""),
                    model=profile_data.get("model", ""),
                    expected_speed=profile_data.get("expected_speed", "unknown"),
                    expected_time_per_story=profile_data.get(
                        "expected_time_per_story", "unknown"
                    ),
                    quality_level=profile_data.get("quality_level", "unknown"),
                    use_cases=profile_data.get("use_cases", []),
                )
            )
        return profiles

    def get_active_profile(self) -> str:
        """Get the currently active profile ID."""
        settings = self._load_settings()
        return settings.get("active_profile", "balanced")

    def set_active_profile(self, profile_id: str) -> bool:
        """
        Set the active profile.

        Args:
            profile_id: Profile ID (fast, balanced, quality)

        Returns:
            True if successful, False otherwise
        """
        config = self._load_model_config()
        if profile_id not in config.get("profiles", {}):
            logger.error(f"Invalid profile ID: {profile_id}")
            return False

        settings = self._load_settings()
        settings["active_profile"] = profile_id
        settings["model_override"] = None  # Clear any override when switching profiles
        self._settings = settings

        if self._save_settings():
            logger.info(f"Active profile changed to: {profile_id}")
            return True
        return False

    def get_profile_info(
        self, profile_id: Optional[str] = None
    ) -> Optional[ProfileInfo]:
        """Get detailed information about a profile."""
        if profile_id is None:
            profile_id = self.get_active_profile()

        config = self._load_model_config()
        profile_data = config.get("profiles", {}).get(profile_id)
        if not profile_data:
            return None

        return ProfileInfo(
            id=profile_id,
            name=profile_data.get("name", profile_id),
            description=profile_data.get("description", ""),
            model=profile_data.get("model", ""),
            expected_speed=profile_data.get("expected_speed", "unknown"),
            expected_time_per_story=profile_data.get(
                "expected_time_per_story", "unknown"
            ),
            quality_level=profile_data.get("quality_level", "unknown"),
            use_cases=profile_data.get("use_cases", []),
        )

    # -------------------------------------------------------------------------
    # Model Management
    # -------------------------------------------------------------------------

    def get_available_models(self) -> List[ModelInfo]:
        """Get list of all configured models."""
        config = self._load_model_config()
        models = []
        for model_name, model_data in config.get("models", {}).items():
            models.append(
                ModelInfo(
                    name=model_name,
                    context_window=model_data.get("context_window", 8192),
                    synthesis_budget=model_data.get("synthesis_budget", 6000),
                    output_reserved=model_data.get("output_reserved", 1000),
                    description=model_data.get("description", ""),
                    family=model_data.get("family", "unknown"),
                    parameters=model_data.get("parameters", "unknown"),
                    vram_required_gb=model_data.get("vram_required_gb", 0),
                )
            )
        return models

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get detailed information about a specific model."""
        config = self._load_model_config()
        model_data = config.get("models", {}).get(model_name)
        if not model_data:
            return None

        return ModelInfo(
            name=model_name,
            context_window=model_data.get("context_window", 8192),
            synthesis_budget=model_data.get("synthesis_budget", 6000),
            output_reserved=model_data.get("output_reserved", 1000),
            description=model_data.get("description", ""),
            family=model_data.get("family", "unknown"),
            parameters=model_data.get("parameters", "unknown"),
            vram_required_gb=model_data.get("vram_required_gb", 0),
        )

    def get_active_model(self) -> str:
        """
        Get the model name to use based on current settings.

        Resolution order:
        1. Model override (if set)
        2. Active profile's model
        3. Environment variable NEWSBRIEF_LLM_MODEL
        4. Fallback to llama3.1:8b
        """
        settings = self._load_settings()

        # Check for explicit override
        model_override = settings.get("model_override")
        if model_override:
            logger.debug(f"Using model override: {model_override}")
            return model_override

        # Get from active profile
        profile_id = settings.get("active_profile", "balanced")
        config = self._load_model_config()
        profile_data = config.get("profiles", {}).get(profile_id)

        if profile_data:
            model = profile_data.get("model")
            if model:
                logger.debug(f"Using model from profile '{profile_id}': {model}")
                return model

        # Fallback to environment variable or default
        env_model = os.getenv("NEWSBRIEF_LLM_MODEL", "llama3.1:8b")
        logger.debug(f"Using fallback model: {env_model}")
        return env_model

    def set_model_override(self, model_name: Optional[str]) -> bool:
        """
        Set a model override that takes precedence over the profile.

        Args:
            model_name: Model name to use, or None to clear override

        Returns:
            True if successful
        """
        settings = self._load_settings()
        settings["model_override"] = model_name
        self._settings = settings
        return self._save_settings()

    # -------------------------------------------------------------------------
    # Configuration Access
    # -------------------------------------------------------------------------

    def get_model_config(self) -> Dict[str, Any]:
        """Get the full model configuration dictionary."""
        return self._load_model_config()

    def get_synthesis_strategy_config(self, strategy: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a synthesis strategy."""
        config = self._load_model_config()
        return config.get("synthesis_strategies", {}).get(strategy)

    def get_defaults(self) -> Dict[str, Any]:
        """Get default configuration values."""
        config = self._load_model_config()
        return config.get("defaults", {})


# Singleton instance
_settings_service: Optional[SettingsService] = None


def get_settings_service() -> SettingsService:
    """Get or create the settings service singleton."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service


# Convenience functions
def get_active_model() -> str:
    """Get the currently active model name."""
    return get_settings_service().get_active_model()


def get_active_profile() -> str:
    """Get the currently active profile ID."""
    return get_settings_service().get_active_profile()


def set_active_profile(profile_id: str) -> bool:
    """Set the active profile."""
    return get_settings_service().set_active_profile(profile_id)
