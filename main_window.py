from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.mode_label = QLabel(self)
        self.sitl_console_status_label = QLabel(self)
        self.launch_mission_planner_button = QPushButton(
            "Launch Mission Planner",
            self,
        )
        self.failover_button = QPushButton("Trigger Failover", self)
        self.restore_button = QPushButton("Restore + Reset", self)
        self.remove_rule_button = QPushButton("Remove Rule", self)
        self.show_menu_button = QPushButton("Show Menu", self)
        self.observe_button = QPushButton("Observe", self)
        self.guided_button = QPushButton("GUIDED", self)
        self.rtl_button = QPushButton("RTL", self)
        self.hold_button = QPushButton("HOLD", self)
        self.land_button = QPushButton("LAND", self)
        self.arm_button = QPushButton("ARM", self)
        self.disarm_button = QPushButton("DISARM", self)
        self.takeoff_button = QPushButton("TAKEOFF", self)
        self.change_altitude_button = QPushButton("Change Altitude", self)
        self.primary_guided_button = QPushButton("Primary GUIDED", self)
        self.primary_rtl_button = QPushButton("Primary RTL", self)
        self.primary_hold_button = QPushButton("Primary HOLD", self)
        self.primary_land_button = QPushButton("Primary LAND", self)
        self.primary_arm_button = QPushButton("Primary ARM", self)
        self.primary_disarm_button = QPushButton("Primary DISARM", self)
        self.primary_takeoff_button = QPushButton("Primary TAKEOFF", self)
        self.primary_change_altitude_button = QPushButton(
            "Primary Change Altitude",
            self,
        )
        self.sitl_command_input = QLineEdit(self)
        self.send_sitl_command_button = QPushButton("Send WSL Command", self)
        self.secondary_command_input = QLineEdit(self)
        self.send_secondary_command_button = QPushButton(
            "Send Secondary Command",
            self,
        )
        self.takeoff_altitude_spin = QDoubleSpinBox(self)
        self.change_altitude_spin = QDoubleSpinBox(self)
        self.primary_takeoff_altitude_spin = QDoubleSpinBox(self)
        self.primary_change_altitude_spin = QDoubleSpinBox(self)

        self.takeoff_altitude_spin.setRange(0.5, 100.0)
        self.takeoff_altitude_spin.setDecimals(1)
        self.takeoff_altitude_spin.setSingleStep(0.5)
        self.takeoff_altitude_spin.setValue(5.0)
        self.takeoff_altitude_spin.setSuffix(" m")

        self.change_altitude_spin.setRange(0.5, 100.0)
        self.change_altitude_spin.setDecimals(1)
        self.change_altitude_spin.setSingleStep(0.5)
        self.change_altitude_spin.setValue(10.0)
        self.change_altitude_spin.setSuffix(" m")
        self.primary_takeoff_altitude_spin.setRange(0.5, 100.0)
        self.primary_takeoff_altitude_spin.setDecimals(1)
        self.primary_takeoff_altitude_spin.setSingleStep(0.5)
        self.primary_takeoff_altitude_spin.setValue(5.0)
        self.primary_takeoff_altitude_spin.setSuffix(" m")
        self.primary_change_altitude_spin.setRange(0.5, 100.0)
        self.primary_change_altitude_spin.setDecimals(1)
        self.primary_change_altitude_spin.setSingleStep(0.5)
        self.primary_change_altitude_spin.setValue(10.0)
        self.primary_change_altitude_spin.setSuffix(" m")
        self.sitl_command_input.setPlaceholderText(
            "Ex: mode guided, arm throttle, takeoff 5, output list"
        )
        self.secondary_command_input.setPlaceholderText(
            "Ex: m, q, r, g, h, l, a, d, t 5, c 10"
        )

        self._build_ui()
        self._connect_signals()
        self._update_buttons()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        session_group = QGroupBox("Session", self)
        session_layout = QGridLayout(session_group)
        session_layout.addWidget(self.mode_label, 0, 0, 1, 2)
        session_layout.addWidget(self.sitl_console_status_label, 1, 0, 1, 2)
        session_layout.addWidget(self.start_sitl_button, 2, 0)
        session_layout.addWidget(self.stop_sitl_button, 2, 1)
        session_layout.addWidget(self.start_secondary_button, 3, 0)
        session_layout.addWidget(self.stop_secondary_button, 3, 1)
        session_layout.addWidget(self.start_all_button, 4, 0)
        session_layout.addWidget(self.stop_all_button, 4, 1)
        session_layout.addWidget(self.launch_mission_planner_button, 5, 0, 1, 2)

        test_group = QGroupBox("Test", self)
        test_layout = QVBoxLayout(test_group)
        test_layout.addWidget(self.failover_button)
        test_layout.addWidget(self.restore_button)
        test_layout.addWidget(self.remove_rule_button)
        test_layout.addStretch(1)

        status_group = QGroupBox("Vehicle / Link Status", self)
        status_layout = QVBoxLayout(status_group)
        status_layout.addWidget(self.status_panel)

        control_group = QGroupBox("Secondary Commands", self)
        control_layout = QGridLayout(control_group)
        control_layout.addWidget(self.show_menu_button, 0, 0)
        control_layout.addWidget(self.observe_button, 0, 1)
        control_layout.addWidget(self.guided_button, 1, 0)
        control_layout.addWidget(self.rtl_button, 1, 1)
        control_layout.addWidget(self.hold_button, 2, 0)
        control_layout.addWidget(self.land_button, 2, 1)
        control_layout.addWidget(self.arm_button, 3, 0)
        control_layout.addWidget(self.disarm_button, 3, 1)
        control_layout.addWidget(QLabel("Takeoff Altitude", self), 4, 0)
        control_layout.addWidget(self.takeoff_altitude_spin, 4, 1)
        control_layout.addWidget(self.takeoff_button, 5, 0, 1, 2)
        control_layout.addWidget(QLabel("Change Altitude", self), 6, 0)
        control_layout.addWidget(self.change_altitude_spin, 6, 1)
        control_layout.addWidget(self.change_altitude_button, 7, 0, 1, 2)
        control_layout.addWidget(QLabel("Secondary Command", self), 8, 0)
        control_layout.addWidget(self.secondary_command_input, 8, 1)
        control_layout.addWidget(self.send_secondary_command_button, 9, 0, 1, 2)

        primary_group = QGroupBox("Primary / MAVProxy Commands", self)
        primary_layout = QGridLayout(primary_group)
        primary_layout.addWidget(self.primary_guided_button, 0, 0)
        primary_layout.addWidget(self.primary_rtl_button, 0, 1)
        primary_layout.addWidget(self.primary_hold_button, 1, 0)
        primary_layout.addWidget(self.primary_land_button, 1, 1)
        primary_layout.addWidget(self.primary_arm_button, 2, 0)
        primary_layout.addWidget(self.primary_disarm_button, 2, 1)
        primary_layout.addWidget(QLabel("Primary Takeoff Altitude", self), 3, 0)
        primary_layout.addWidget(self.primary_takeoff_altitude_spin, 3, 1)
        primary_layout.addWidget(self.primary_takeoff_button, 4, 0, 1, 2)
        primary_layout.addWidget(QLabel("Primary Target Altitude", self), 5, 0)
        primary_layout.addWidget(self.primary_change_altitude_spin, 5, 1)
        primary_layout.addWidget(
            self.primary_change_altitude_button,
            6,
            0,
            1,
            2,
        )

        wsl_group = QGroupBox("WSL / MAVProxy Console", self)
        wsl_layout = QGridLayout(wsl_group)
        wsl_layout.addWidget(QLabel("Command", self), 0, 0)
        wsl_layout.addWidget(self.sitl_command_input, 0, 1)
        wsl_layout.addWidget(self.send_sitl_command_button, 1, 0, 1, 2)

        controls_column = QVBoxLayout()
        controls_column.addWidget(session_group)
        controls_column.addWidget(test_group)
        controls_column.addWidget(status_group)
        controls_column.addWidget(control_group)
        controls_column.addWidget(primary_group)
        controls_column.addWidget(wsl_group)
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
        self.remove_rule_button.clicked.connect(self.manager.remove_firewall_rule)
        self.show_menu_button.clicked.connect(self.manager.secondary_show_menu)
        self.observe_button.clicked.connect(self.manager.secondary_observe)
        self.guided_button.clicked.connect(self.manager.secondary_guided)
        self.rtl_button.clicked.connect(self.manager.secondary_rtl)
        self.hold_button.clicked.connect(self.manager.secondary_hold)
        self.land_button.clicked.connect(self.manager.secondary_land)
        self.arm_button.clicked.connect(self.manager.secondary_arm)
        self.disarm_button.clicked.connect(self.manager.secondary_disarm)
        self.takeoff_button.clicked.connect(
            lambda: self.manager.secondary_takeoff(self.takeoff_altitude_spin.value())
        )
        self.change_altitude_button.clicked.connect(
            lambda: self.manager.secondary_change_altitude(
                self.change_altitude_spin.value()
            )
        )
        self.primary_guided_button.clicked.connect(self.manager.primary_guided)
        self.primary_rtl_button.clicked.connect(self.manager.primary_rtl)
        self.primary_hold_button.clicked.connect(self.manager.primary_hold)
        self.primary_land_button.clicked.connect(self.manager.primary_land)
        self.primary_arm_button.clicked.connect(self.manager.primary_arm)
        self.primary_disarm_button.clicked.connect(self.manager.primary_disarm)
        self.primary_takeoff_button.clicked.connect(
            lambda: self.manager.primary_takeoff(
                self.primary_takeoff_altitude_spin.value()
            )
        )
        self.primary_change_altitude_button.clicked.connect(
            lambda: self.manager.primary_change_altitude(
                self.primary_change_altitude_spin.value()
            )
        )
        self.send_sitl_command_button.clicked.connect(self._send_sitl_command)
        self.sitl_command_input.returnPressed.connect(self._send_sitl_command)
        self.send_secondary_command_button.clicked.connect(
            self._send_secondary_command
        )
        self.secondary_command_input.returnPressed.connect(
            self._send_secondary_command
        )

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
        hardware_mode = self.manager.config.hardware_mode

        self.mode_label.setText("HARDWARE MODE" if hardware_mode else "SITL MODE")
        self.mode_label.setStyleSheet(
            (
                "color: #c97a00; font-weight: bold;"
                if hardware_mode
                else "color: #1b8f3a; font-weight: bold;"
            )
        )
        self.sitl_console_status_label.setText(
            "WSL Console: CONNECTED"
            if sitl_running
            else "WSL Console: DISCONNECTED"
        )
        self.sitl_console_status_label.setStyleSheet(
            "color: #1b8f3a; font-weight: bold;"
            if sitl_running
            else "color: #b42318; font-weight: bold;"
        )

        self.start_sitl_button.setEnabled((not hardware_mode) and (not sitl_running))
        self.stop_sitl_button.setEnabled((not hardware_mode) and sitl_running)
        self.start_secondary_button.setEnabled(not secondary_running)
        self.stop_secondary_button.setEnabled(secondary_running)
        if hardware_mode:
            self.start_all_button.setEnabled(not secondary_running)
        else:
            self.start_all_button.setEnabled(not (sitl_running and secondary_running))
        self.stop_all_button.setEnabled(sitl_running or secondary_running)
        self.launch_mission_planner_button.setEnabled(True)
        self.failover_button.setEnabled((not hardware_mode) and secondary_running)
        self.restore_button.setEnabled(
            (not hardware_mode) and (sitl_running or secondary_running)
        )
        secondary_controls = [
            self.show_menu_button,
            self.observe_button,
            self.guided_button,
            self.rtl_button,
            self.hold_button,
            self.land_button,
            self.arm_button,
            self.disarm_button,
            self.takeoff_button,
            self.change_altitude_button,
            self.takeoff_altitude_spin,
            self.change_altitude_spin,
            self.secondary_command_input,
            self.send_secondary_command_button,
        ]
        for widget in secondary_controls:
            widget.setEnabled(secondary_running)
        primary_controls = [
            self.primary_guided_button,
            self.primary_rtl_button,
            self.primary_hold_button,
            self.primary_land_button,
            self.primary_arm_button,
            self.primary_disarm_button,
            self.primary_takeoff_button,
            self.primary_change_altitude_button,
            self.primary_takeoff_altitude_spin,
            self.primary_change_altitude_spin,
        ]
        for widget in primary_controls:
            widget.setEnabled(sitl_running)
        self.sitl_command_input.setEnabled(sitl_running)
        self.send_sitl_command_button.setEnabled(sitl_running)
        self.start_sitl_button.setToolTip(
            "Porneste ArduPilot SITL in WSL pentru simulare."
        )
        self.start_secondary_button.setToolTip(
            "Porneste scriptul secondary_channel_v4.py."
        )
        self.start_all_button.setToolTip(
            "In SITL Mode porneste SITL + Secondary. In Hardware Mode porneste doar Secondary."
        )
        self.failover_button.setToolTip(
            "Disabled in Hardware Mode"
            if hardware_mode
            else "In SITL Mode elimina output-ul MAVProxy catre UDP 14560 si aplica regula firewall."
        )
        self.restore_button.setToolTip(
            "Disabled in Hardware Mode"
            if hardware_mode
            else "Restaureaza linkul de monitorizare, opreste procesele si reporneste SITL + Secondary de la zero."
        )
        self.remove_rule_button.setToolTip(
            "Sterge doar regula firewall de failover, fara sa modifice output-ul MAVProxy."
        )
        self.show_menu_button.setToolTip(
            "Trimite m catre script si afiseaza meniul manual post-failover."
        )
        self.observe_button.setToolTip(
            "Trimite q catre script si revine la observare."
        )
        self.guided_button.setToolTip("Schimba modul in GUIDED.")
        self.rtl_button.setToolTip("Return to Launch.")
        self.hold_button.setToolTip("Mentine pozitia curenta in GUIDED/HOLD.")
        self.land_button.setToolTip("Aterizare controlata.")
        self.arm_button.setToolTip("Armeaza drona dupa prechecks.")
        self.disarm_button.setToolTip("Dezarmeaza drona doar in conditii sigure.")
        self.takeoff_button.setToolTip(
            "Trimite TAKEOFF cu altitudinea selectata."
        )
        self.change_altitude_button.setToolTip(
            "Trimite comanda de schimbare altitudine cu valoarea selectata."
        )
        self.primary_guided_button.setToolTip(
            "Trimite 'mode guided' catre MAVProxy pe canalul principal."
        )
        self.primary_rtl_button.setToolTip(
            "Trimite 'mode rtl' catre MAVProxy pe canalul principal."
        )
        self.primary_hold_button.setToolTip(
            "Trimite 'mode loiter' ca echivalent de hold pe canalul principal."
        )
        self.primary_land_button.setToolTip(
            "Trimite 'mode land' catre MAVProxy pe canalul principal."
        )
        self.primary_arm_button.setToolTip(
            "Trimite 'arm throttle' catre MAVProxy pe canalul principal."
        )
        self.primary_disarm_button.setToolTip(
            "Trimite 'disarm' catre MAVProxy pe canalul principal."
        )
        self.primary_takeoff_button.setToolTip(
            "Trimite secventa mode guided + arm throttle + takeoff ALT pe canalul principal."
        )
        self.primary_change_altitude_button.setToolTip(
            "Trimite mode guided + guided ALT pe canalul principal."
        )
        self.sitl_command_input.setToolTip(
            "Scrie comenzi MAVProxy/WSL exact ca in terminalul WSL."
        )
        self.send_sitl_command_button.setToolTip(
            "Trimite comanda catre procesul SITL/MAVProxy pornit din UI."
        )
        self.secondary_command_input.setToolTip(
            "Scrie comenzi pentru scriptul secondary: m, q, r, g, h, l, a, d, t 5, c 10."
        )
        self.send_secondary_command_button.setToolTip(
            "Trimite comanda catre scriptul secondary_channel_v4.py."
        )
        self.launch_mission_planner_button.setToolTip(
            "Launch Mission Planner. If no path is configured, the app will try to auto-detect it."
        )

    def _show_process_error(self, process_name: str, message: str) -> None:
        QMessageBox.warning(self, f"{process_name} Error", message)

    def _send_sitl_command(self) -> None:
        command_text = self.sitl_command_input.text().strip()
        if not command_text:
            return
        if self.manager.send_sitl_input(command_text):
            self.sitl_command_input.clear()

    def _send_secondary_command(self) -> None:
        command_text = self.secondary_command_input.text().strip()
        if not command_text:
            return
        if self.manager.send_secondary_console_input(command_text):
            self.secondary_command_input.clear()
