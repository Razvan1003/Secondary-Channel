from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget


class StatusPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels = {
            "monitor_status": QLabel("UNKNOWN"),
            "command_status": QLabel("DISCONNECTED"),
            "trust_status": QLabel("UNTRUSTED"),
            "failover_status": QLabel("NORMAL"),
            "mode": QLabel("UNKNOWN"),
            "armed": QLabel("UNKNOWN"),
            "altitude": QLabel("N/A"),
        }
        self.failover_banner = QLabel("PRIMARY LINK OK")
        self.failover_banner.setAlignment(Qt.AlignCenter)
        self.failover_banner.setMinimumHeight(42)

        root_layout = QVBoxLayout(self)
        root_layout.addWidget(self.failover_banner)
        layout = QFormLayout()
        root_layout.addLayout(layout)
        layout.addRow("Monitor", self._labels["monitor_status"])
        layout.addRow("Command", self._labels["command_status"])
        layout.addRow("Trust", self._labels["trust_status"])
        layout.addRow("Failover", self._labels["failover_status"])
        layout.addRow("Mode", self._labels["mode"])
        layout.addRow("Armed", self._labels["armed"])
        layout.addRow("Altitude", self._labels["altitude"])

        for key, label in self._labels.items():
            self._apply_status_color(key, label, label.text())

    def update_status(self, status: dict[str, str]) -> None:
        for key, value in status.items():
            label = self._labels.get(key)
            if label is not None:
                label.setText(str(value))
                self._apply_status_color(key, label, str(value))
        self._update_failover_banner()

    def _update_failover_banner(self) -> None:
        monitor = self._labels["monitor_status"].text()
        trust = self._labels["trust_status"].text()
        failover = self._labels["failover_status"].text()

        if failover == "SECONDARY UNTRUSTED" or (
            monitor == "LOST" and trust != "TRUSTED"
        ):
            self.failover_banner.setText("PRIMARY LOST - SECONDARY UNTRUSTED")
            self.failover_banner.setStyleSheet(
                "background-color: #7f1d1d; color: white; "
                "font-size: 17px; font-weight: 800; "
                "border: 2px solid #ef4444; border-radius: 6px; padding: 8px;"
            )
            return

        if monitor == "LOST" or failover in {"PRIMARY LOST", "SECONDARY ACTIVE"}:
            self.failover_banner.setText("PRIMARY LINK LOST - SECONDARY ACTIVE")
            self.failover_banner.setStyleSheet(
                "background-color: #b42318; color: white; "
                "font-size: 17px; font-weight: 800; "
                "border: 2px solid #f97316; border-radius: 6px; padding: 8px;"
            )
            return

        self.failover_banner.setText("PRIMARY LINK OK")
        self.failover_banner.setStyleSheet(
            "background-color: #0f5132; color: white; "
            "font-size: 14px; font-weight: 700; "
            "border: 1px solid #1b8f3a; border-radius: 6px; padding: 6px;"
        )

    def _apply_status_color(self, key: str, label: QLabel, value: str) -> None:
        color = ""

        if key == "trust_status":
            if value == "TRUSTED":
                color = "#1b8f3a"
            elif value in {"UNTRUSTED", "BLOCKED"}:
                color = "#b42318"
            else:
                color = "#6b7280"
        elif key in {"monitor_status", "command_status"}:
            if value in {"OK", "CONNECTED"}:
                color = "#1b8f3a"
            elif value in {"LOST", "DISCONNECTED"}:
                color = "#b42318"
            else:
                color = "#6b7280"
        elif key == "failover_status":
            if value in {"NORMAL", "PRIMARY OK"}:
                color = "#1b8f3a"
            elif value in {"PRIMARY LOST", "SECONDARY ACTIVE"}:
                color = "#c97a00"
            elif value in {"SECONDARY UNTRUSTED"}:
                color = "#b42318"
            else:
                color = "#6b7280"

        if color:
            label.setStyleSheet(f"color: {color}; font-weight: 600;")
        else:
            label.setStyleSheet("")
