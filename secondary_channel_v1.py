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
        log(
            "Monitor link connected. "
            f"Vehicle HEARTBEAT received from system {target_system}, "
            f"component {target_component}."
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

        log(
            "Command link connected. "
            f"Vehicle HEARTBEAT confirmed for system {target_system}, "
            f"component {target_component}."
        )
        return command_master


def drain_messages(master):
    while master.recv_match(blocking=False) is not None:
        pass


def wait_for_command_ack(command_master, expected_command):
    deadline = monotonic_time() + COMMAND_ACK_TIMEOUT

    while monotonic_time() < deadline:
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if message is None:
            continue

        if message.get_type() != "COMMAND_ACK":
            continue

        if message.command != expected_command:
            continue

        result_name = mav_result_name(message.result)
        log(f"COMMAND_ACK received for RTL: {result_name}")

        return message.result in (
            mavutil.mavlink.MAV_RESULT_ACCEPTED,
            mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
        )

    log("No COMMAND_ACK received for RTL.")
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
    )


def monitor_heartbeat(monitor_master, command_master, target_system, target_component):
    last_heartbeat_time = monotonic_time()
    emergency_active = False
    recovery_logged = False

    log(
        "Heartbeat monitoring started for "
        f"system {target_system}, component {target_component}."
    )

    while True:
        message = monitor_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        current_time = monotonic_time()

        if is_relevant_heartbeat(message, target_system, target_component):
            last_heartbeat_time = current_time

            if emergency_active:
                if not recovery_logged:
                    log("HEARTBEAT received again, but emergency state remains active.")
                    recovery_logged = True
            else:
                log(
                    "HEARTBEAT received normally "
                    f"(system {target_system}, component {target_component})."
                )

        if not emergency_active and current_time - last_heartbeat_time > HEARTBEAT_TIMEOUT:
            emergency_active = True
            recovery_logged = False

            log("Primary link lost")
            log("Secondary channel activated")

            rtl_ok = send_rtl_and_wait_ack(
                command_master,
                target_system,
                target_component,
            )

            if rtl_ok:
                log("Emergency action completed: RTL confirmed.")
            else:
                log("Emergency action issued, but RTL confirmation failed.")

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
