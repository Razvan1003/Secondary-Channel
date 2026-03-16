"""
Secondary channel V1 for a MAVLink-based drone.

What this script does:
1. Connects to a MAVLink stream.
2. Monitors HEARTBEAT messages.
3. Stores the moment of the last heartbeat.
4. If no heartbeat is received for 5 seconds, it considers the primary link lost.
5. Prints clear messages in the console.
6. Sends one RTL command for each detected loss event.

Install dependency:
    pip install pymavlink

Run example:
    python secondary_channel_v1.py
"""

import sys
import time

try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlink is not installed.")
    print("Install it with: pip install pymavlink")
    sys.exit(1)


# Easy-to-change settings.
# For MAVProxy running in WSL and the script running on Windows, listen on all
# Windows interfaces so packets sent to the Windows host IP can be received.
MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.5


def timestamp():
    """Return a simple timestamp for console messages."""
    return time.strftime("%H:%M:%S")


def connect_mavlink():
    """
    Connect to the MAVLink stream and wait for the first HEARTBEAT.

    Waiting for the first heartbeat confirms that the script can see the drone.
    """
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
    """
    Send a single RTL command to the drone.

    This function is intentionally separate to keep the script easy to read.
    """
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
    """
    Monitor HEARTBEAT messages and detect link loss.

    The script sends RTL only once per loss event. If heartbeat returns later,
    the state is reset and a future loss can trigger RTL again.
    """
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
    """Entry point of the script."""
    try:
        master = connect_mavlink()
        monitor_heartbeat(master)
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Script stopped by user.")
    except Exception as error:
        print(f"[{timestamp()}] Error: {error}")


if __name__ == "__main__":
    main()
