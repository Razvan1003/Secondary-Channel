from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from process_manager import ProcessManager
from widgets.log_panel import LogPanel
from widgets.status_panel import StatusPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Secondary Channel Orchestrator")
        self.resize(1180, 760)

        self.manager = ProcessManager(parent=self)

        self.sitl_log = LogPanel(self)
        self.secondary_log = LogPanel(self)
        self.app_log = LogPanel(self)
        self.status_panel = StatusPanel(self)

        self.start_sitl_button = QPushButton("Start SITL", self)
        self.stop_sitl_button = QPushButton("Stop SITL", self)
        self.start_secondary_button = QPushButton("Start Secondary Channel", self)
        self.stop_secondary_button = QPushButton("Stop Secondary Channel", self)
        self.start_all_button = QPushButton("Start All", self)
        self.stop_all_button = QPushButton("Stop All", self)
        self.launch_mission_planner_button = QPushButton(
            "Launch Mission Planner",
            self,
        )
        self.failover_button = QPushButton("Trigger Failover", self)
        self.restore_button = QPushButton("Restore Link", self)

        self._build_ui()
        self._connect_signals()
        self._update_buttons()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        session_group = QGroupBox("Session", self)
        session_layout = QGridLayout(session_group)
        session_layout.addWidget(self.start_sitl_button, 0, 0)
        session_layout.addWidget(self.stop_sitl_button, 0, 1)
        session_layout.addWidget(self.start_secondary_button, 1, 0)
        session_layout.addWidget(self.stop_secondary_button, 1, 1)
        session_layout.addWidget(self.start_all_button, 2, 0)
        session_layout.addWidget(self.stop_all_button, 2, 1)
        session_layout.addWidget(self.launch_mission_planner_button, 3, 0, 1, 2)

        test_group = QGroupBox("Test", self)
        test_layout = QVBoxLayout(test_group)
        test_layout.addWidget(self.failover_button)
        test_layout.addWidget(self.restore_button)
        test_layout.addStretch(1)

        status_group = QGroupBox("Vehicle / Link Status", self)
        status_layout = QVBoxLayout(status_group)
        status_layout.addWidget(self.status_panel)

        controls_column = QVBoxLayout()
        controls_column.addWidget(session_group)
        controls_column.addWidget(test_group)
        controls_column.addWidget(status_group)
        controls_column.addStretch(1)

        tabs = QTabWidget(self)
        tabs.addTab(self.sitl_log, "SITL Log")
        tabs.addTab(self.secondary_log, "Secondary Log")
        tabs.addTab(self.app_log, "App Events")

        root_layout = QHBoxLayout(central)
        root_layout.addLayout(controls_column, 0)
        # Future direct-control UI can be added as another operator panel here.
        root_layout.addWidget(tabs, 1)

    def _connect_signals(self) -> None:
        self.start_sitl_button.clicked.connect(self.manager.start_sitl)
        self.stop_sitl_button.clicked.connect(self.manager.stop_sitl)
        self.start_secondary_button.clicked.connect(self.manager.start_secondary)
        self.stop_secondary_button.clicked.connect(self.manager.stop_secondary)
        self.start_all_button.clicked.connect(self.manager.start_all)
        self.stop_all_button.clicked.connect(self.manager.stop_all)
        self.launch_mission_planner_button.clicked.connect(
            self.manager.launch_mission_planner
        )
        self.failover_button.clicked.connect(self.manager.trigger_failover)
        self.restore_button.clicked.connect(self.manager.restore_link)

        self.manager.sitl_output.connect(self.sitl_log.append_line)
        self.manager.secondary_output.connect(self.secondary_log.append_line)
        self.manager.app_output.connect(self.app_log.append_line)
        self.manager.status_updated.connect(self.status_panel.update_status)
        self.manager.sitl_running_changed.connect(lambda _running: self._update_buttons())
        self.manager.secondary_running_changed.connect(
            lambda _running: self._update_buttons()
        )
        self.manager.process_error.connect(self._show_process_error)

    def _update_buttons(self) -> None:
        sitl_running = self.manager.sitl_running
        secondary_running = self.manager.secondary_running

        self.start_sitl_button.setEnabled(not sitl_running)
        self.stop_sitl_button.setEnabled(sitl_running)
        self.start_secondary_button.setEnabled(not secondary_running)
        self.stop_secondary_button.setEnabled(secondary_running)
        self.start_all_button.setEnabled(not (sitl_running and secondary_running))
        self.stop_all_button.setEnabled(sitl_running or secondary_running)
        mission_planner_configured = bool(self.manager.config.mission_planner_path)
        self.launch_mission_planner_button.setEnabled(mission_planner_configured)
        if mission_planner_configured:
            self.launch_mission_planner_button.setToolTip(
                self.manager.config.mission_planner_path
            )
        else:
            self.launch_mission_planner_button.setToolTip(
                "Set MISSION_PLANNER_PATH in config.py environment to enable this button."
            )

    def _show_process_error(self, process_name: str, message: str) -> None:
        QMessageBox.warning(self, f"{process_name} Error", message)
