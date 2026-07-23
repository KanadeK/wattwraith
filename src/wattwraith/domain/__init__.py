"""Offline, explainable WattWraith domain API."""

from wattwraith.domain.analysis import Clock, SystemClock, analyze_device, reprice_report
from wattwraith.domain.frames import FrameValidationError, validate_and_normalize_frame
from wattwraith.domain.models import (
    AnalysisConfig,
    AnalysisReport,
    DetectionStatus,
    DeviceAnnotation,
    FindingKind,
    NightWindow,
    PowerReading,
    TariffPlan,
)

__all__ = [
    "AnalysisConfig",
    "AnalysisReport",
    "Clock",
    "DetectionStatus",
    "DeviceAnnotation",
    "FindingKind",
    "FrameValidationError",
    "NightWindow",
    "PowerReading",
    "SystemClock",
    "TariffPlan",
    "analyze_device",
    "reprice_report",
    "validate_and_normalize_frame",
]
