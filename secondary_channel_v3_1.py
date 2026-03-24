import os
import sys
import time

try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlink is not installed.")
    print("Install it with: pip install pymavlink")
    sys.exit(1)


MONITOR_CONNECTION = "udpin:0.0.0.0:14560"
COMMAND_CONNECTION = "tcp:172.30.214.87:5762"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
HOLD_SEND_INTERVAL = 0.5
POSITION_CAPTURE_TIMEOUT = 1.0
GLOBAL_POSITION_INTERVAL_US = 500000
SECONDARY_HEARTBEAT_TIMEOUT = 1.5
SECONDARY_LOG_INTERVAL = 1.0
SECONDARY_NO_HEARTBEAT_RELOG_INTERVAL = 5.0
ACTION_CHOICES = {
    "r": "rtl",
    "h": "hold",
    "l": "land",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_PATH = os.path.join(
    SCRIPT_DIR,
    f"secondary_channel_v3_1_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
)

STATUS = {
    "current_mode": "UNKNOWN",
    "armed_state": "UNKNOWN",
    "current_altitude": None,
    "link_state": "STARTING",
    "_last_monitor_mode_logged": None,
    "_last_secondary_mode_logged": None,
}

LOG_FILE_HANDLE = None


def timestamp():
    return time.strftime("%H:%M:%S")


def monotonic_time():
    return time.monotonic()


def init_log_file():
    global LOG_FILE_HANDLE
    LOG_FILE_HANDLE = open(LOG_FILE_PATH, "a", encoding="utf-8", buffering=1)


def close_log_file():
    global LOG_FILE_HANDLE
    if LOG_FILE_HANDLE is not None:
        LOG_FILE_HANDLE.close()
        LOG_FILE_HANDLE = None


def format_altitude(altitude):
    if altitude is None:
        return "N/A"
    return f"{altitude:.2f}m"


def format_status(status):
    return (
        f"mode={status['current_mode']} "
        f"armed={status['armed_state']} "
        f"alt={format_altitude(status['current_altitude'])} "
        f"link={status['link_state']}"
    )


def write_log_line(line):
    print(line)
    if LOG_FILE_HANDLE is not None:
        LOG_FILE_HANDLE.write(line + "\n")
        LOG_FILE_HANDLE.flush()


def log_event(level, event, details="", status=None):
    current_status = STATUS if status is None else status
    details_part = f" {details}" if details else ""
    line = (
        f"[{timestamp()}] {level:<5} {event:<24}"
        f"{details_part} | {format_status(current_status)}"
    )
    write_log_line(line)


def mav_result_name(result):
    result_enum = mavutil.mavlink.enums["MAV_RESULT"].get(result)
    if result_enum is None:
        return f"UNKNOWN({result})"
    return result_enum.name


def is_vehicle_heartbeat(message):
    return (
        message is not None
        and message.get_type() == "HEARTBEAT"
        and message.autopilot != mavutil.mavlink.MAV_AUTOPILOT_INVALID
    )


def is_relevant_heartbeat(message, target_system, target_component):
    return (
        is_vehicle_heartbeat(message)
        and message.get_srcSystem() == target_system
        and message.get_srcComponent() == target_component
    )


def flight_mode_name(message):
    try:
        return mavutil.mode_string_v10(message)
    except Exception:
        return "UNKNOWN"


def armed_state_from_heartbeat(message):
    armed = bool(
        message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
    )
    return "ARMED" if armed else "DISARMED"


def update_status_from_heartbeat(status, message, link_state=None):
    status["current_mode"] = flight_mode_name(message)
    status["armed_state"] = armed_state_from_heartbeat(message)
    if link_state is not None:
        status["link_state"] = link_state


def update_status_from_global_position(status, message):
    status["current_altitude"] = message.relative_alt / 1000.0


def heading_radians_from_global_position(message):
    if message is None or getattr(message, "hdg", 65535) == 65535:
        return None
    return (message.hdg / 100.0) * 3.141592653589793 / 180.0


def current_hold_target_from_global_position(global_position):
    yaw = heading_radians_from_global_position(global_position)

    if yaw is None:
        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )
        yaw = 0.0
    else:
        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )

    return {
        "lat_int": global_position.lat,
        "lon_int": global_position.lon,
        "relative_alt_m": global_position.relative_alt / 1000.0,
        "yaw_rad": yaw,
        "type_mask": type_mask,
    }


def connect_monitor_link():
    log_event(
        "INFO",
        "SCRIPT_STARTED",
        f"log_file={os.path.basename(LOG_FILE_PATH)}",
    )
    monitor_master = mavutil.mavlink_connection(MONITOR_CONNECTION)

    while True:
        message = monitor_master.recv_match(
            type="HEARTBEAT",
            blocking=True,
            timeout=CHECK_INTERVAL,
        )
        if not is_vehicle_heartbeat(message):
            continue

        target_system = message.get_srcSystem()
        target_component = message.get_srcComponent()
        update_status_from_heartbeat(STATUS, message, "MONITOR_OK")
        log_event(
            "INFO",
            "MONITOR_LINK_CONNECTED",
            (
                f"connection={MONITOR_CONNECTION} "
                f"system={target_system} component={target_component}"
            ),
        )
        log_monitor_mode_if_changed()
        return monitor_master, target_system, target_component


def connect_command_link(target_system, target_component):
    command_master = mavutil.mavlink_connection(COMMAND_CONNECTION)

    while True:
        message = command_master.recv_match(
            type="HEARTBEAT",
            blocking=True,
            timeout=CHECK_INTERVAL,
        )
        if not is_relevant_heartbeat(message, target_system, target_component):
            continue

        update_status_from_heartbeat(STATUS, message, STATUS["link_state"])
        log_event(
            "INFO",
            "COMMAND_LINK_CONNECTED",
            (
                f"connection={COMMAND_CONNECTION} "
                f"system={target_system} component={target_component}"
            ),
        )
        request_global_position_int_stream(
            command_master,
            target_system,
            target_component,
        )
        return command_master


def log_monitor_mode_if_changed():
    current_mode = STATUS["current_mode"]
    if current_mode == "UNKNOWN":
        return

    if current_mode != STATUS["_last_monitor_mode_logged"]:
        STATUS["_last_monitor_mode_logged"] = current_mode
        log_event("INFO", "MODE_OBSERVED", f"source=monitor_link mode={current_mode}")


def log_secondary_mode_if_changed():
    current_mode = STATUS["current_mode"]
    if current_mode == "UNKNOWN":
        return

    if current_mode != STATUS["_last_secondary_mode_logged"]:
        STATUS["_last_secondary_mode_logged"] = current_mode
        log_event(
            "INFO",
            "SECONDARY_MODE_OBSERVED",
            f"mode={current_mode}",
        )


def select_emergency_action():
    log_event(
        "INFO",
        "ACTION_MENU_SHOWN",
        "options=RTL,HOLD,LAND",
    )
    print()
    print("Select emergency action:")
    print("  r = RTL")
    print("  h = HOLD")
    print("  l = LAND")

    while True:
        choice = input("Enter your choice (r/h/l): ").strip().lower()
        action = ACTION_CHOICES.get(choice)

        if action is None:
            print("Invalid choice. Use r, h or l.")
            continue

        log_event("INFO", "ACTION_SELECTED", f"action={action.upper()}")
        return action


def drain_messages(master):
    while master.recv_match(blocking=False) is not None:
        pass


def request_global_position_int_stream(command_master, target_system, target_component):
    command_master.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
        GLOBAL_POSITION_INTERVAL_US,
        0,
        0,
        0,
        0,
        0,
        0,
    )

    deadline = monotonic_time() + COMMAND_ACK_TIMEOUT
    while monotonic_time() < deadline:
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        if message is None:
            continue

        if message.get_type() != "COMMAND_ACK":
            continue

        if message.command != mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL:
            continue

        result_name = mav_result_name(message.result)
        log_event(
            "INFO",
            "COMMAND_ACK",
            (
                "command=MAV_CMD_SET_MESSAGE_INTERVAL "
                f"message=GLOBAL_POSITION_INT result={result_name}"
            ),
        )
        return

    log_event(
        "WARN",
        "COMMAND_ACK_MISSING",
        "command=MAV_CMD_SET_MESSAGE_INTERVAL message=GLOBAL_POSITION_INT",
    )


def poll_command_link_state(command_master, target_system, target_component):
    latest_global_position = None

    while True:
        message = command_master.recv_match(blocking=False)
        if message is None:
            break

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            latest_global_position = message
            update_status_from_global_position(STATUS, message)
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])

    return latest_global_position


def capture_current_position(command_master, target_system, target_component):
    deadline = monotonic_time() + POSITION_CAPTURE_TIMEOUT
    latest_global_position = None

    while monotonic_time() < deadline:
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            latest_global_position = message
            update_status_from_global_position(STATUS, message)
            break

        if is_relevant_heartbeat(message, target_system, target_component):
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])

    return latest_global_position


def wait_for_command_ack(
    command_master,
    target_system,
    target_component,
    expected_command,
    label,
):
    deadline = monotonic_time() + COMMAND_ACK_TIMEOUT

    while monotonic_time() < deadline:
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            update_status_from_global_position(STATUS, message)
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])
            continue

        if message.get_type() != "COMMAND_ACK":
            continue

        if message.command != expected_command:
            continue

        result_name = mav_result_name(message.result)
        log_event(
            "INFO",
            "COMMAND_ACK",
            f"command={label} result={result_name}",
        )

        return message.result in (
            mavutil.mavlink.MAV_RESULT_ACCEPTED,
            mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
        )

    log_event(
        "WARN",
        "COMMAND_ACK_MISSING",
        f"command={label} timeout={COMMAND_ACK_TIMEOUT:.1f}",
    )
    return False


def send_rtl_and_wait_ack(command_master, target_system, target_component):
    drain_messages(command_master)

    log_event(
        "INFO",
        "COMMAND_SENT",
        "command=MAV_CMD_NAV_RETURN_TO_LAUNCH",
    )
    command_master.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )

    return wait_for_command_ack(
        command_master,
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
        "RTL",
    )


def send_land_and_wait_ack(command_master, target_system, target_component):
    drain_messages(command_master)

    log_event(
        "INFO",
        "COMMAND_SENT",
        "command=MAV_CMD_NAV_LAND",
    )
    command_master.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )

    return wait_for_command_ack(
        command_master,
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
        "LAND",
    )


def send_guided_hold_target(command_master, target_system, target_component, hold_target):
    command_master.mav.set_position_target_global_int_send(
        0,
        target_system,
        target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        hold_target["type_mask"],
        hold_target["lat_int"],
        hold_target["lon_int"],
        hold_target["relative_alt_m"],
        0,
        0,
        0,
        0,
        0,
        0,
        hold_target["yaw_rad"],
        0,
    )


def start_hold(
    command_master,
    target_system,
    target_component,
    latest_command_global_position,
    latest_monitor_global_position,
):
    global_position = None

    if latest_command_global_position is not None:
        global_position = latest_command_global_position
        log_event(
            "INFO",
            "POSITION_SOURCE",
            "source=command_link",
        )
    elif latest_monitor_global_position is not None:
        global_position = latest_monitor_global_position
        log_event(
            "INFO",
            "POSITION_SOURCE",
            "source=monitor_link_fallback",
        )
    else:
        global_position = capture_current_position(
            command_master,
            target_system,
            target_component,
        )
        if global_position is not None:
            log_event(
                "INFO",
                "POSITION_SOURCE",
                "source=command_link_captured",
            )

    if global_position is None:
        log_event(
            "WARN",
            "POSITION_SOURCE",
            "source=unavailable",
        )
        return False, None

    hold_target = current_hold_target_from_global_position(global_position)

    log_event(
        "INFO",
        "COMMAND_SENT",
        (
            "command=GUIDED_HOLD "
            f"lat={hold_target['lat_int'] / 1e7:.7f} "
            f"lon={hold_target['lon_int'] / 1e7:.7f} "
            f"rel_alt={hold_target['relative_alt_m']:.2f}"
        ),
    )
    send_guided_hold_target(command_master, target_system, target_component, hold_target)
    return True, hold_target


def execute_emergency_action(
    action,
    command_master,
    target_system,
    target_component,
    latest_command_global_position,
    latest_monitor_global_position,
):
    log_event(
        "INFO",
        "ACTION_EXECUTION_STARTED",
        f"action={action.upper()}",
    )

    if action == "rtl":
        action_ok = send_rtl_and_wait_ack(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "land":
        action_ok = send_land_and_wait_ack(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    action_ok, hold_target = start_hold(
        command_master,
        target_system,
        target_component,
        latest_command_global_position,
        latest_monitor_global_position,
    )
    return action_ok, True, hold_target


def monitor_secondary_link(
    command_master,
    target_system,
    target_component,
    hold_active=False,
    hold_target=None,
):
    STATUS["link_state"] = "SECONDARY_ACTIVE"
    log_event(
        "INFO",
        "SECONDARY_LINK_OK",
        "command_link=connected",
    )

    last_secondary_heartbeat_time = monotonic_time()
    last_secondary_heartbeat_log_time = 0.0
    last_altitude_log_time = 0.0
    last_position_log_time = 0.0
    last_hold_send_time = 0.0
    last_secondary_no_heartbeat_log_time = None

    while True:
        current_time = monotonic_time()

        if hold_active and hold_target is not None:
            if current_time - last_hold_send_time >= HOLD_SEND_INTERVAL:
                send_guided_hold_target(
                    command_master,
                    target_system,
                    target_component,
                    hold_target,
                )
                last_hold_send_time = current_time

        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        current_time = monotonic_time()

        if message is None:
            if (
                last_secondary_heartbeat_time is not None
                and current_time - last_secondary_heartbeat_time > SECONDARY_HEARTBEAT_TIMEOUT
                and (
                    last_secondary_no_heartbeat_log_time is None
                    or current_time - last_secondary_no_heartbeat_log_time
                    >= SECONDARY_NO_HEARTBEAT_RELOG_INTERVAL
                )
            ):
                STATUS["link_state"] = "SECONDARY_NO_HEARTBEAT"
                log_event(
                    "WARN",
                    "SECONDARY_LINK_NO_HEARTBEAT",
                    (
                        f"timeout={SECONDARY_HEARTBEAT_TIMEOUT:.1f} "
                        "probable_loss_of_control=true"
                    ),
                )
                last_secondary_no_heartbeat_log_time = current_time
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            update_status_from_global_position(STATUS, message)

            if current_time - last_altitude_log_time >= SECONDARY_LOG_INTERVAL:
                log_event(
                    "INFO",
                    "SECONDARY_ALTITUDE_OBSERVED",
                    f"rel_alt={STATUS['current_altitude']:.2f}",
                )
                last_altitude_log_time = current_time

            if current_time - last_position_log_time >= SECONDARY_LOG_INTERVAL:
                log_event(
                    "INFO",
                    "SECONDARY_POSITION_OBSERVED",
                    f"lat={message.lat / 1e7:.7f} lon={message.lon / 1e7:.7f}",
                )
                last_position_log_time = current_time

            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            heartbeat_restored = STATUS["link_state"] == "SECONDARY_NO_HEARTBEAT"
            last_secondary_heartbeat_time = current_time
            STATUS["link_state"] = "SECONDARY_ACTIVE"
            update_status_from_heartbeat(STATUS, message, "SECONDARY_ACTIVE")
            if heartbeat_restored:
                log_event(
                    "INFO",
                    "SECONDARY_LINK_OK",
                    "command_link=heartbeat_restored",
                )

            if current_time - last_secondary_heartbeat_log_time >= SECONDARY_LOG_INTERVAL:
                log_event(
                    "INFO",
                    "SECONDARY_HEARTBEAT_OK",
                    f"mode={STATUS['current_mode']} armed={STATUS['armed_state']}",
                )
                last_secondary_heartbeat_log_time = current_time

            log_secondary_mode_if_changed()


def monitor_heartbeat(monitor_master, command_master, target_system, target_component):
    last_heartbeat_time = monotonic_time()
    emergency_active = False
    recovery_logged = False
    hold_active = False
    hold_target = None
    last_hold_send_time = 0.0
    latest_monitor_global_position = None
    latest_command_global_position = None

    STATUS["link_state"] = "MONITOR_OK"

    while True:
        command_position = poll_command_link_state(
            command_master,
            target_system,
            target_component,
        )
        if command_position is not None:
            latest_command_global_position = command_position

        message = monitor_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        current_time = monotonic_time()

        if (
            message is not None
            and message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            latest_monitor_global_position = message
            update_status_from_global_position(STATUS, message)

        if is_relevant_heartbeat(message, target_system, target_component):
            last_heartbeat_time = current_time
            update_status_from_heartbeat(
                STATUS,
                message,
                "SECONDARY_ACTIVE" if emergency_active else "MONITOR_OK",
            )

            if emergency_active:
                if not recovery_logged:
                    log_event(
                        "INFO",
                        "HEARTBEAT_OK",
                        "heartbeat received again on monitor link, emergency state still active",
                    )
                    recovery_logged = True
            else:
                log_event(
                    "INFO",
                    "HEARTBEAT_OK",
                    (
                        f"system={target_system} component={target_component} "
                        f"mode={STATUS['current_mode']}"
                    ),
                )

            log_monitor_mode_if_changed()

        if hold_active and hold_target is not None:
            if current_time - last_hold_send_time >= HOLD_SEND_INTERVAL:
                send_guided_hold_target(
                    command_master,
                    target_system,
                    target_component,
                    hold_target,
                )
                last_hold_send_time = current_time

        if not emergency_active and current_time - last_heartbeat_time > HEARTBEAT_TIMEOUT:
            emergency_active = True
            recovery_logged = False
            STATUS["link_state"] = "TIMEOUT"

            log_event(
                "WARN",
                "LINK_TIMEOUT",
                f"timeout={HEARTBEAT_TIMEOUT:.1f} probable_cause=heartbeat_timeout",
            )
            log_event(
                "WARN",
                "MONITOR_LINK_LOST",
                "source=monitor_link",
            )

            STATUS["link_state"] = "SECONDARY_ACTIVE"
            log_event(
                "WARN",
                "SECONDARY_ACTIVATED",
                "trigger=automatic",
            )
            action = select_emergency_action()

            action_ok, action_is_hold, returned_hold_target = execute_emergency_action(
                action,
                command_master,
                target_system,
                target_component,
                latest_command_global_position,
                latest_monitor_global_position,
            )

            if action_is_hold and action_ok:
                hold_active = True
                hold_target = returned_hold_target
                last_hold_send_time = monotonic_time()
                log_event(
                    "INFO",
                    "HOLD_ACTIVE",
                    f"mode={STATUS['current_mode']}",
                )

            if not action_ok:
                log_event(
                    "WARN",
                    "ACTION_EXECUTION_FAILED",
                    f"action={action.upper()}",
                )

            monitor_secondary_link(
                command_master,
                target_system,
                target_component,
                hold_active,
                hold_target,
            )
            return


def main():
    monitor_master = None
    command_master = None

    try:
        init_log_file()
        monitor_master, target_system, target_component = connect_monitor_link()
        command_master = connect_command_link(target_system, target_component)
        monitor_heartbeat(
            monitor_master,
            command_master,
            target_system,
            target_component,
        )
    except KeyboardInterrupt:
        log_event("INFO", "SCRIPT_STOPPED", "stopped_by=user")
    except Exception as error:
        log_event("ERROR", "SCRIPT_ERROR", f"message={error}")
    finally:
        if monitor_master is not None:
            monitor_master.close()
        if command_master is not None:
            command_master.close()
        close_log_file()


if __name__ == "__main__":
    main()
