import sys
import time

try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlink is not installed.")
    print("Install it with: pip install pymavlink")
    sys.exit(1)


MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.5


def timestamp():
    return time.strftime("%H:%M:%S")


def connect_mavlink():
    print(f"[{timestamp()}] Connecting to MAVLink stream: {MAVLINK_CONNECTION}")
    master = mavutil.mavlink_connection(MAVLINK_CONNECTION)

    print(f"[{timestamp()}] Waiting for first HEARTBEAT...")
    master.wait_heartbeat()
    print(
        f"[{timestamp()}] Connected. First HEARTBEAT received from "
        f"system {master.target_system}, component {master.target_component}."
    )

    return master


def send_rtl(master):
    print(f"[{timestamp()}] Sending RTL command...")

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
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

    print(f"[{timestamp()}] RTL command sent.")


def monitor_heartbeat(master):
    last_heartbeat_time = time.time()
    link_lost = False
    rtl_sent_for_current_loss = False

    print(f"[{timestamp()}] Heartbeat monitoring started.")

    while True:
        message = master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        current_time = time.time()

        if message is not None and message.get_type() == "HEARTBEAT":
            last_heartbeat_time = current_time

            if link_lost:
                print(f"[{timestamp()}] HEARTBEAT received again. Link restored.")

            link_lost = False
            rtl_sent_for_current_loss = False

            print(
                f"[{timestamp()}] HEARTBEAT received normally "
                f"(system {message.get_srcSystem()}, component {message.get_srcComponent()})."
            )

        if current_time - last_heartbeat_time > HEARTBEAT_TIMEOUT and not link_lost:
            link_lost = True
            print(f"[{timestamp()}] Primary link lost")
            print(f"[{timestamp()}] Secondary channel activated")

            if not rtl_sent_for_current_loss:
                send_rtl(master)
                rtl_sent_for_current_loss = True


def main():
    try:
        master = connect_mavlink()
        monitor_heartbeat(master)
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Script stopped by user.")
    except Exception as error:
        print(f"[{timestamp()}] Error: {error}")


if __name__ == "__main__":
    main()
