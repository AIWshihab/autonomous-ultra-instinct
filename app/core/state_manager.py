from typing import Mapping

from app.adapters.base_adapter import BaseAdapter
from app.adapters.linux_adapter import LinuxAdapter
from app.adapters.macos_adapter import MacOSAdapter
from app.adapters.windows_adapter import WindowsAdapter
from app.detectors.base_detector import BaseDetector
from app.detectors.rule_based import RuleBasedDetector
from app.core.scoring import ScoringEngine
from app.models.schemas import StateSnapshot


class InvalidPlatformError(ValueError):
    pass


class InvalidModeError(ValueError):
    pass


class StateManager:
    """Manage platform adapter selection and snapshot collection mode."""

    default_platform = "linux"
    default_mode = "mock"

    def __init__(
        self,
        adapters: Mapping[str, BaseAdapter] | None = None,
        detector: BaseDetector | None = None,
        scoring_engine: ScoringEngine | None = None,
    ) -> None:
        self.adapters = dict(
            adapters
            or {
                "linux": LinuxAdapter(),
                "windows": WindowsAdapter(),
                "macos": MacOSAdapter(),
            }
        )
        self.detector = detector or RuleBasedDetector()
        self.scoring_engine = scoring_engine or ScoringEngine()

    def collect_snapshot(self, platform: str | None = None, mode: str | None = None) -> StateSnapshot:
        adapter = self.get_adapter(platform)
        normalized_mode = self.normalize_mode(mode)
        snapshot = adapter.collect_snapshot(mode=normalized_mode)
        issues = sorted(
            self.detector.detect(snapshot),
            key=lambda issue: (-issue.priority_score, issue.id),
        )
        health_score, risk_score, issue_summary = self.scoring_engine.summarize_issues(issues)
        return snapshot.model_copy(
            update={
                "issues": issues,
                "health_score": health_score,
                "risk_score": risk_score,
                "issue_summary": issue_summary,
            }
        )

    def get_adapter(self, platform: str | None = None) -> BaseAdapter:
        normalized_platform = self.normalize_platform(platform)
        adapter = self.adapters.get(normalized_platform)
        if adapter is None:
            supported_platforms = ", ".join(self.adapters.keys())
            raise InvalidPlatformError(
                f"Unsupported platform '{normalized_platform}'. Supported platforms: {supported_platforms}."
            )
        return adapter

    def normalize_platform(self, platform: str | None = None) -> str:
        if platform is None:
            return self.default_platform
        normalized = platform.strip().lower()
        if not normalized:
            return self.default_platform
        return normalized

    def normalize_mode(self, mode: str | None = None) -> str:
        if mode is None:
            return self.default_mode
        normalized = mode.strip().lower()
        if not normalized:
            return self.default_mode
        if normalized not in {"mock", "live"}:
            raise InvalidModeError(
                f"Unsupported mode '{normalized}'. Supported modes: mock, live."
            )
        return normalized
