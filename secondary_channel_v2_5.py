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
ACTION_CHOICES = {
    "r": "rtl",
    "h": "hold",
    "l": "land",
}


def timestamp():
    return time.strftime("%H:%M:%S")


def monotonic_time():
    return time.monotonic()


def log(message):
    print(f"[{timestamp()}] {message}")


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
    log(f"Connecting monitor link: {MONITOR_CONNECTION}")
    monitor_master = mavutil.mavlink_connection(MONITOR_CONNECTION)

    log("Waiting for vehicle HEARTBEAT on monitor link...")
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
        current_mode = flight_mode_name(message)
        log(
            "Monitor link connected. "
            f"Vehicle HEARTBEAT received from system {target_system}, "
            f"component {target_component}, mode {current_mode}."
        )
        return monitor_master, target_system, target_component


def connect_command_link(target_system, target_component):
    log(f"Connecting command link: {COMMAND_CONNECTION}")
    command_master = mavutil.mavlink_connection(COMMAND_CONNECTION)

    log("Waiting for vehicle HEARTBEAT on command link...")
    while True:
        message = command_master.recv_match(
            type="HEARTBEAT",
            blocking=True,
            timeout=CHECK_INTERVAL,
        )
        if not is_relevant_heartbeat(message, target_system, target_component):
            continue

        current_mode = flight_mode_name(message)
        log(
            "Command link connected. "
            f"Vehicle HEARTBEAT confirmed for system {target_system}, "
            f"component {target_component}, mode {current_mode}."
        )
        return command_master


def select_emergency_action():
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

        log(f"Selected emergency action: {action.upper()}")
        return action


def drain_messages(master):
    while master.recv_match(blocking=False) is not None:
        pass


def poll_command_link_state(command_master, target_system):
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

    return latest_global_position


def capture_current_position(command_master, target_system):
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
            break

    return latest_global_position


def wait_for_command_ack(command_master, expected_command, label):
    deadline = monotonic_time() + COMMAND_ACK_TIMEOUT

    while monotonic_time() < deadline:
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if message is None or message.get_type() != "COMMAND_ACK":
            continue

        if message.command != expected_command:
            continue

        result_name = mav_result_name(message.result)
        log(f"COMMAND_ACK received for {label}: {result_name}")

        return message.result in (
            mavutil.mavlink.MAV_RESULT_ACCEPTED,
            mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
        )

    log(f"No COMMAND_ACK received for {label}.")
    return False


def send_rtl_and_wait_ack(command_master, target_system, target_component):
    drain_messages(command_master)

    log("Sending RTL command...")
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
    log("RTL command sent. Waiting for COMMAND_ACK...")

    return wait_for_command_ack(
        command_master,
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
        "RTL",
    )


def send_land_and_wait_ack(command_master, target_system, target_component):
    drain_messages(command_master)

    log("Sending LAND command...")
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
    log("LAND command sent. Waiting for COMMAND_ACK...")

    return wait_for_command_ack(
        command_master,
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


def start_hold(command_master, target_system, target_component, latest_global_position):
    if latest_global_position is None:
        latest_global_position = capture_current_position(command_master, target_system)

    if latest_global_position is None:
        log("Cannot activate HOLD: no GLOBAL_POSITION_INT available on command link.")
        return False, None

    hold_target = current_hold_target_from_global_position(latest_global_position)

    log("Sending GUIDED hold target based on current position...")
    send_guided_hold_target(command_master, target_system, target_component, hold_target)
    log(
        "GUIDED hold target sent. "
        f"Lat {hold_target['lat_int'] / 1e7:.7f}, "
        f"Lon {hold_target['lon_int'] / 1e7:.7f}, "
        f"RelAlt {hold_target['relative_alt_m']:.2f} m."
    )
    log(
        "SET_POSITION_TARGET messages do not return COMMAND_ACK. "
        "Confirmation is operational: vehicle should remain in GUIDED and hold position."
    )
    return True, hold_target


def execute_emergency_action(
    action,
    command_master,
    target_system,
    target_component,
    latest_global_position,
):
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
        latest_global_position,
    )
    return action_ok, True, hold_target


def monitor_heartbeat(monitor_master, command_master, target_system, target_component):
    last_heartbeat_time = monotonic_time()
    emergency_active = False
    recovery_logged = False
    hold_active = False
    hold_target = None
    last_hold_send_time = 0.0
    latest_monitor_global_position = None
    latest_command_global_position = None

    log(
        "Heartbeat monitoring started for "
        f"system {target_system}, component {target_component}."
    )
    while True:
        command_position = poll_command_link_state(command_master, target_system)
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

        if is_relevant_heartbeat(message, target_system, target_component):
            last_heartbeat_time = current_time

            if emergency_active:
                if not recovery_logged:
                    log("HEARTBEAT received again, but emergency state remains active.")
                    recovery_logged = True
            else:
                current_mode = flight_mode_name(message)
                log(
                    "HEARTBEAT received normally "
                    f"(system {target_system}, component {target_component}, mode {current_mode})."
                )

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

            log("Primary link lost")
            log("Secondary channel activated")
            action = select_emergency_action()

            action_ok, action_is_hold, returned_hold_target = execute_emergency_action(
                action,
                command_master,
                target_system,
                target_component,
                latest_command_global_position or latest_monitor_global_position,
            )

            if action_is_hold and action_ok:
                hold_active = True
                hold_target = returned_hold_target
                last_hold_send_time = monotonic_time()
                log("Emergency action completed: HOLD active.")
            elif action_ok:
                log(f"Emergency action completed: {action.upper()} confirmed.")
            else:
                log(f"Emergency action issued, but {action.upper()} confirmation failed.")

            log("System remains in emergency state until manual reset.")


def main():
    monitor_master = None
    command_master = None

    try:
        monitor_master, target_system, target_component = connect_monitor_link()
        command_master = connect_command_link(target_system, target_component)
        monitor_heartbeat(
            monitor_master,
            command_master,
            target_system,
            target_component,
        )
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Script stopped by user.")
    except Exception as error:
        log(f"Error: {error}")
    finally:
        if monitor_master is not None:
            monitor_master.close()
        if command_master is not None:
            command_master.close()


if __name__ == "__main__":
    main()
