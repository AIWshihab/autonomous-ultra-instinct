import pytest

from app.adapters.linux_adapter import LinuxAdapter
from app.adapters.macos_adapter import MacOSAdapter
from app.adapters.windows_adapter import WindowsAdapter
from app.core.state_manager import InvalidModeError, InvalidPlatformError, StateManager


def test_state_manager_selects_correct_adapter_for_each_platform():
    manager = StateManager()

    assert isinstance(manager.get_adapter("linux"), LinuxAdapter)
    assert isinstance(manager.get_adapter("windows"), WindowsAdapter)
    assert isinstance(manager.get_adapter("macos"), MacOSAdapter)


def test_state_manager_defaults_to_linux_adapter():
    manager = StateManager()

    snapshot = manager.collect_snapshot()

    assert snapshot.system_info.os_name == "Linux"
    assert any(issue.type == "SERVICE_DOWN" for issue in snapshot.issues)


def test_state_manager_live_mode_for_windows_falls_back_to_mock_snapshot():
    manager = StateManager()

    snapshot = manager.collect_snapshot(platform="windows", mode="live")

    assert snapshot.system_info.os_name == "Windows"


def test_state_manager_normalizes_blank_mode_to_mock():
    manager = StateManager()

    assert manager.normalize_mode("") == "mock"


def test_state_manager_raises_for_invalid_platform():
    manager = StateManager()

    with pytest.raises(
        InvalidPlatformError,
        match="Unsupported platform 'bsd'. Supported platforms: linux, windows, macos.",
    ):
        manager.get_adapter("bsd")


def test_state_manager_raises_for_invalid_mode():
    manager = StateManager()

    with pytest.raises(
        InvalidModeError,
        match="Unsupported mode 'turbo'. Supported modes: mock, live.",
    ):
        manager.normalize_mode("turbo")
