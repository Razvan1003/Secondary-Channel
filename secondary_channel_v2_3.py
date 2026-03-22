import os
import sys
import time

try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlink is not installed.")
    print("Install it with: pip install pymavlink")
    sys.exit(1)


MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
CHECK_INTERVAL = 0.2
HOLD_SEND_INTERVAL = 0.5
COMMAND_ACK_TIMEOUT = 3
HOLD_KEY = "h"
LAND_KEY = "d"
QUIT_KEY = "q"


if os.name == "nt":
    import msvcrt
else:
    import select


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


def connect_mavlink():
    log(f"Connecting to MAVLink stream: {MAVLINK_CONNECTION}")
    master = mavutil.mavlink_connection(MAVLINK_CONNECTION)

    log("Waiting for first vehicle HEARTBEAT...")
    while True:
        message = master.recv_match(
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
            "MAVLink stream connected. "
            f"Vehicle HEARTBEAT received from system {target_system}, "
            f"component {target_component}, mode {current_mode}."
        )
        return master, target_system, target_component


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


def send_guided_hold_target(master, target_system, target_component, hold_target):
    master.mav.set_position_target_global_int_send(
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


def capture_and_start_hold(master, latest_global_position, target_system, target_component):
    if latest_global_position is None:
        log("Cannot activate hold: no GLOBAL_POSITION_INT received yet.")
        return None

    hold_target = current_hold_target_from_global_position(latest_global_position)

    log("Manual secondary-channel activation requested.")
    log("Sending GUIDED hold target based on current position...")

    send_guided_hold_target(master, target_system, target_component, hold_target)

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

    return hold_target


def drain_messages(master):
    while master.recv_match(blocking=False) is not None:
        pass


def wait_for_command_ack(master, expected_command):
    deadline = monotonic_time() + COMMAND_ACK_TIMEOUT

    while monotonic_time() < deadline:
        message = master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if message is None or message.get_type() != "COMMAND_ACK":
            continue

        if message.command != expected_command:
            continue

        result_name = mav_result_name(message.result)
        log(f"COMMAND_ACK received for LAND: {result_name}")

        return message.result in (
            mavutil.mavlink.MAV_RESULT_ACCEPTED,
            mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
        )

    log("No COMMAND_ACK received for LAND.")
    return False


def send_land_and_wait_ack(master, target_system, target_component):
    drain_messages(master)

    log("Manual secondary-channel activation requested.")
    log("Sending LAND command...")

    master.mav.command_long_send(
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
        master,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
    )


def poll_user_key():
    if os.name == "nt":
        if not msvcrt.kbhit():
            return None

        key = msvcrt.getwch()
        if key in ("\r", "\n"):
            return None

        return key.lower()

    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None

    return sys.stdin.readline().strip().lower()


def monitor_and_wait_manual_activation(master, target_system, target_component):
    latest_global_position = None
    hold_active = False
    hold_target = None
    last_hold_send_time = 0.0
    land_requested = False

    log(
        "Heartbeat monitoring started for "
        f"system {target_system}, component {target_component}."
    )
    log(
        f"Press '{HOLD_KEY}' for GUIDED hold, "
        f"'{LAND_KEY}' for LAND, "
        f"'{QUIT_KEY}' to quit."
    )

    while True:
        message = master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if message is not None and message.get_type() == "GLOBAL_POSITION_INT":
            if message.get_srcSystem() == target_system:
                latest_global_position = message

        if is_relevant_heartbeat(message, target_system, target_component):
            current_mode = flight_mode_name(message)
            log(
                "HEARTBEAT received normally "
                f"(system {target_system}, component {target_component}, mode {current_mode})."
            )

        if hold_active and hold_target is not None:
            current_time = monotonic_time()
            if current_time - last_hold_send_time >= HOLD_SEND_INTERVAL:
                send_guided_hold_target(master, target_system, target_component, hold_target)
                last_hold_send_time = current_time

        user_key = poll_user_key()
        if user_key is None:
            continue

        if user_key == QUIT_KEY:
            log("Quit requested by user.")
            return

        if user_key == HOLD_KEY:
            if land_requested:
                log("LAND was already requested. Restart the script for a new session.")
                continue

            if hold_active:
                log("GUIDED hold is already active.")
                continue

            hold_target = capture_and_start_hold(
                master,
                latest_global_position,
                target_system,
                target_component,
            )

            if hold_target is None:
                continue

            hold_active = True
            last_hold_send_time = monotonic_time()
            log("Manual emergency action completed: GUIDED hold is active.")
            log("Script remains connected and refreshes the hold target until manual stop.")
            continue

        if user_key == LAND_KEY:
            if land_requested:
                log("LAND has already been requested in this session.")
                continue

            hold_active = False
            hold_target = None
            land_requested = True

            land_ok = send_land_and_wait_ack(master, target_system, target_component)

            if land_ok:
                log("Manual emergency action completed: LAND confirmed.")
            else:
                log("LAND command was issued, but confirmation failed.")

            log("Script remains connected for observation until manual stop.")
            continue

        log(
            f"Unknown command '{user_key}'. "
            f"Use '{HOLD_KEY}' for hold, '{LAND_KEY}' for land "
            f"or '{QUIT_KEY}' to quit."
        )


def main():
    master = None

    try:
        master, target_system, target_component = connect_mavlink()
        monitor_and_wait_manual_activation(master, target_system, target_component)
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Script stopped by user.")
    except Exception as error:
        log(f"Error: {error}")
    finally:
        if master is not None:
            master.close()


if __name__ == "__main__":
    main()
