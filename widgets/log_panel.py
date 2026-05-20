from __future__ import annotations

from time import monotonic

from PySide6.QtGui import QColor, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget


ALERT_RULES = (
    ("MONITOR_LINK_LOST", "PRIMARY LINK LOST", "#7f1d1d"),
    ("LINK_TIMEOUT", "PRIMARY LINK TIMEOUT", "#7f1d1d"),
    ("SECONDARY_ACTIVATED", "SECONDARY CHANNEL ACTIVE", "#b42318"),
    ("SECONDARY_CONTROL_UNAVAILABLE", "SECONDARY CONTROL BLOCKED", "#7f1d1d"),
    ("SECURITY_POLICY_BLOCKED_COMMAND", "SECURITY POLICY BLOCKED COMMAND", "#7f1d1d"),
    ("COMMAND_LINK_TRUSTED", "SECONDARY TRUSTED", "#0f5132"),
    ("COMMAND_CONTROL_TRUSTED", "SECONDARY TRUSTED", "#0f5132"),
)

ALERT_REPEAT_SECONDS = 4.0


class LogPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = QTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setAcceptRichText(False)
        self._editor.document().setDocumentMargin(1)
        self._editor.setStyleSheet(
            "QTextEdit { font-family: Consolas, 'Cascadia Mono', monospace; "
            "font-size: 10px; }"
        )
        self._last_alert_times: dict[str, float] = {}
        self._normal_char_format = QTextCharFormat()
        self._normal_char_format.setFontFamily("Consolas")
        self._normal_char_format.setFontPointSize(8.5)

        self._alert_char_format = QTextCharFormat()
        self._alert_char_format.setFontFamily("Consolas")
        self._alert_char_format.setFontPointSize(14)
        self._alert_char_format.setFontWeight(900)
        self._alert_char_format.setForeground(QColor("white"))

        self._normal_block_format = QTextBlockFormat()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._editor)

    def append_line(self, line: str) -> None:
        if not line:
            return
        text = line.rstrip()
        alert = self._alert_for_line(text)
        if alert is not None:
            label, color = alert
            self._append_alert(label, color)
        self._append_normal_line(text)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._editor.setTextCursor(cursor)

    def clear(self) -> None:
        self._editor.clear()
        self._last_alert_times.clear()

    def _alert_for_line(self, line: str) -> tuple[str, str] | None:
        for marker, label, color in ALERT_RULES:
            if marker not in line:
                continue
            now = monotonic()
            last_time = self._last_alert_times.get(label, 0.0)
            if now - last_time < ALERT_REPEAT_SECONDS:
                return None
            self._last_alert_times[label] = now
            return label, color
        return None

    def _append_alert(self, label: str, color: str) -> None:
        block_format = QTextBlockFormat()
        block_format.setBackground(QColor(color))
        block_format.setTopMargin(2)
        block_format.setBottomMargin(2)
        block_format.setLeftMargin(4)
        self._append_text_line(f"!!! {label} !!!", self._alert_char_format, block_format)

    def _append_normal_line(self, line: str) -> None:
        self._append_text_line(line, self._normal_char_format, self._normal_block_format)

    def _append_text_line(
        self,
        text: str,
        char_format: QTextCharFormat,
        block_format: QTextBlockFormat,
    ) -> None:
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self._editor.document().isEmpty() and cursor.block().text():
            cursor.insertBlock()
        cursor.setBlockFormat(block_format)
        cursor.insertText(text, char_format)
        cursor.insertBlock()
