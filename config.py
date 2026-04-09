from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class SigningConfig:
    signing_enabled: bool
    monitor_signing_enabled: bool
    command_signing_enabled: bool
    signing_key: str
    command_unsigned_policy: str
    security_test_mode: bool


@dataclass(frozen=True)
class AppConfig:
    wsl_executable: str
    powershell_executable: str
    python_launcher: str
    wsl_distro: str
    ardupilot_wsl_path: str
    windows_host_ip: str
    command_host: str
    mission_planner_path: str
    mission_planner_udp_port: int
    monitor_udp_port: int
    command_tcp_port: int
    firewall_rule_name: str
    secondary_script_path: Path
    secondary_workdir: Path
    signing: SigningConfig


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    signing_enabled = _env_flag("SECONDARY_CHANNEL_SIGNING_ENABLED", True)
    signing = SigningConfig(
        signing_enabled=signing_enabled,
        monitor_signing_enabled=_env_flag(
            "SECONDARY_CHANNEL_MONITOR_SIGNING_ENABLED",
            False,
        ),
        command_signing_enabled=_env_flag(
            "SECONDARY_CHANNEL_COMMAND_SIGNING_ENABLED",
            signing_enabled,
        ),
        signing_key=os.environ.get("SECONDARY_CHANNEL_SIGNING_KEY", "").strip(),
        command_unsigned_policy=os.environ.get(
            "SECONDARY_CHANNEL_COMMAND_UNSIGNED_POLICY",
            "reject",
        ).strip().lower(),
        security_test_mode=_env_flag(
            "SECONDARY_CHANNEL_SECURITY_TEST_MODE",
            False,
        ),
    )
    secondary_script_path = Path(
        os.environ.get(
            "SECONDARY_CHANNEL_SCRIPT_PATH",
            str(REPO_ROOT / "secondary_channel_v4.py"),
        )
    ).expanduser()
    secondary_workdir = Path(
        os.environ.get(
            "SECONDARY_CHANNEL_WORKDIR",
            str(secondary_script_path.parent),
        )
    ).expanduser()
    return AppConfig(
        wsl_executable=os.environ.get("WSL_EXECUTABLE", "wsl.exe").strip(),
        powershell_executable=os.environ.get(
            "POWERSHELL_EXECUTABLE",
            "powershell.exe",
        ).strip(),
        python_launcher=os.environ.get("SECONDARY_PYTHON_LAUNCHER", "py").strip(),
        wsl_distro=os.environ.get("ARDUPILOT_WSL_DISTRO", "").strip(),
        ardupilot_wsl_path=os.environ.get(
            "ARDUPILOT_WSL_PATH",
            "~/ardupilot/ArduCopter",
        ).strip(),
        windows_host_ip=os.environ.get(
            "SECONDARY_WINDOWS_HOST_IP",
            "172.30.208.1",
        ).strip(),
        command_host=os.environ.get(
            "SECONDARY_COMMAND_HOST",
            "127.0.0.1",
        ).strip(),
        mission_planner_path=os.environ.get("MISSION_PLANNER_PATH", "").strip(),
        mission_planner_udp_port=int(
            os.environ.get("MISSION_PLANNER_UDP_PORT", "14550").strip()
        ),
        monitor_udp_port=int(
            os.environ.get("SECONDARY_MONITOR_UDP_PORT", "14560").strip()
        ),
        command_tcp_port=int(
            os.environ.get("SECONDARY_COMMAND_TCP_PORT", "5782").strip()
        ),
        firewall_rule_name=os.environ.get(
            "SECONDARY_FIREWALL_RULE_NAME",
            "Block_MAVLink_14560_Test",
        ).strip(),
        secondary_script_path=secondary_script_path,
        secondary_workdir=secondary_workdir,
        signing=signing,
    )
