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
COMMAND_ACK_TIMEOUT = 3
ACTIVATE_KEYS = {"l", "d"}
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
    land_requested = False

    log(
        "Heartbeat monitoring started for "
        f"system {target_system}, component {target_component}."
    )
    log("Press 'l' or 'd' to activate LAND. Press 'q' to quit.")

    while True:
        message = master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if is_relevant_heartbeat(message, target_system, target_component):
            current_mode = flight_mode_name(message)
            log(
                "HEARTBEAT received normally "
                f"(system {target_system}, component {target_component}, mode {current_mode})."
            )

        user_key = poll_user_key()
        if user_key is None:
            continue

        if user_key == QUIT_KEY:
            log("Quit requested by user.")
            return

        if user_key not in ACTIVATE_KEYS:
            log(
                f"Unknown command '{user_key}'. "
                "Use 'l' or 'd' for LAND "
                f"or '{QUIT_KEY}' to quit."
            )
            continue

        if land_requested:
            log("LAND has already been requested in this session.")
            continue

        land_requested = True
        land_ok = send_land_and_wait_ack(master, target_system, target_component)

        if land_ok:
            log("Manual emergency action completed: LAND confirmed.")
        else:
            log("LAND command was issued, but confirmation failed.")

        log("Script remains connected for observation until manual stop.")


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
