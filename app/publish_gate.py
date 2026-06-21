"""
Confidence-based publish gate (#287).

Classifies stories by confidence_score and applies hold/warn/publish decisions.
Thresholds are configured in data/model_config.json → publish_gate.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "model_config.json"

_GATE_ENABLED = os.getenv("NEWSBRIEF_PUBLISH_GATE_ENABLED", "").lower()
_GATE_HOLD = os.getenv("NEWSBRIEF_PUBLISH_GATE_HOLD_THRESHOLD", "")
_GATE_WARN = os.getenv("NEWSBRIEF_PUBLISH_GATE_WARN_THRESHOLD", "")


class GateDecision(str, Enum):
    PUBLISH = "publish"
    WARN = "warn"
    HOLD = "hold"


@dataclass
class GateConfig:
    enabled: bool = True
    hold_threshold: float = 0.4
    warn_threshold: float = 0.65


def _load_gate_config() -> GateConfig:
    cfg = GateConfig()
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                data = json.load(f).get("publish_gate", {})
            cfg.enabled = data.get("enabled", True)
            cfg.hold_threshold = float(data.get("hold_threshold", 0.4))
            cfg.warn_threshold = float(data.get("warn_threshold", 0.65))
    except Exception as e:
        logger.warning(f"Failed to load publish_gate config, using defaults: {e}")

    # Env overrides
    if _GATE_ENABLED in ("true", "false"):
        cfg.enabled = _GATE_ENABLED == "true"
    if _GATE_HOLD:
        try:
            cfg.hold_threshold = float(_GATE_HOLD)
        except ValueError:
            pass
    if _GATE_WARN:
        try:
            cfg.warn_threshold = float(_GATE_WARN)
        except ValueError:
            pass

    return cfg


def evaluate_confidence(score: Optional[float]) -> GateDecision:
    """
    Return the gate decision for a given confidence score.

    If the gate is disabled or score is None, always returns PUBLISH.
    """
    cfg = _load_gate_config()
    if not cfg.enabled or score is None:
        return GateDecision.PUBLISH

    if score < cfg.hold_threshold:
        return GateDecision.HOLD
    if score < cfg.warn_threshold:
        return GateDecision.WARN
    return GateDecision.PUBLISH


def gate_result_to_story_fields(
    decision: GateDecision,
) -> dict:
    """
    Map a GateDecision to the story column values that should be set.

    Returns a dict with: status, processing_state, confidence_warning, failure_stage
    """
    from .processing_states import StoryProcessingState

    if decision == GateDecision.HOLD:
        return {
            "status": "held",
            "processing_state": StoryProcessingState.FAILED.value,
            "confidence_warning": False,
            "failure_stage": "confidence_gate",
        }
    if decision == GateDecision.WARN:
        return {
            "status": "active",
            "processing_state": StoryProcessingState.PUBLISHED.value,
            "confidence_warning": True,
            "failure_stage": None,
        }
    return {
        "status": "active",
        "processing_state": StoryProcessingState.PUBLISHED.value,
        "confidence_warning": False,
        "failure_stage": None,
    }
