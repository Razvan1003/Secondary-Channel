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
)
from config import AppConfig, load_config


STATUS_PATTERN = re.compile(
    r"\|\s*mode=(?P<mode>\S+)\s+armed=(?P<armed>\S+)\s+alt=(?P<alt>\S+)\s+link=(?P<link>\S+)"
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
            "mode": "UNKNOWN",
            "armed": "UNKNOWN",
            "altitude": "N/A",
        }
        self._sitl_buffer = ""
        self._secondary_buffer = ""
        self._utility_processes: set[QProcess] = set()

        self.sitl_process = QProcess(self)
        self.secondary_process = QProcess(self)

        self._configure_long_process(
            self.sitl_process,
            "SITL",
            self.sitl_output,
            self.sitl_running_changed,
            "_sitl_buffer",
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
        self.start_sitl()
        if not self.secondary_running:
            QTimer.singleShot(3000, self._start_secondary_after_sitl)

    def stop_all(self) -> None:
        self.stop_secondary()
        self.stop_sitl()

    def start_sitl(self) -> None:
        if self.sitl_running:
            self._emit_app_event("SITL is already running.")
            return
        spec = build_wsl_sitl_command(self.config)
        self._start_process(self.sitl_process, "SITL", spec)

    def stop_sitl(self) -> None:
        self._stop_process(self.sitl_process, "SITL")

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
        self._start_process(self.secondary_process, "SECONDARY", spec)

    def _start_secondary_after_sitl(self) -> None:
        if self.sitl_running:
            self.start_secondary()
        else:
            self._emit_app_event("Skipping Secondary start because SITL is not running.")

    def stop_secondary(self) -> None:
        self._stop_process(self.secondary_process, "SECONDARY")

    def trigger_failover(self) -> None:
        self._run_oneshot("FAILOVER", build_failover_block_command(self.config))

    def restore_link(self) -> None:
        self._run_oneshot("RESTORE", build_failover_restore_command(self.config))

    def launch_mission_planner(self) -> None:
        spec = build_mission_planner_command(self.config)
        if spec is None:
            self._emit_app_event("Mission Planner path is not configured.")
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

    def _on_error(self, name: str, process: QProcess, _error: QProcess.ProcessError) -> None:
        message = f"{name} process error: {process.errorString()}"
        self._emit_app_event(message)
        self.process_error.emit(name, message)

    def _emit_app_event(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.app_output.emit(f"[{timestamp}] {message}")

    def _update_status(self, **updates: str) -> None:
        changed = False
        for key, value in updates.items():
            if self._status.get(key) != value:
                self._status[key] = value
                changed = True
        if changed:
            self.status_updated.emit(dict(self._status))

    def _parse_secondary_line(self, line: str) -> None:
        if "MONITOR_LINK_CONNECTED" in line or "MONITOR_HEARTBEAT_RECEIVED" in line:
            self._update_status(monitor_status="OK")
        if "MONITOR_LINK_LOST" in line or "LINK_TIMEOUT" in line:
            self._update_status(monitor_status="LOST")
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
            self._update_status(trust_status="UNTRUSTED")
        if "COMMAND_LOOP_ACTIVE" in line and self._status["command_status"] == "CONNECTED":
            self._update_status(trust_status="TRUSTED")
        if "SECONDARY_ACTIVATED" in line:
            self._update_status(monitor_status="LOST")

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
            "altitude": altitude,
        }
        if link == "MONITOR_OK":
            updates["monitor_status"] = "OK"
        elif link == "TIMEOUT":
            updates["monitor_status"] = "LOST"
        elif link in {"SECONDARY_ACTIVE", "SECONDARY_NO_HEARTBEAT"}:
            updates["command_status"] = (
                "CONNECTED" if link == "SECONDARY_ACTIVE" else "DISCONNECTED"
            )
        self._update_status(**updates)
