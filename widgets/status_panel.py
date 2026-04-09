from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget


class StatusPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels = {
            "monitor_status": QLabel("UNKNOWN"),
            "command_status": QLabel("DISCONNECTED"),
            "trust_status": QLabel("UNTRUSTED"),
            "mode": QLabel("UNKNOWN"),
            "armed": QLabel("UNKNOWN"),
            "altitude": QLabel("N/A"),
        }

        layout = QFormLayout(self)
        layout.addRow("Monitor", self._labels["monitor_status"])
        layout.addRow("Command", self._labels["command_status"])
        layout.addRow("Trust", self._labels["trust_status"])
        layout.addRow("Mode", self._labels["mode"])
        layout.addRow("Armed", self._labels["armed"])
        layout.addRow("Altitude", self._labels["altitude"])

    def update_status(self, status: dict[str, str]) -> None:
        for key, value in status.items():
            label = self._labels.get(key)
            if label is not None:
                label.setText(str(value))
