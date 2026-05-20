from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config import AppConfig


@dataclass(frozen=True)
class CommandSpec:
    program: str
    args: list[str]
    cwd: Path | None = None
    env_updates: dict[str, str] = field(default_factory=dict)
    display: str = ""


def _quote(arg: str) -> str:
    if not arg or any(char.isspace() for char in arg) or '"' in arg:
        return f'"{arg.replace(chr(34), chr(92) + chr(34))}"'
    return arg


def format_command(program: str, args: list[str]) -> str:
    return " ".join([_quote(program), *(_quote(arg) for arg in args)])


def build_wsl_sitl_command(config: AppConfig) -> CommandSpec | None:
    if config.hardware_mode:
        return None
    sim_vehicle_cmd = (
        f'cd {config.ardupilot_wsl_path} && '
        "sim_vehicle.py -w -v ArduCopter -f quad --map --console "
        f"--out={config.windows_host_ip}:{config.mission_planner_udp_port} "
        f"--out={config.windows_host_ip}:{config.monitor_udp_port} "
        f'-A "--serial2=tcp:{config.command_tcp_port}"'
    )
    args = ["--"]
    if config.wsl_distro:
        args = ["-d", config.wsl_distro, "--"]
    args.extend(["bash", "-lc", sim_vehicle_cmd])
    return CommandSpec(
        program=config.wsl_executable,
        args=args,
        display=format_command(config.wsl_executable, args),
    )


def build_wsl_sitl_cleanup_command(config: AppConfig) -> CommandSpec | None:
    if config.hardware_mode:
        return None
    cleanup_cmd = (
        'pkill -f "sim_vehicle.py|mavproxy.py|MAVProxy|arducopter" '
        "2>/dev/null || true"
    )
    args = ["--"]
    if config.wsl_distro:
        args = ["-d", config.wsl_distro, "--"]
    args.extend(["bash", "-lc", cleanup_cmd])
    return CommandSpec(
        program=config.wsl_executable,
        args=args,
        display=format_command(config.wsl_executable, args),
    )


def build_secondary_command(config: AppConfig) -> CommandSpec:
    args = [f".\\{config.secondary_script_path.name}"]
    if config.hardware_mode:
        monitor_connection = config.monitor_serial_port
        command_connection = config.command_serial_port
    else:
        monitor_connection = f"udpin:0.0.0.0:{config.monitor_udp_port}"
        command_connection = f"tcp:{config.command_host}:{config.command_tcp_port}"
    env_updates = {
        "SECONDARY_HARDWARE_MODE": str(config.hardware_mode).lower(),
        "SECONDARY_CHANNEL_MONITOR_CONNECTION": monitor_connection,
        "SECONDARY_CHANNEL_COMMAND_CONNECTION": command_connection,
        "SECONDARY_CHANNEL_MONITOR_BAUD": str(config.monitor_serial_baud),
        "SECONDARY_CHANNEL_COMMAND_BAUD": str(config.command_serial_baud),
        "SECONDARY_CHANNEL_SIGNING_ENABLED": str(
            config.signing.signing_enabled
        ).lower(),
        "SECONDARY_CHANNEL_MONITOR_SIGNING_ENABLED": str(
            config.signing.monitor_signing_enabled
        ).lower(),
        "SECONDARY_CHANNEL_COMMAND_SIGNING_ENABLED": str(
            config.signing.command_signing_enabled
        ).lower(),
        "SECONDARY_CHANNEL_SIGNING_KEY": config.signing.signing_key,
        "SECONDARY_CHANNEL_COMMAND_UNSIGNED_POLICY": (
            config.signing.command_unsigned_policy
        ),
        "SECONDARY_CHANNEL_SECURITY_TEST_MODE": str(
            config.signing.security_test_mode
        ).lower(),
    }
    return CommandSpec(
        program=config.python_launcher,
        args=args,
        cwd=config.secondary_workdir,
        env_updates=env_updates,
        display=format_command(config.python_launcher, args),
    )


def build_failover_block_command(config: AppConfig) -> CommandSpec:
    command = (
        f'Remove-NetFirewallRule -DisplayName "{config.firewall_rule_name}" '
        "-ErrorAction SilentlyContinue; "
        f'New-NetFirewallRule -DisplayName "{config.firewall_rule_name}" '
        "-Direction Inbound -Action Block -Protocol UDP "
        f"-LocalPort {config.monitor_udp_port} -Profile Any"
    )
    args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
    return CommandSpec(
        program=config.powershell_executable,
        args=args,
        display=format_command(config.powershell_executable, args),
    )


def build_failover_restore_command(config: AppConfig) -> CommandSpec:
    command = (
        f'Remove-NetFirewallRule -DisplayName "{config.firewall_rule_name}" '
        "-ErrorAction SilentlyContinue"
    )
    args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
    return CommandSpec(
        program=config.powershell_executable,
        args=args,
        display=format_command(config.powershell_executable, args),
    )


def resolve_mission_planner_path(config: AppConfig) -> Path | None:
    candidate_paths: list[Path] = []
    if config.mission_planner_path:
        candidate_paths.append(Path(config.mission_planner_path).expanduser())

    home = Path.home()
    candidate_paths.extend(
        [
            Path(r"C:\Program Files (x86)\Mission Planner\MissionPlanner.exe"),
            Path(r"C:\Program Files\Mission Planner\MissionPlanner.exe"),
            home / "AppData" / "Local" / "Mission Planner" / "MissionPlanner.exe",
            home
            / "AppData"
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Mission Planner"
            / "Mission Planner.lnk",
        ]
    )

    for candidate in candidate_paths:
        if candidate.exists():
            return candidate

    return None


def build_mission_planner_command(
    config: AppConfig,
    mission_planner_path: Path | None = None,
) -> CommandSpec | None:
    resolved_path = mission_planner_path or resolve_mission_planner_path(config)
    if resolved_path is None:
        return None

    if resolved_path.suffix.lower() == ".lnk":
        args = [
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f'Start-Process -FilePath "{resolved_path}"',
        ]
        return CommandSpec(
            program=config.powershell_executable,
            args=args,
            cwd=resolved_path.parent,
            display=format_command(config.powershell_executable, args),
        )

    return CommandSpec(
        program=str(resolved_path),
        args=[],
        cwd=resolved_path.parent,
        display=_quote(str(resolved_path)),
    )
