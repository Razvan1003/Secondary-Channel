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


def build_wsl_sitl_command(config: AppConfig) -> CommandSpec:
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


def build_secondary_command(config: AppConfig) -> CommandSpec:
    args = [f".\\{config.secondary_script_path.name}"]
    env_updates = {
        "SECONDARY_CHANNEL_MONITOR_CONNECTION": (
            f"udpin:0.0.0.0:{config.monitor_udp_port}"
        ),
        "SECONDARY_CHANNEL_COMMAND_CONNECTION": (
            f"tcp:{config.command_host}:{config.command_tcp_port}"
        ),
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


def build_mission_planner_command(config: AppConfig) -> CommandSpec | None:
    if not config.mission_planner_path:
        return None
    return CommandSpec(
        program=config.mission_planner_path,
        args=[],
        cwd=Path(config.mission_planner_path).parent,
        display=_quote(config.mission_planner_path),
    )
