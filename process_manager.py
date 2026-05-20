from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from commands import (
    CommandSpec,
    build_failover_block_command,
    build_failover_restore_command,
    build_mission_planner_command,
    build_secondary_command,
    build_wsl_sitl_command,
    build_wsl_sitl_cleanup_command,
    resolve_mission_planner_path,
)
from config import AppConfig, load_config


STATUS_PATTERN = re.compile(
    r"\|\s*mode=(?P<mode>\S+)\s+armed=(?P<armed>\S+)\s+alt=(?P<alt>\S+)\s+link=(?P<link>\S+)"
)
MAVPROXY_ALTITUDE_PATTERN = re.compile(
    r"\bAlt\s+(?P<alt>-?\d+(?:\.\d+)?)m\b",
    re.IGNORECASE,
)
MAVPROXY_TAKEOFF_PATTERN = re.compile(
    r"^takeoff\s+(?P<alt>\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)
MAVPROXY_GUIDED_ALTITUDE_PATTERN = re.compile(
    r"^guided\s+(?P<alt>\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


class ProcessManager(QObject):
    sitl_output = Signal(str)
    secondary_output = Signal(str)
    app_output = Signal(str)
    status_updated = Signal(dict)
    sitl_running_changed = Signal(bool)
    secondary_running_changed = Signal(bool)
    process_error = Signal(str, str)

    def __init__(self, config: AppConfig | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config or load_config()
        self._status = {
            "monitor_status": "UNKNOWN",
            "command_status": "DISCONNECTED",
            "trust_status": "UNTRUSTED",
            "failover_status": "NORMAL",
            "mode": "UNKNOWN",
            "armed": "UNKNOWN",
            "altitude": "N/A",
        }
        self._sitl_buffer = ""
        self._secondary_buffer = ""
        self._utility_processes: set[QProcess] = set()
        self._secondary_autostart_pending = False
        self._sitl_ready_seen = False
        self._last_useful_altitude: str | None = None
        self._primary_altitude_hint: str | None = None

        self.sitl_process = QProcess(self)
        self.secondary_process = QProcess(self)

        self._configure_long_process(
            self.sitl_process,
            "SITL",
            self.sitl_output,
            self.sitl_running_changed,
            "_sitl_buffer",
            parser=self._parse_sitl_line,
        )
        self._configure_long_process(
            self.secondary_process,
            "SECONDARY",
            self.secondary_output,
            self.secondary_running_changed,
            "_secondary_buffer",
            parser=self._parse_secondary_line,
        )

    @property
    def sitl_running(self) -> bool:
        return self.sitl_process.state() != QProcess.NotRunning

    @property
    def secondary_running(self) -> bool:
        return self.secondary_process.state() != QProcess.NotRunning

    def start_all(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event(
                "Hardware Mode active: starting Secondary Channel only."
            )
            self.start_secondary()
            return

        self.start_sitl()
        if not self.secondary_running:
            self._secondary_autostart_pending = True
            QTimer.singleShot(18000, self._start_secondary_after_sitl)

    def stop_all(self) -> None:
        self.stop_secondary()
        self.stop_sitl()

    def start_sitl(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event(
                "SITL start skipped because Hardware Mode is active."
            )
            return
        if self.sitl_running:
            self._emit_app_event("SITL is already running.")
            return
        spec = build_wsl_sitl_command(self.config)
        if spec is None:
            self._emit_app_event(
                "SITL start skipped because Hardware Mode is active."
            )
            return
        self._remove_failover_firewall_rule("PRESTART_RESTORE")
        self._start_process(self.sitl_process, "SITL", spec)

    def stop_sitl(self) -> None:
        self._stop_process(self.sitl_process, "SITL")
        self._cleanup_wsl_sitl_processes()

    def start_secondary(self) -> None:
        if self.secondary_running:
            self._emit_app_event("Secondary channel is already running.")
            return
        spec = build_secondary_command(self.config)
        script_path = self.config.secondary_script_path
        if not script_path.exists():
            message = f"Secondary script not found: {script_path}"
            self._emit_app_event(message)
            self.process_error.emit("Secondary Channel", message)
            return
        self._log_secondary_runtime_config()
        self._start_process(self.secondary_process, "SECONDARY", spec)

    def _start_secondary_after_sitl(self) -> None:
        if not self._secondary_autostart_pending:
            return
        if self.secondary_running:
            self._secondary_autostart_pending = False
            return
        if self.sitl_running:
            self._secondary_autostart_pending = False
            self.start_secondary()
        else:
            self._emit_app_event("Skipping Secondary start because SITL is not running.")

    def stop_secondary(self) -> None:
        self._stop_process(self.secondary_process, "SECONDARY")

    def trigger_failover(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event(
                "Failover firewall simulation is disabled in Hardware Mode."
            )
            return
        self._remove_monitor_output_from_mavproxy()
        self._run_oneshot("FAILOVER", build_failover_block_command(self.config))

    def restore_link(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event(
                "Restore firewall simulation is disabled in Hardware Mode."
            )
            return
        self._emit_app_event(
            "Restore requested: restoring monitor link and resetting SITL session."
        )
        self._restore_monitor_output_to_mavproxy()
        self._run_oneshot("RESTORE", build_failover_restore_command(self.config))
        self.reset_sitl_session()

    def remove_firewall_rule(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event(
                "Firewall rule cleanup is disabled in Hardware Mode."
            )
            return
        self._remove_failover_firewall_rule("REMOVE_RULE")

    def reset_sitl_session(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event("Session reset is disabled in Hardware Mode.")
            return
        self._emit_app_event(
            "Resetting session: stopping Secondary/SITL, then starting a clean SITL run."
        )
        self.stop_secondary()
        self.stop_sitl()
        self._reset_status()
        QTimer.singleShot(5500, self.start_all)

    def launch_mission_planner(self) -> None:
        mission_planner_path = resolve_mission_planner_path(self.config)
        if mission_planner_path is None:
            message = (
                "Mission Planner path is not configured and could not be auto-detected."
            )
            self._emit_app_event(message)
            self.process_error.emit("Mission Planner", message)
            return

        self._emit_app_event(f"Mission Planner path resolved: {mission_planner_path}")
        spec = build_mission_planner_command(self.config, mission_planner_path)
        if spec is None:
            message = (
                "Mission Planner path is not configured and could not be auto-detected."
            )
            self._emit_app_event(message)
            self.process_error.emit("Mission Planner", message)
            return
        started = QProcess.startDetached(spec.program, spec.args, str(spec.cwd))
        if isinstance(started, tuple):
            started = started[0]
        if started:
            self._emit_app_event(f"Mission Planner launched: {spec.display}")
        else:
            message = f"Failed to launch Mission Planner: {spec.display}"
            self._emit_app_event(message)
            self.process_error.emit("Mission Planner", message)

    def send_secondary_input(self, text: str) -> bool:
        return self._send_secondary_text(text, ensure_newline=True)

    def send_secondary_console_input(self, text: str) -> bool:
        command_text = text.strip()
        if not command_text:
            return False

        parts = command_text.lower().split()
        command = parts[0]

        if command in {"g", "r", "h", "l", "a", "d"} and len(parts) == 1:
            self._send_secondary_menu_action(command)
            return True

        if command == "m" and len(parts) == 1:
            return self.send_secondary_input("m")

        if command == "q" and len(parts) == 1:
            return self.send_secondary_input("q")

        if command == "t":
            if len(parts) != 2:
                self._emit_app_event(
                    "Secondary console: use 't <altitude>' or the TAKEOFF button."
                )
                return False
            try:
                altitude = float(parts[1])
            except ValueError:
                self._emit_app_event(
                    f"Secondary console invalid takeoff altitude: {parts[1]}"
                )
                return False
            self.secondary_takeoff(altitude)
            return True

        if command == "c":
            if len(parts) != 2:
                self._emit_app_event(
                    "Secondary console: use 'c <altitude>' or the Change Altitude button."
                )
                return False
            try:
                altitude = float(parts[1])
            except ValueError:
                self._emit_app_event(
                    f"Secondary console invalid altitude change target: {parts[1]}"
                )
                return False
            self.secondary_change_altitude(altitude)
            return True

        return self.send_secondary_input(command_text)

    def send_sitl_input(self, text: str) -> bool:
        command_text = text.strip()
        if command_text:
            self._emit_app_event(f"MAVProxy command queued: {command_text}")
            self.sitl_output.emit(f">>> {command_text}")
            self._schedule_primary_altitude_hint_from_command(command_text)
        return self._send_process_text(
            self.sitl_process,
            "SITL",
            text,
            ensure_newline=True,
        )

    def secondary_show_menu(self) -> None:
        self.send_secondary_input("m")

    def secondary_observe(self) -> None:
        self.send_secondary_input("q")

    def secondary_guided(self) -> None:
        self._send_secondary_menu_action("g")

    def secondary_rtl(self) -> None:
        self._send_secondary_menu_action("r")

    def secondary_hold(self) -> None:
        self._send_secondary_menu_action("h")

    def secondary_land(self) -> None:
        self._send_secondary_menu_action("l")

    def secondary_arm(self) -> None:
        self._send_secondary_menu_action("a")

    def secondary_disarm(self) -> None:
        self._send_secondary_menu_action("d")

    def secondary_takeoff(self, altitude_m: float) -> None:
        if not self._send_secondary_text("m", ensure_newline=True):
            return
        QTimer.singleShot(
            200,
            lambda: self._send_secondary_text("t", ensure_newline=False),
        )
        QTimer.singleShot(
            400,
            lambda altitude=f"{altitude_m:g}": self.send_secondary_input(altitude),
        )

    def secondary_change_altitude(self, altitude_m: float) -> None:
        if not self._send_secondary_text("m", ensure_newline=True):
            return
        QTimer.singleShot(
            200,
            lambda: self._send_secondary_text("c", ensure_newline=False),
        )
        QTimer.singleShot(
            400,
            lambda altitude=f"{altitude_m:g}": self.send_secondary_input(altitude),
        )

    def primary_guided(self) -> None:
        self._emit_app_event("PRIMARY_ACTION_REQUESTED action=GUIDED")
        self.send_sitl_input("mode guided")

    def primary_rtl(self) -> None:
        self._emit_app_event("PRIMARY_ACTION_REQUESTED action=RTL")
        self.send_sitl_input("mode rtl")

    def primary_hold(self) -> None:
        self._emit_app_event("PRIMARY_ACTION_REQUESTED action=HOLD")
        self.send_sitl_input("mode loiter")

    def primary_land(self) -> None:
        self._emit_app_event("PRIMARY_ACTION_REQUESTED action=LAND")
        self.send_sitl_input("mode land")

    def primary_arm(self) -> None:
        self._emit_app_event("PRIMARY_ACTION_REQUESTED action=ARM")
        self.send_sitl_input("arm throttle")

    def primary_disarm(self) -> None:
        self._emit_app_event("PRIMARY_ACTION_REQUESTED action=DISARM")
        self.send_sitl_input("disarm")

    def primary_takeoff(self, altitude_m: float) -> None:
        self._emit_app_event(
            f"PRIMARY_ACTION_REQUESTED action=TAKEOFF altitude={altitude_m:.1f}m"
        )
        QTimer.singleShot(
            1200,
            lambda altitude=altitude_m: self._apply_primary_altitude_hint(
                altitude,
                "primary_takeoff_target",
            ),
        )
        if not self.send_sitl_input("mode guided"):
            return
        QTimer.singleShot(200, lambda: self.send_sitl_input("arm throttle"))
        QTimer.singleShot(
            400,
            lambda altitude=f"{altitude_m:g}": self.send_sitl_input(
                f"takeoff {altitude}"
            ),
        )

    def primary_change_altitude(self, altitude_m: float) -> None:
        self._emit_app_event(
            f"PRIMARY_ACTION_REQUESTED action=CHANGE_ALTITUDE altitude={altitude_m:.1f}m"
        )
        QTimer.singleShot(
            1200,
            lambda altitude=altitude_m: self._apply_primary_altitude_hint(
                altitude,
                "primary_change_altitude_target",
            ),
        )
        if not self.send_sitl_input("mode guided"):
            return
        QTimer.singleShot(
            250,
            lambda altitude=f"{altitude_m:g}": self.send_sitl_input(
                f"guided {altitude}"
            ),
        )

    def _apply_primary_altitude_hint(self, altitude_m: float, source: str) -> None:
        altitude_text = f"{altitude_m:.2f}m"
        self._primary_altitude_hint = altitude_text
        self._last_useful_altitude = altitude_text
        self._emit_app_event(
            f"PRIMARY_ALTITUDE_HINT source={source} altitude={altitude_text}"
        )
        self._update_status(altitude=altitude_text)

    def _schedule_primary_altitude_hint_from_command(self, command_text: str) -> None:
        for pattern, source, delay_ms in (
            (MAVPROXY_TAKEOFF_PATTERN, "mavproxy_takeoff", 3500),
            (MAVPROXY_GUIDED_ALTITUDE_PATTERN, "mavproxy_guided_altitude", 2500),
        ):
            match = pattern.match(command_text)
            if match is None:
                continue
            altitude_m = float(match.group("alt"))
            QTimer.singleShot(
                delay_ms,
                lambda altitude=altitude_m, hint_source=source: self._apply_primary_altitude_hint(
                    altitude,
                    hint_source,
                ),
            )
            return

    def _monitor_output_address(self) -> str:
        return f"{self.config.windows_host_ip}:{self.config.monitor_udp_port}"

    def _remove_monitor_output_from_mavproxy(self) -> None:
        if not self.sitl_running:
            self._emit_app_event(
                "MAVProxy monitor output remove skipped because SITL is not running."
            )
            return
        address = self._monitor_output_address()
        self._emit_app_event(f"Removing MAVProxy monitor output: {address}")
        self.send_sitl_input(f"output remove {address}")

    def _restore_monitor_output_to_mavproxy(self) -> None:
        if not self.sitl_running:
            self._emit_app_event(
                "MAVProxy monitor output restore skipped because SITL is not running."
            )
            return
        address = self._monitor_output_address()
        self._emit_app_event(f"Restoring MAVProxy monitor output: udp:{address}")
        self.send_sitl_input(f"output add udp:{address}")

    def _cleanup_wsl_sitl_processes(self) -> None:
        spec = build_wsl_sitl_cleanup_command(self.config)
        if spec is None:
            return
        self._run_oneshot("WSL_CLEANUP", spec)

    def _remove_failover_firewall_rule(self, label: str) -> None:
        self._emit_app_event(
            f"{label}: ensuring failover firewall rule is removed before monitor test."
        )
        self._run_oneshot(label, build_failover_restore_command(self.config))

    def _configure_long_process(
        self,
        process: QProcess,
        name: str,
        output_signal: Signal,
        running_signal: Signal,
        buffer_attr: str,
        parser=None,
    ) -> None:
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.setInputChannelMode(QProcess.ManagedInputChannel)
        process.started.connect(lambda n=name, s=running_signal: self._on_started(n, s))
        process.finished.connect(
            lambda code, status, n=name, s=running_signal: self._on_finished(
                n,
                code,
                status,
                s,
            )
        )
        process.errorOccurred.connect(
            lambda error, n=name, p=process: self._on_error(n, p, error)
        )
        process.readyReadStandardOutput.connect(
            lambda p=process, b=buffer_attr, sig=output_signal, parse=parser: self._drain_process_output(
                p,
                b,
                sig,
                parse,
                read_stderr=False,
            )
        )
        process.readyReadStandardError.connect(
            lambda p=process, b=buffer_attr, sig=output_signal, parse=parser: self._drain_process_output(
                p,
                b,
                sig,
                parse,
                read_stderr=True,
            )
        )

    def _start_process(self, process: QProcess, name: str, spec: CommandSpec) -> None:
        env = QProcessEnvironment.systemEnvironment()
        for key, value in spec.env_updates.items():
            env.insert(key, value)
        process.setProcessEnvironment(env)
        if spec.cwd is not None:
            process.setWorkingDirectory(str(spec.cwd))

        self._emit_app_event(f"Starting {name}: {spec.display}")
        process.start(spec.program, spec.args)
        if not process.waitForStarted(1500):
            message = f"{name} failed to start: {process.errorString()}"
            self._emit_app_event(message)
            self.process_error.emit(name, message)

    def _stop_process(self, process: QProcess, name: str) -> None:
        if process.state() == QProcess.NotRunning:
            return
        self._emit_app_event(f"Stopping {name}...")
        process.terminate()
        QTimer.singleShot(3000, lambda p=process, n=name: self._kill_if_running(p, n))

    def _kill_if_running(self, process: QProcess, name: str) -> None:
        if process.state() == QProcess.NotRunning:
            return
        self._emit_app_event(f"Force-killing {name}.")
        process.kill()

    def _run_oneshot(self, name: str, spec: CommandSpec) -> None:
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        self._utility_processes.add(process)
        self._emit_app_event(f"{name}: {spec.display}")

        def cleanup() -> None:
            self._utility_processes.discard(process)
            process.deleteLater()

        def read_output(read_stderr: bool) -> None:
            data = process.readAllStandardError() if read_stderr else process.readAllStandardOutput()
            text = bytes(data).decode("utf-8", errors="replace")
            for line in text.replace("\r\n", "\n").split("\n"):
                if line.strip():
                    self._emit_app_event(f"{name}> {line.rstrip()}")

        process.readyReadStandardOutput.connect(lambda: read_output(False))
        process.readyReadStandardError.connect(lambda: read_output(True))
        process.errorOccurred.connect(
            lambda _error, n=name, p=process: self._emit_app_event(
                f"{n} failed: {p.errorString()}"
            )
        )
        process.finished.connect(
            lambda code, _status, n=name: self._emit_app_event(
                f"{n} finished with exit code {code}."
            )
        )
        process.finished.connect(lambda *_args: cleanup())
        process.start(spec.program, spec.args)

    def _drain_process_output(
        self,
        process: QProcess,
        buffer_attr: str,
        output_signal: Signal,
        parser,
        read_stderr: bool,
    ) -> None:
        data = process.readAllStandardError() if read_stderr else process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        buffer = getattr(self, buffer_attr) + text
        lines = buffer.splitlines(keepends=True)
        remainder = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            remainder = lines.pop()
        setattr(self, buffer_attr, remainder)

        for raw_line in lines:
            line = raw_line.rstrip()
            if not line:
                continue
            output_signal.emit(line)
            if parser is not None:
                parser(line)

    def _on_started(self, name: str, running_signal: Signal) -> None:
        self._emit_app_event(f"{name} started.")
        if name == "SITL":
            self._sitl_ready_seen = False
        running_signal.emit(True)

    def _on_finished(
        self,
        name: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
        running_signal: Signal,
    ) -> None:
        status_name = "crashed" if exit_status == QProcess.CrashExit else "finished"
        self._emit_app_event(f"{name} {status_name} with exit code {exit_code}.")
        running_signal.emit(False)
        if name == "SECONDARY":
            self._update_status(command_status="DISCONNECTED", trust_status="UNTRUSTED")
        if name == "SITL" and not self.secondary_running:
            self._update_status(monitor_status="UNKNOWN")
            self._secondary_autostart_pending = False

    def _on_error(self, name: str, process: QProcess, _error: QProcess.ProcessError) -> None:
        message = f"{name} process error: {process.errorString()}"
        self._emit_app_event(message)
        self.process_error.emit(name, message)

    def _emit_app_event(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.app_output.emit(f"[{timestamp}] {message}")

    def _log_secondary_runtime_config(self) -> None:
        if self.config.hardware_mode:
            self._emit_app_event("Mode: HARDWARE")
            self._emit_app_event(
                "Monitor serial: "
                f"{self.config.monitor_serial_port} @ {self.config.monitor_serial_baud}"
            )
            self._emit_app_event(
                "Command serial: "
                f"{self.config.command_serial_port} @ {self.config.command_serial_baud}"
            )
        else:
            self._emit_app_event("Mode: SITL")
            self._emit_app_event(f"Monitor UDP: {self.config.monitor_udp_port}")
            self._emit_app_event(f"Command TCP: {self.config.command_tcp_port}")

        self._emit_app_event(
            "Signing: "
            f"enabled={str(self.config.signing.signing_enabled).lower()} "
            f"command_signing={str(self.config.signing.command_signing_enabled).lower()}"
        )

    def _send_secondary_menu_action(self, action_key: str) -> None:
        if not self._send_secondary_text("m", ensure_newline=True):
            return
        QTimer.singleShot(
            200,
            lambda key=action_key: self._send_secondary_text(
                key,
                ensure_newline=True,
            ),
        )

    def _send_secondary_text(self, text: str, ensure_newline: bool) -> bool:
        return self._send_process_text(
            self.secondary_process,
            "Secondary Channel",
            text,
            ensure_newline=ensure_newline,
        )

    def _send_process_text(
        self,
        process: QProcess,
        process_name: str,
        text: str,
        ensure_newline: bool,
    ) -> bool:
        if process.state() != QProcess.Running:
            message = f"{process_name} is not running."
            self._emit_app_event(message)
            self.process_error.emit(process_name, message)
            return False

        payload = text
        if ensure_newline and not payload.endswith("\n"):
            payload = f"{payload}\n"

        written = process.write(payload.encode("utf-8"))
        if written == -1:
            message = f"Failed to write to {process_name} stdin."
            self._emit_app_event(message)
            self.process_error.emit(process_name, message)
            return False

        display_text = payload.replace("\r", "\\r").replace("\n", "\\n")
        self._emit_app_event(
            f"{process_name.upper().replace(' ', '_')}_INPUT_SENT text={display_text}"
        )
        return True

    def _reset_status(self) -> None:
        self._last_useful_altitude = None
        self._primary_altitude_hint = None
        self._status = {
            "monitor_status": "UNKNOWN",
            "command_status": "DISCONNECTED",
            "trust_status": "UNTRUSTED",
            "failover_status": "NORMAL",
            "mode": "UNKNOWN",
            "armed": "UNKNOWN",
            "altitude": "N/A",
        }
        self.status_updated.emit(dict(self._status))

    def _update_status(self, **updates: str) -> None:
        changed = False
        for key, value in updates.items():
            if key == "altitude" and not self._is_unavailable_altitude(value):
                self._last_useful_altitude = value
            if self._status.get(key) != value:
                self._status[key] = value
                changed = True
        if changed:
            self.status_updated.emit(dict(self._status))

    @staticmethod
    def _is_unavailable_altitude(value: str) -> bool:
        return value in {"N/A", "0.00m", "0.0m", "0m", "-0.00m", "-0.0m", "-0m"}

    def _parse_secondary_line(self, line: str) -> None:
        if "MONITOR_LINK_CONNECTED" in line or "MONITOR_HEARTBEAT_RECEIVED" in line:
            self._update_status(monitor_status="OK", failover_status="PRIMARY OK")
        if "MONITOR_LINK_LOST" in line or "LINK_TIMEOUT" in line:
            self._update_status(monitor_status="LOST", failover_status="PRIMARY LOST")
        if "COMMAND_LINK_CONNECTED" in line or "SECONDARY_LINK_RECONNECTED" in line:
            self._update_status(command_status="CONNECTED")
        if "SECONDARY_LINK_NO_HEARTBEAT" in line or "SECONDARY_RECONNECT_FAILED" in line:
            self._update_status(command_status="DISCONNECTED")
        if "COMMAND_LINK_OBSERVABLE" in line:
            self._update_status(trust_status="OBSERVABLE")
        if "COMMAND_LINK_TRUSTED" in line or "COMMAND_CONTROL_TRUSTED" in line:
            self._update_status(command_status="CONNECTED", trust_status="TRUSTED")
        if (
            "COMMAND_LINK_CONNECTED_BUT_NOT_TRUSTED" in line
            or "SECONDARY_CONTROL_UNAVAILABLE" in line
            or "SECONDARY_LINK_NOT_TRUSTED_YET" in line
            or "SECURITY_POLICY_BLOCKED_COMMAND" in line
        ):
            self._update_status(
                trust_status="UNTRUSTED",
                failover_status=(
                    "SECONDARY UNTRUSTED"
                    if self._status.get("monitor_status") == "LOST"
                    else self._status.get("failover_status", "NORMAL")
                ),
            )
        if "SECONDARY_ACTIVATED" in line:
            self._update_status(
                monitor_status="LOST",
                failover_status="SECONDARY ACTIVE",
            )

        match = STATUS_PATTERN.search(line)
        if not match:
            return

        mode = match.group("mode")
        armed = match.group("armed")
        altitude = match.group("alt")
        link = match.group("link")
        updates = {
            "mode": mode,
            "armed": armed,
        }
        if self._is_unavailable_altitude(altitude) and link == "SECONDARY_UNAVAILABLE":
            fallback_altitude = self._last_useful_altitude or self._primary_altitude_hint
            if fallback_altitude is not None:
                updates["altitude"] = fallback_altitude
        else:
            updates["altitude"] = altitude
        if link == "MONITOR_OK":
            updates["monitor_status"] = "OK"
        elif link == "TIMEOUT":
            updates["monitor_status"] = "LOST"
        elif link in {"SECONDARY_ACTIVE", "SECONDARY_NO_HEARTBEAT"}:
            updates["command_status"] = (
                "CONNECTED" if link == "SECONDARY_ACTIVE" else "DISCONNECTED"
            )
        self._update_status(**updates)

    def _parse_sitl_line(self, line: str) -> None:
        lower_line = line.lower()
        altitude_match = MAVPROXY_ALTITUDE_PATTERN.search(line)
        if altitude_match is not None:
            try:
                altitude = float(altitude_match.group("alt"))
            except ValueError:
                altitude = None
            if altitude is not None:
                self._update_status(altitude=f"{altitude:.2f}m")

        ready_markers = (
            "mav>",
            "stabilize>",
            "guided>",
            "loiter>",
            "rtl>",
            "land>",
            "received",
            "online system",
        )
        if self._sitl_ready_seen or not any(marker in lower_line for marker in ready_markers):
            return
        self._sitl_ready_seen = True
        self._emit_app_event("SITL/MAVProxy ready detected.")
        if self._secondary_autostart_pending:
            self._emit_app_event("Starting Secondary after SITL readiness detection.")
            self._start_secondary_after_sitl()
