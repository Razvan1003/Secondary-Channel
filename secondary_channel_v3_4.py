import math
import os
import sys
import time

MAVLINK_PROTOCOL_VERSION = 2
if MAVLINK_PROTOCOL_VERSION == 2:
    os.environ.setdefault("MAVLINK20", "1")

try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlink is not installed.")
    print("Install it with: pip install pymavlink")
    sys.exit(1)


def env_flag(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in ("1", "true", "yes", "on")


MONITOR_CONNECTION = os.environ.get(
    "SECONDARY_CHANNEL_MONITOR_CONNECTION",
    "udpin:0.0.0.0:14560",
).strip()
COMMAND_CONNECTION = os.environ.get(
    "SECONDARY_CHANNEL_COMMAND_CONNECTION",
    "tcp:127.0.0.1:5762",
).strip()
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
HOLD_SEND_INTERVAL = 0.5
POSITION_CAPTURE_TIMEOUT = 1.0
GLOBAL_POSITION_INTERVAL_US = 1000000
MONITOR_CONNECT_TIMEOUT = 10.0
SECONDARY_HEARTBEAT_TIMEOUT = 1.5
SECONDARY_LOG_INTERVAL = 1.0
SECONDARY_NO_HEARTBEAT_RELOG_INTERVAL = 5.0
SECONDARY_CONNECT_TIMEOUT = 10.0
COMMAND_RECONNECT_INTERVAL = 5.0
COMMAND_TRUST_ESTABLISH_TIMEOUT = 5.0
GCS_HEARTBEAT_INTERVAL = 1.0
ARM_DISARM_STATE_TIMEOUT = 5.0
TAKEOFF_STATE_TIMEOUT = 12.0
COMMAND_LOOP_OBSERVATION_WINDOW = 1.0
TAKEOFF_ALTITUDE_M = 5.0
TAKEOFF_MIN_CLIMB_M = 0.8
TAKEOFF_MAX_START_ALT_M = 0.5
DISARM_MAX_ALTITUDE_M = 0.5
CONTROLLED_FLIGHT_MIN_ALT_M = 0.8
YAW_STEP_DEG = 15.0
YAW_RATE_DEG_S = 15.0
YAW_EFFECT_TIMEOUT = 3.0
YAW_EFFECT_MIN_DEG = 5.0
MOVE_STEP_METERS = 1.0
MOVE_EFFECT_TIMEOUT = 4.0
MOVE_EFFECT_MIN_METERS = 0.3
SIGNING_ENABLED = env_flag("SECONDARY_CHANNEL_SIGNING_ENABLED", False)
MONITOR_SIGNING_ENABLED = env_flag(
    "SECONDARY_CHANNEL_MONITOR_SIGNING_ENABLED",
    SIGNING_ENABLED,
)
COMMAND_SIGNING_ENABLED = env_flag(
    "SECONDARY_CHANNEL_COMMAND_SIGNING_ENABLED",
    SIGNING_ENABLED,
)
SIGNING_KEY = os.environ.get(
    "SECONDARY_CHANNEL_SIGNING_KEY",
    "0123456789abcdef0123456789abcdef",
).strip()
MONITOR_SIGNING_LINK_ID = int(
    os.environ.get("SECONDARY_CHANNEL_MONITOR_SIGNING_LINK_ID", "11").strip()
)
COMMAND_SIGNING_LINK_ID = int(
    os.environ.get("SECONDARY_CHANNEL_COMMAND_SIGNING_LINK_ID", "12").strip()
)
SIGNING_INITIAL_TIMESTAMP = os.environ.get(
    "SECONDARY_CHANNEL_SIGNING_INITIAL_TIMESTAMP",
    "",
).strip()
MONITOR_UNSIGNED_POLICY = os.environ.get(
    "SECONDARY_CHANNEL_MONITOR_UNSIGNED_POLICY",
    "log_only",
).strip().lower()
COMMAND_UNSIGNED_POLICY = os.environ.get(
    "SECONDARY_CHANNEL_COMMAND_UNSIGNED_POLICY",
    "reject",
).strip().lower()
SECURITY_TEST_MODE = env_flag("SECONDARY_CHANNEL_SECURITY_TEST_MODE", False)
UNSIGNED_LOG_INTERVAL = 1.0
COMMAND_INBOUND_ALLOWLIST = {
    mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT: "HEARTBEAT",
    mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT: "GLOBAL_POSITION_INT",
    mavutil.mavlink.MAVLINK_MSG_ID_COMMAND_ACK: "COMMAND_ACK",
}
ACTION_CHOICES = {
    "r": "rtl",
    "h": "hold",
    "l": "land",
    "a": "arm",
    "d": "disarm",
    "t": "takeoff",
    "j": "yaw_left",
    "k": "yaw_right",
    "f": "move_forward",
    "n": "move_left",
    "q": "quit",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_PATH = os.path.join(
    SCRIPT_DIR,
    f"secondary_channel_v3_4_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
)

STATUS = {
    "current_mode": "UNKNOWN",
    "armed_state": "UNKNOWN",
    "current_altitude": None,
    "link_state": "STARTING",
    "command_observation_active": False,
    "command_control_trusted": False,
    "command_operational_proof_seen": False,
    "command_crypto_metadata_seen": False,
    "command_unsigned_seen": False,
    "command_signed_feedback_seen": False,
    "command_last_unsigned_time": None,
    "command_connected_time": None,
    "command_trust_timeout_logged": False,
    "_last_gcs_heartbeat_sent": 0.0,
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


def mark_command_observation_active():
    if STATUS["command_observation_active"]:
        return

    STATUS["command_observation_active"] = True
    log_event("INFO", "COMMAND_LINK_OBSERVABLE", "link=command")

    if command_signing_is_strict() and not STATUS["command_control_trusted"]:
        log_event(
            "WARN",
            "SIGNED_CONTROL_NOT_VERIFIED",
            "link=command mode=observation_only",
        )


def mark_command_control_untrusted(reason):
    was_trusted = STATUS["command_control_trusted"]
    STATUS["command_control_trusted"] = False

    if was_trusted:
        log_event(
            "WARN",
            "COMMAND_CONTROL_UNTRUSTED",
            f"link=command reason={reason}",
        )


def mark_command_control_trusted():
    STATUS["command_signed_feedback_seen"] = True
    STATUS["command_control_trusted"] = True


def reset_command_link_status():
    STATUS["command_observation_active"] = False
    STATUS["command_control_trusted"] = False
    STATUS["command_operational_proof_seen"] = False
    STATUS["command_crypto_metadata_seen"] = False
    STATUS["command_unsigned_seen"] = False
    STATUS["command_signed_feedback_seen"] = False
    STATUS["command_last_unsigned_time"] = None
    STATUS["command_connected_time"] = None
    STATUS["command_trust_timeout_logged"] = False


def close_master_safely(master):
    if master is None:
        return
    try:
        master.close()
    except Exception:
        pass


def validate_endpoint(label, endpoint):
    if not endpoint:
        raise ValueError(f"{label} endpoint is empty")
    if "<" in endpoint or ">" in endpoint:
        raise ValueError(
            f"{label} endpoint contains placeholder text: {endpoint}"
        )


def parse_signing_key(secret_text):
    if not secret_text:
        raise ValueError("signing key is empty")

    if len(secret_text) == 64:
        try:
            return bytes.fromhex(secret_text)
        except ValueError as error:
            raise ValueError("64-character signing key is not valid hex") from error

    key_bytes = secret_text.encode("utf-8")
    if len(key_bytes) == 32:
        return key_bytes

    raise ValueError(
        "signing key must be either 32 ASCII characters or 64 hex characters"
    )


def parse_initial_timestamp():
    if not SIGNING_INITIAL_TIMESTAMP:
        return None
    try:
        return int(SIGNING_INITIAL_TIMESTAMP)
    except ValueError as error:
        raise ValueError(
            "SECONDARY_CHANNEL_SIGNING_INITIAL_TIMESTAMP must be an integer"
        ) from error


def validate_signing_policy(link_label, policy):
    if policy not in ("reject", "log_only", "accept", "allowlist"):
        raise ValueError(
            (
                f"{link_label} signing policy must be one of: "
                "reject, log_only, accept, allowlist"
            )
        )


def effective_signing_policy(link_label, enabled, requested_policy):
    validate_signing_policy(link_label, requested_policy)

    if link_label == "command" and enabled:
        enforced_policy = "reject" if SECURITY_TEST_MODE else "allowlist"
        if requested_policy != enforced_policy:
            log_event(
                "WARN",
                "SECURITY_POLICY_OVERRIDDEN",
                (
                    f"link={link_label} requested_unsigned_policy={requested_policy} "
                    f"enforced_unsigned_policy={enforced_policy} "
                    "reason=command_path_outbound_strict"
                ),
            )
        return enforced_policy

    return requested_policy


def command_inbound_allowlist_name(msg_id):
    return COMMAND_INBOUND_ALLOWLIST.get(msg_id)


def make_unsigned_callback(link_label, policy):
    last_log_time = 0.0
    suppressed_count = 0

    def callback(*args):
        nonlocal last_log_time, suppressed_count
        if len(args) >= 2:
            msg_id = args[1]
        elif len(args) == 1:
            msg_id = args[0]
        else:
            msg_id = "UNKNOWN"

        current_time = monotonic_time()
        details = (
            f"link={link_label} msg_id={msg_id} "
            "reason=unsigned_or_invalid_signature"
        )
        if suppressed_count > 0:
            details = f"{details} suppressed={suppressed_count}"

        should_log = (current_time - last_log_time) >= UNSIGNED_LOG_INTERVAL
        allowed_message_name = None
        if link_label == "command":
            allowed_message_name = command_inbound_allowlist_name(msg_id)

        if policy == "allowlist":
            if link_label == "command":
                if allowed_message_name is not None:
                    allowlist_details = (
                        f"link={link_label} msg_id={msg_id} msg_name={allowed_message_name} "
                        "reason=unsigned_or_invalid_signature "
                        "allowlist=command_observation_feedback"
                    )
                    if suppressed_count > 0:
                        allowlist_details = (
                            f"{allowlist_details} suppressed={suppressed_count}"
                        )
                    if should_log:
                        log_event("WARN", "UNSIGNED_TELEMETRY_ACCEPTED", allowlist_details)
                        last_log_time = current_time
                        suppressed_count = 0
                    else:
                        suppressed_count += 1
                    return True

                reject_details = f"link=command msg_id={msg_id}"
                if suppressed_count > 0:
                    reject_details = f"{reject_details} suppressed={suppressed_count}"
                if should_log:
                    log_event("WARN", "UNSIGNED_NON_ALLOWLIST_REJECTED", reject_details)
                    last_log_time = current_time
                    suppressed_count = 0
                else:
                    suppressed_count += 1
                STATUS["command_unsigned_seen"] = True
                STATUS["command_last_unsigned_time"] = current_time
                if not STATUS["command_operational_proof_seen"]:
                    mark_command_observation_active()
                    mark_command_control_untrusted(
                        "unsigned_or_invalid_signed_feedback_seen"
                    )
                return False

            if allowed_message_name is not None:
                allowlist_details = (
                    f"link={link_label} msg_id={msg_id} msg_name={allowed_message_name} "
                    "reason=unsigned_or_invalid_signature "
                    "allowlist=command_observation_feedback"
                )
                if suppressed_count > 0:
                    allowlist_details = (
                        f"{allowlist_details} suppressed={suppressed_count}"
                    )
                if should_log:
                    log_event("WARN", "UNSIGNED_TELEMETRY_ACCEPTED", allowlist_details)
                    last_log_time = current_time
                    suppressed_count = 0
                else:
                    suppressed_count += 1
                return True

        if link_label == "command":
            STATUS["command_unsigned_seen"] = True
            STATUS["command_last_unsigned_time"] = current_time
            if not STATUS["command_operational_proof_seen"]:
                mark_command_observation_active()
                mark_command_control_untrusted(
                    "unsigned_or_invalid_signed_feedback_seen"
                )

        if policy == "reject":
            if should_log:
                log_event("WARN", "UNSIGNED_MESSAGE_REJECTED", details)
                last_log_time = current_time
                suppressed_count = 0
            else:
                suppressed_count += 1
            return False
        if policy == "log_only":
            if should_log:
                log_event("WARN", "UNSIGNED_MESSAGE_ACCEPTED", details)
                last_log_time = current_time
                suppressed_count = 0
            else:
                suppressed_count += 1
            return True
        return True

    return callback


def configure_link_signing(master, link_label, enabled, sign_outgoing, policy, link_id):
    try:
        effective_policy = effective_signing_policy(link_label, enabled, policy)

        if not enabled:
            log_event(
                "INFO",
                "SIGNING_NOT_ENABLED",
                f"link={link_label} policy={effective_policy}",
            )
            return

        secret_key = parse_signing_key(SIGNING_KEY)
        initial_timestamp = parse_initial_timestamp()
        allow_unsigned_callback = make_unsigned_callback(link_label, effective_policy)

        master.setup_signing(
            secret_key=secret_key,
            sign_outgoing=sign_outgoing,
            allow_unsigned_callback=allow_unsigned_callback,
            initial_timestamp=initial_timestamp,
            link_id=link_id,
        )
        if link_label == "command" and effective_policy in ("reject", "allowlist"):
            allowed_inbound = ",".join(COMMAND_INBOUND_ALLOWLIST.values())
            if effective_policy == "reject":
                enforcement_details = (
                    "link=command mode=full_reject "
                    "inbound_policy=reject allowed_unsigned_inbound=none"
                )
            else:
                enforcement_details = (
                    "link=command mode=outbound_strict "
                    "inbound_policy=allowlist "
                    f"allowed_unsigned_inbound={allowed_inbound}"
                )
            log_event(
                "INFO",
                "SECURITY_ENFORCEMENT_ACTIVE",
                enforcement_details,
            )
        log_event(
            "INFO",
            "SIGNING_ENABLED",
            (
                f"link={link_label} sign_outgoing={str(sign_outgoing).lower()} "
                f"policy={effective_policy} link_id={link_id}"
            ),
        )
        log_event(
            "INFO",
            "SECURITY_POLICY_APPLIED",
            f"link={link_label} unsigned_policy={effective_policy}",
        )
    except Exception as error:
        log_event(
            "ERROR",
            "SIGNING_CONFIG_INVALID",
            f"link={link_label} message={error}",
        )
        raise


def log_security_configuration():
    log_event(
        "INFO",
        "SIGNING_CONFIG_LOADED",
        (
            f"mavlink_version={MAVLINK_PROTOCOL_VERSION} "
            f"signing_enabled={str(SIGNING_ENABLED).lower()} "
            f"monitor_signing={str(MONITOR_SIGNING_ENABLED).lower()} "
            f"command_signing={str(COMMAND_SIGNING_ENABLED).lower()}"
        ),
    )
    if SECURITY_TEST_MODE:
        log_event(
            "INFO",
            "SECURITY_TEST_MODE_ACTIVE",
            "enabled=true",
        )


def open_mavlink_endpoint(event_name, endpoint):
    log_event(
        "INFO",
        event_name,
        f"endpoint={endpoint}",
    )
    validate_endpoint(event_name, endpoint)
    try:
        return mavutil.mavlink_connection(endpoint)
    except Exception as error:
        raise ConnectionError(
            f"{event_name} failed for endpoint={endpoint}: {error}"
        ) from error


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


def is_guided_mode(mode):
    if mode is None:
        return False
    return mode.upper().startswith("GUIDED")


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


def heading_degrees_from_global_position(message):
    if message is None or getattr(message, "hdg", 65535) == 65535:
        return None
    return message.hdg / 100.0


def normalize_heading_delta(delta_deg):
    while delta_deg > 180.0:
        delta_deg -= 360.0
    while delta_deg < -180.0:
        delta_deg += 360.0
    return delta_deg


def horizontal_distance_meters(lat1_int, lon1_int, lat2_int, lon2_int):
    lat1 = lat1_int / 1e7
    lon1 = lon1_int / 1e7
    lat2 = lat2_int / 1e7
    lon2 = lon2_int / 1e7

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = lat2_rad - lat1_rad
    dlon = math.radians(lon2 - lon1)
    mean_lat = (lat1_rad + lat2_rad) / 2.0
    earth_radius_m = 6371000.0

    x = dlon * math.cos(mean_lat)
    y = dlat
    return math.hypot(x, y) * earth_radius_m


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
    log_security_configuration()
    monitor_master = open_mavlink_endpoint(
        "MONITOR_CONNECT_ATTEMPT",
        MONITOR_CONNECTION,
    )
    configure_link_signing(
        monitor_master,
        "monitor",
        MONITOR_SIGNING_ENABLED,
        False,
        MONITOR_UNSIGNED_POLICY,
        MONITOR_SIGNING_LINK_ID,
    )
    deadline = monotonic_time() + MONITOR_CONNECT_TIMEOUT

    while monotonic_time() < deadline:
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
            "MONITOR_HEARTBEAT_RECEIVED",
            f"system={target_system} component={target_component}",
        )
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

    log_event(
        "WARN",
        "MONITOR_HEARTBEAT_TIMEOUT",
        (
            f"endpoint={MONITOR_CONNECTION} timeout={MONITOR_CONNECT_TIMEOUT:.1f} "
            "probable_cause=no_mavproxy_forwarding_to_windows"
        ),
    )
    raise TimeoutError(
        "Monitor link did not produce a vehicle HEARTBEAT. "
        f"endpoint={MONITOR_CONNECTION} timeout={MONITOR_CONNECT_TIMEOUT:.1f}s. "
        "If SITL/MAVProxy run in WSL and the script runs in Windows, use "
        "MAVProxy output to the Windows host IP:14560 and keep "
        "MONITOR_CONNECTION on udpin:0.0.0.0:14560."
    )


def connect_command_link(target_system, target_component):
    command_master = open_mavlink_endpoint(
        "SECONDARY_CONNECT_ATTEMPT",
        COMMAND_CONNECTION,
    )
    reset_command_link_status()
    configure_link_signing(
        command_master,
        "command",
        COMMAND_SIGNING_ENABLED,
        True,
        COMMAND_UNSIGNED_POLICY,
        COMMAND_SIGNING_LINK_ID,
    )
    STATUS["_last_gcs_heartbeat_sent"] = 0.0
    maybe_send_gcs_heartbeat(command_master, force=True)
    deadline = monotonic_time() + SECONDARY_CONNECT_TIMEOUT

    while monotonic_time() < deadline:
        maybe_send_gcs_heartbeat(command_master)
        message = command_master.recv_match(
            type="HEARTBEAT",
            blocking=True,
            timeout=CHECK_INTERVAL,
        )
        if not is_relevant_heartbeat(message, target_system, target_component):
            continue

        mark_command_observation_active()
        update_status_from_heartbeat(STATUS, message, STATUS["link_state"])
        STATUS["command_connected_time"] = monotonic_time()
        log_event(
            "INFO",
            "SECONDARY_HEARTBEAT_RECEIVED",
            f"system={target_system} component={target_component}",
        )
        log_event(
            "INFO",
            "COMMAND_LINK_CONNECTED",
            (
                f"connection={COMMAND_CONNECTION} "
                f"system={target_system} component={target_component}"
            ),
        )
        maybe_send_gcs_heartbeat(command_master, force=True)
        request_global_position_int_stream(
            command_master,
            target_system,
            target_component,
        )
        if command_signing_is_strict():
            if STATUS["command_operational_proof_seen"]:
                log_event("INFO", "COMMAND_LINK_TRUSTED", "link=command")
            else:
                log_event(
                    "WARN",
                    "SIGNED_CONTROL_NOT_VERIFIED",
                    "link=command reason=no_operational_command_ack",
                )
                log_event(
                    "WARN",
                    "COMMAND_LINK_CONNECTED_BUT_NOT_TRUSTED",
                    "link=command reason=no_operational_command_ack",
                )
        return command_master

    log_event(
        "ERROR",
        "SECONDARY_CONTROL_UNAVAILABLE",
        (
            f"endpoint={COMMAND_CONNECTION} timeout={SECONDARY_CONNECT_TIMEOUT:.1f} "
            "reason=no_secondary_heartbeat"
        ),
    )
    raise TimeoutError(
        "Secondary command link did not produce a vehicle HEARTBEAT. "
        f"endpoint={COMMAND_CONNECTION} timeout={SECONDARY_CONNECT_TIMEOUT:.1f}s. "
        "Verify MAVProxy exposes the secondary endpoint and the host/IP is reachable. "
        "If command-link signing is enabled, also verify that MAVProxy/vehicle use the "
        "same MAVLink2 signing key and that the vehicle accepts signed commands."
    )


def try_connect_command_link(target_system, target_component, reason):
    try:
        command_master = connect_command_link(target_system, target_component)
        log_event(
            "INFO",
            "SECONDARY_LINK_RECONNECTED",
            f"reason={reason}",
        )
        if command_signing_is_strict() and not command_link_is_trusted_for_control():
            log_event(
                "WARN",
                "SECONDARY_LINK_NOT_TRUSTED_YET",
                f"reason={reason}",
            )
        return command_master
    except Exception as error:
        log_event(
            "WARN",
            "SECONDARY_RECONNECT_FAILED",
            f"reason={reason} message={error}",
        )
        return None


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
        "options=RTL,HOLD,LAND,ARM,DISARM,TAKEOFF,YAW_LEFT,YAW_RIGHT,MOVE_FORWARD,MOVE_LEFT,QUIT",
    )
    print()
    print("Select emergency action:")
    print("  r = RTL")
    print("  h = HOLD")
    print("  l = LAND")
    print("  a = ARM")
    print("  d = DISARM")
    print("  t = TAKEOFF")
    print("  j = YAW LEFT")
    print("  k = YAW RIGHT")
    print("  f = MOVE FORWARD")
    print("  n = MOVE LEFT")
    print("  q = monitor only / exit command loop")

    while True:
        choice = input("Enter your choice (r/h/l/a/d/t/j/k/f/n/q): ").strip().lower()
        action = ACTION_CHOICES.get(choice)

        if action is None:
            log_event(
                "WARN",
                "COMMAND_REJECTED_IF_INVALID",
                f"choice={choice or '<empty>'}",
            )
            print("Invalid choice. Use r, h, l, a, d, t, j, k, f, n or q.")
            continue

        log_event("INFO", "ACTION_SELECTED", f"action={action.upper()}")
        return action


def drain_messages(master):
    while master.recv_match(blocking=False) is not None:
        pass


def send_gcs_heartbeat(master):
    master.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_GCS,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
        0,
        0,
        mavutil.mavlink.MAV_STATE_ACTIVE,
    )


def maybe_send_gcs_heartbeat(master, force=False):
    if master is None:
        return

    current_time = monotonic_time()
    last_sent = STATUS["_last_gcs_heartbeat_sent"]
    if not force and current_time - last_sent < GCS_HEARTBEAT_INTERVAL:
        return

    send_gcs_heartbeat(master)
    STATUS["_last_gcs_heartbeat_sent"] = current_time


def register_command_ack_proof(message, command_label):
    if message.result not in (
        mavutil.mavlink.MAV_RESULT_ACCEPTED,
        mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
    ):
        return

    STATUS["command_operational_proof_seen"] = True
    signed_metadata_present = bool(
        getattr(message, "_signed", False)
        or getattr(message, "signature", None)
    )
    if signed_metadata_present and not STATUS["command_crypto_metadata_seen"]:
        STATUS["command_crypto_metadata_seen"] = True
        log_event(
            "INFO",
            "SIGNED_METADATA_OBSERVED",
            "link=command message=COMMAND_ACK",
        )
    elif command_signing_is_strict():
        log_event(
            "WARN",
            "COMMAND_ACK_WITHOUT_SIGNED_METADATA",
            f"link=command command={command_label}",
        )

    if command_signing_is_strict():
        newly_trusted = not command_link_is_trusted_for_control()
        mark_command_control_trusted()
        if newly_trusted:
            log_event(
                "INFO",
                "COMMAND_CONTROL_TRUSTED",
                f"link=command proof=operational_command_ack command={command_label}",
            )


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
        maybe_send_gcs_heartbeat(command_master)
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
        register_command_ack_proof(message, "MAV_CMD_SET_MESSAGE_INTERVAL")
        return

    log_event(
        "WARN",
        "COMMAND_ACK_MISSING",
        "command=MAV_CMD_SET_MESSAGE_INTERVAL message=GLOBAL_POSITION_INT",
    )


def poll_command_link_state(command_master, target_system, target_component):
    if command_master is None:
        return None

    maybe_send_gcs_heartbeat(command_master)
    latest_global_position = None

    while True:
        message = command_master.recv_match(blocking=False)
        if message is None:
            break

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            mark_command_observation_active()
            latest_global_position = message
            update_status_from_global_position(STATUS, message)
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            mark_command_observation_active()
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
        maybe_send_gcs_heartbeat(command_master)
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)

        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            mark_command_observation_active()
            update_status_from_global_position(STATUS, message)
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            mark_command_observation_active()
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
        register_command_ack_proof(message, label)

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


def wait_for_mode(
    command_master,
    target_system,
    target_component,
    expected_mode,
    timeout=5.0,
):
    deadline = monotonic_time() + timeout

    while monotonic_time() < deadline:
        if STATUS["current_mode"] == expected_mode:
            log_event(
                "INFO",
                "MODE_CHANGE_CONFIRMED",
                f"mode={STATUS['current_mode']}",
            )
            return True

        maybe_send_gcs_heartbeat(command_master)
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            mark_command_observation_active()
            update_status_from_global_position(STATUS, message)
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            mark_command_observation_active()
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])
            if STATUS["current_mode"] == expected_mode:
                log_event(
                    "INFO",
                    "MODE_CHANGE_CONFIRMED",
                    f"mode={STATUS['current_mode']}",
                )
                return True

    log_event(
        "WARN",
        "MODE_CHANGE_NOT_CONFIRMED",
        f"expected={expected_mode} timeout={timeout:.1f}",
    )
    return False


# Mode changes are confirmed from HEARTBEAT.custom_mode.
def send_mode_change_and_confirm(
    command_master,
    target_system,
    target_component,
    mode_name,
    timeout=5.0,
):
    drain_messages(command_master)
    mode_map = command_master.mode_mapping() or {}
    mode_name = mode_name.upper()
    custom_mode = mode_map.get(mode_name)

    if custom_mode is None:
        log_event(
            "WARN",
            "MODE_CHANGE_NOT_FOUND",
            f"mode={mode_name}",
        )
        return False

    log_event(
        "INFO",
        "COMMAND_SENT",
        f"command=SET_MODE mode={mode_name} custom_mode={custom_mode}",
    )
    command_master.mav.set_mode_send(
        target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        custom_mode,
    )

    return wait_for_mode(
        command_master,
        target_system,
        target_component,
        mode_name,
        timeout=timeout,
    )


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

    ack_ok = wait_for_command_ack(
        command_master,
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
        "RTL",
    )
    if not ack_ok:
        return False

    return wait_for_mode(
        command_master,
        target_system,
        target_component,
        "RTL",
        timeout=8.0,
    )


# Command-long actions still rely on COMMAND_ACK.
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


def ensure_current_altitude(command_master, target_system, target_component):
    if STATUS["current_altitude"] is not None:
        return STATUS["current_altitude"]

    capture_current_position(command_master, target_system, target_component)
    return STATUS["current_altitude"]


def log_precheck_failed(action, reason):
    log_event(
        "WARN",
        "PRECHECK_FAILED",
        f"action={action} reason={reason}",
    )
    if reason.startswith("altitude_too_high") or reason.startswith("not_safely_airborne"):
        log_event(
            "WARN",
            "COMMAND_REJECTED_UNSAFE_STATE",
            f"action={action} reason={reason}",
        )
    else:
        log_event(
            "WARN",
            "COMMAND_REJECTED_INVALID_CONTEXT",
            f"action={action} reason={reason}",
        )


def send_arm_disarm_and_wait_ack(command_master, target_system, target_component, arm):
    drain_messages(command_master)
    param1 = 1 if arm else 0
    label = "ARM" if arm else "DISARM"

    log_event(
        "INFO",
        "COMMAND_SENT",
        f"command=MAV_CMD_COMPONENT_ARM_DISARM param1={param1}",
    )
    command_master.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        param1,
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
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        label,
    )


def wait_for_armed_state(
    command_master,
    target_system,
    target_component,
    expected_armed,
    timeout,
    success_event,
):
    deadline = monotonic_time() + timeout
    expected_label = "ARMED" if expected_armed else "DISARMED"

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
            if STATUS["armed_state"] == expected_label:
                log_event(
                    "INFO",
                    success_event,
                    f"armed_state={STATUS['armed_state']}",
                )
                return True

    log_event(
        "WARN",
        "ARMED_STATE_NOT_CONFIRMED",
        f"expected={expected_label} timeout={timeout:.1f}",
    )
    return False


def send_takeoff_and_wait_ack(command_master, target_system, target_component):
    drain_messages(command_master)

    log_event(
        "INFO",
        "COMMAND_SENT",
        f"command=MAV_CMD_NAV_TAKEOFF alt={TAKEOFF_ALTITUDE_M:.1f}",
    )
    command_master.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        TAKEOFF_ALTITUDE_M,
    )

    return wait_for_command_ack(
        command_master,
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        "TAKEOFF",
    )


def wait_for_takeoff_altitude(command_master, target_system, target_component, start_altitude):
    deadline = monotonic_time() + TAKEOFF_STATE_TIMEOUT
    target_altitude = start_altitude + TAKEOFF_MIN_CLIMB_M

    while monotonic_time() < deadline:
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            update_status_from_global_position(STATUS, message)
            if STATUS["current_altitude"] is not None:
                if STATUS["current_altitude"] >= target_altitude:
                    log_event(
                        "INFO",
                        "TAKEOFF_CONFIRMED",
                        (
                            f"alt={STATUS['current_altitude']:.2f} "
                            f"target={target_altitude:.2f}"
                        ),
                    )
                    return True
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])

    log_event(
        "WARN",
        "TAKEOFF_NOT_CONFIRMED",
        f"target_alt={target_altitude:.2f} timeout={TAKEOFF_STATE_TIMEOUT:.1f}",
    )
    return False


def precheck_arm():
    if STATUS["armed_state"] == "ARMED":
        log_precheck_failed("ARM", "already_armed")
        return False
    return True


def precheck_disarm(command_master, target_system, target_component):
    if STATUS["armed_state"] == "DISARMED":
        log_precheck_failed("DISARM", "already_disarmed")
        return False

    altitude = ensure_current_altitude(command_master, target_system, target_component)
    if altitude is None:
        log_precheck_failed("DISARM", "altitude_unknown")
        return False

    if altitude > DISARM_MAX_ALTITUDE_M:
        log_precheck_failed(
            "DISARM",
            f"altitude_too_high alt={altitude:.2f}",
        )
        return False

    return True


def precheck_takeoff(command_master, target_system, target_component):
    if STATUS["armed_state"] != "ARMED":
        log_precheck_failed("TAKEOFF", "not_armed")
        return False, None

    if not is_guided_mode(STATUS["current_mode"]):
        log_precheck_failed(
            "TAKEOFF",
            f"mode_not_guided mode={STATUS['current_mode']}",
        )
        return False, None

    altitude = ensure_current_altitude(command_master, target_system, target_component)
    if altitude is None:
        log_precheck_failed("TAKEOFF", "altitude_unknown")
        return False, None

    if altitude > TAKEOFF_MAX_START_ALT_M:
        log_precheck_failed(
            "TAKEOFF",
            f"already_airborne alt={altitude:.2f}",
        )
        return False, None

    return True, altitude


def precheck_guided_in_air(action, command_master, target_system, target_component):
    if STATUS["armed_state"] != "ARMED":
        log_precheck_failed(action, "not_armed")
        return False, None

    if not is_guided_mode(STATUS["current_mode"]):
        log_precheck_failed(
            action,
            f"mode_not_guided mode={STATUS['current_mode']}",
        )
        return False, None

    global_position = capture_current_position(
        command_master,
        target_system,
        target_component,
    )
    if global_position is None:
        log_precheck_failed(action, "position_unavailable")
        return False, None

    altitude = STATUS["current_altitude"]
    if altitude is None:
        log_precheck_failed(action, "altitude_unknown")
        return False, None

    if altitude < CONTROLLED_FLIGHT_MIN_ALT_M:
        log_precheck_failed(
            action,
            f"not_safely_airborne alt={altitude:.2f}",
        )
        return False, None

    return True, global_position


def command_signing_is_strict():
    return COMMAND_SIGNING_ENABLED


def command_control_block_reason():
    if command_signing_is_strict() and not STATUS["command_operational_proof_seen"]:
        return "no_operational_command_ack"
    if STATUS["command_unsigned_seen"]:
        return "unsigned_or_invalid_signed_feedback_seen"
    if STATUS["command_observation_active"]:
        return "command_link_observation_only"
    return "signed_control_not_verified"


def command_link_is_trusted_for_control():
    if not command_signing_is_strict():
        return True
    return (
        STATUS["command_control_trusted"]
        and STATUS["command_operational_proof_seen"]
    )


def should_reconnect_command_link(command_master):
    if command_master is None:
        return True
    if STATUS["link_state"] == "SECONDARY_NO_HEARTBEAT":
        return True
    if (
        command_signing_is_strict()
        and not command_link_is_trusted_for_control()
        and STATUS["command_connected_time"] is not None
        and monotonic_time() - STATUS["command_connected_time"]
        >= COMMAND_TRUST_ESTABLISH_TIMEOUT
    ):
        return True
    return False


def send_arm_and_confirm(command_master, target_system, target_component):
    if not precheck_arm():
        return False

    ack_ok = send_arm_disarm_and_wait_ack(
        command_master,
        target_system,
        target_component,
        True,
    )
    if not ack_ok:
        return False

    return wait_for_armed_state(
        command_master,
        target_system,
        target_component,
        True,
        ARM_DISARM_STATE_TIMEOUT,
        "ARM_CONFIRMED",
    )


def send_disarm_and_confirm(command_master, target_system, target_component):
    if not precheck_disarm(command_master, target_system, target_component):
        return False

    ack_ok = send_arm_disarm_and_wait_ack(
        command_master,
        target_system,
        target_component,
        False,
    )
    if not ack_ok:
        return False

    return wait_for_armed_state(
        command_master,
        target_system,
        target_component,
        False,
        ARM_DISARM_STATE_TIMEOUT,
        "DISARM_CONFIRMED",
    )


def send_takeoff_and_confirm(command_master, target_system, target_component):
    ok, start_altitude = precheck_takeoff(
        command_master,
        target_system,
        target_component,
    )
    if not ok:
        return False

    ack_ok = send_takeoff_and_wait_ack(
        command_master,
        target_system,
        target_component,
    )
    if not ack_ok:
        return False

    return wait_for_takeoff_altitude(
        command_master,
        target_system,
        target_component,
        start_altitude,
    )


def send_yaw_command_and_wait_ack(
    command_master,
    target_system,
    target_component,
    angle_deg,
    direction,
    label,
):
    drain_messages(command_master)

    log_event(
        "INFO",
        "YAW_COMMAND_SENT",
        f"direction={label} angle_deg={angle_deg:.1f} relative=true",
    )
    log_event(
        "INFO",
        "COMMAND_SENT",
        f"command=MAV_CMD_CONDITION_YAW direction={label} angle_deg={angle_deg:.1f}",
    )
    command_master.mav.command_long_send(
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_CONDITION_YAW,
        0,
        angle_deg,
        YAW_RATE_DEG_S,
        direction,
        1,
        0,
        0,
        0,
        0,
    )

    return wait_for_command_ack(
        command_master,
        target_system,
        target_component,
        mavutil.mavlink.MAV_CMD_CONDITION_YAW,
        f"CONDITION_YAW_{label.upper()}",
    )


def observe_yaw_effect(
    command_master,
    target_system,
    target_component,
    start_heading_deg,
    label,
):
    if start_heading_deg is None:
        log_event(
            "WARN",
            "YAW_EFFECT_NOT_OBSERVED",
            f"direction={label} reason=heading_unavailable",
        )
        return False

    deadline = monotonic_time() + YAW_EFFECT_TIMEOUT

    while monotonic_time() < deadline:
        maybe_send_gcs_heartbeat(command_master)
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            update_status_from_global_position(STATUS, message)
            current_heading_deg = heading_degrees_from_global_position(message)
            if current_heading_deg is None:
                continue

            delta_deg = normalize_heading_delta(current_heading_deg - start_heading_deg)
            if label == "left" and delta_deg <= -YAW_EFFECT_MIN_DEG:
                log_event(
                    "INFO",
                    "YAW_EFFECT_OBSERVED",
                    f"direction={label} delta_deg={delta_deg:.1f} heading={current_heading_deg:.1f}",
                )
                return True
            if label == "right" and delta_deg >= YAW_EFFECT_MIN_DEG:
                log_event(
                    "INFO",
                    "YAW_EFFECT_OBSERVED",
                    f"direction={label} delta_deg={delta_deg:.1f} heading={current_heading_deg:.1f}",
                )
                return True
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])

    log_event(
        "WARN",
        "YAW_EFFECT_NOT_OBSERVED",
        f"direction={label} timeout={YAW_EFFECT_TIMEOUT:.1f}",
    )
    return False


# Movement uses position targets, not mode changes or COMMAND_LONG.
def send_move_command(
    command_master,
    target_system,
    target_component,
    x_m,
    y_m,
    label,
):
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

    log_event(
        "INFO",
        "MOVE_COMMAND_SENT",
        f"direction={label} distance_m={MOVE_STEP_METERS:.2f}",
    )
    log_event(
        "INFO",
        "COMMAND_SENT",
        (
            "command=SET_POSITION_TARGET_LOCAL_NED "
            f"frame=BODY_OFFSET_NED x={x_m:.2f} y={y_m:.2f} z=0.00"
        ),
    )
    command_master.mav.set_position_target_local_ned_send(
        0,
        target_system,
        target_component,
        mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
        type_mask,
        x_m,
        y_m,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )


def observe_movement_effect(
    command_master,
    target_system,
    target_component,
    start_global_position,
    label,
):
    if start_global_position is None:
        log_event(
            "WARN",
            "MOVEMENT_EFFECT_NOT_OBSERVED",
            f"action={label} reason=position_unavailable",
        )
        return False

    deadline = monotonic_time() + MOVE_EFFECT_TIMEOUT
    start_lat_int = start_global_position.lat
    start_lon_int = start_global_position.lon

    while monotonic_time() < deadline:
        maybe_send_gcs_heartbeat(command_master)
        message = command_master.recv_match(blocking=True, timeout=CHECK_INTERVAL)
        if message is None:
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            update_status_from_global_position(STATUS, message)
            distance_m = horizontal_distance_meters(
                start_lat_int,
                start_lon_int,
                message.lat,
                message.lon,
            )
            if distance_m >= MOVE_EFFECT_MIN_METERS:
                log_event(
                    "INFO",
                    "MOVEMENT_EFFECT_OBSERVED",
                    f"action={label} distance_m={distance_m:.2f}",
                )
                return True
            continue

        if is_relevant_heartbeat(message, target_system, target_component):
            update_status_from_heartbeat(STATUS, message, STATUS["link_state"])

    log_event(
        "WARN",
        "MOVEMENT_EFFECT_NOT_OBSERVED",
        f"action={label} timeout={MOVE_EFFECT_TIMEOUT:.1f}",
    )
    return False


def send_yaw_left(command_master, target_system, target_component):
    ok, global_position = precheck_guided_in_air(
        "YAW_LEFT",
        command_master,
        target_system,
        target_component,
    )
    if not ok:
        return False

    start_heading_deg = heading_degrees_from_global_position(global_position)
    ack_ok = send_yaw_command_and_wait_ack(
        command_master,
        target_system,
        target_component,
        YAW_STEP_DEG,
        -1,
        "left",
    )
    if not ack_ok:
        return False

    observe_yaw_effect(
        command_master,
        target_system,
        target_component,
        start_heading_deg,
        "left",
    )
    return True


def send_yaw_right(command_master, target_system, target_component):
    ok, global_position = precheck_guided_in_air(
        "YAW_RIGHT",
        command_master,
        target_system,
        target_component,
    )
    if not ok:
        return False

    start_heading_deg = heading_degrees_from_global_position(global_position)
    ack_ok = send_yaw_command_and_wait_ack(
        command_master,
        target_system,
        target_component,
        YAW_STEP_DEG,
        1,
        "right",
    )
    if not ack_ok:
        return False

    observe_yaw_effect(
        command_master,
        target_system,
        target_component,
        start_heading_deg,
        "right",
    )
    return True


def send_move_forward(command_master, target_system, target_component):
    ok, global_position = precheck_guided_in_air(
        "MOVE_FORWARD",
        command_master,
        target_system,
        target_component,
    )
    if not ok:
        return False

    send_move_command(
        command_master,
        target_system,
        target_component,
        MOVE_STEP_METERS,
        0.0,
        "forward",
    )
    observe_movement_effect(
        command_master,
        target_system,
        target_component,
        global_position,
        "MOVE_FORWARD",
    )
    return True


def send_move_left(command_master, target_system, target_component):
    ok, global_position = precheck_guided_in_air(
        "MOVE_LEFT",
        command_master,
        target_system,
        target_component,
    )
    if not ok:
        return False

    send_move_command(
        command_master,
        target_system,
        target_component,
        0.0,
        -MOVE_STEP_METERS,
        "left",
    )
    observe_movement_effect(
        command_master,
        target_system,
        target_component,
        global_position,
        "MOVE_LEFT",
    )
    return True


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
    if not command_link_is_trusted_for_control():
        log_event(
            "ERROR",
            "SECURITY_POLICY_BLOCKED_COMMAND",
            f"reason={command_control_block_reason()}",
        )
        return False, False, None

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

    if action == "arm":
        action_ok = send_arm_and_confirm(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "disarm":
        action_ok = send_disarm_and_confirm(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "takeoff":
        action_ok = send_takeoff_and_confirm(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "yaw_left":
        action_ok = send_yaw_left(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "yaw_right":
        action_ok = send_yaw_right(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "move_forward":
        action_ok = send_move_forward(
            command_master,
            target_system,
            target_component,
        )
        return action_ok, False, None

    if action == "move_left":
        action_ok = send_move_left(
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
    observation_window=None,
    announce_link=True,
):
    STATUS["link_state"] = "SECONDARY_ACTIVE"
    if announce_link:
        log_event(
            "INFO",
            "SECONDARY_LINK_OK",
            "command_link=connected",
        )

    observation_start_time = monotonic_time()
    last_secondary_heartbeat_time = monotonic_time()
    last_secondary_heartbeat_log_time = 0.0
    last_altitude_log_time = 0.0
    last_position_log_time = 0.0
    last_hold_send_time = 0.0
    last_secondary_no_heartbeat_log_time = None

    while True:
        current_time = monotonic_time()

        if (
            observation_window is not None
            and current_time - observation_start_time >= observation_window
        ):
            return "continue_secondary"

        maybe_send_gcs_heartbeat(command_master)

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
                if command_signing_is_strict():
                    log_event(
                        "ERROR",
                        "SECONDARY_CONTROL_UNAVAILABLE",
                        "reason=no_valid_secondary_heartbeat_for_strict_policy",
                    )
                last_secondary_no_heartbeat_log_time = current_time
                return "secondary_lost"
            continue

        if (
            message.get_type() == "GLOBAL_POSITION_INT"
            and message.get_srcSystem() == target_system
        ):
            mark_command_observation_active()
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
            mark_command_observation_active()
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


def secondary_command_loop(
    command_master,
    target_system,
    target_component,
    latest_monitor_global_position,
    latest_command_global_position,
    hold_active=False,
    hold_target=None,
):
    log_event(
        "INFO",
        "COMMAND_LOOP_ACTIVE",
        "mode=post_failover",
    )

    first_observation = True
    last_security_block_log_time = 0.0

    while True:
        command_position = poll_command_link_state(
            command_master,
            target_system,
            target_component,
        )
        if command_position is not None:
            latest_command_global_position = command_position

        secondary_status = monitor_secondary_link(
            command_master,
            target_system,
            target_component,
            hold_active,
            hold_target,
            observation_window=COMMAND_LOOP_OBSERVATION_WINDOW,
            announce_link=first_observation,
        )
        first_observation = False
        if secondary_status == "secondary_lost":
            return {
                "hold_active": hold_active,
                "hold_target": hold_target,
                "session_result": "secondary_lost",
            }

        if not command_link_is_trusted_for_control():
            current_time = monotonic_time()
            if (
                current_time - last_security_block_log_time
                >= SECONDARY_NO_HEARTBEAT_RELOG_INTERVAL
            ):
                log_event(
                    "ERROR",
                    "SECURITY_POLICY_BLOCKED_COMMAND",
                    f"reason={command_control_block_reason()}",
                )
                last_security_block_log_time = current_time
            return {
                "hold_active": hold_active,
                "hold_target": hold_target,
                "session_result": "secondary_lost",
            }

        action = select_emergency_action()
        if action == "quit":
            log_event(
                "INFO",
                "COMMAND_LOOP_EXITED",
                "mode=monitor_only",
            )
            return {
                "hold_active": hold_active,
                "hold_target": hold_target,
                "session_result": "monitor_only",
            }

        command_position = poll_command_link_state(
            command_master,
            target_system,
            target_component,
        )
        if command_position is not None:
            latest_command_global_position = command_position

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
            log_event(
                "INFO",
                "HOLD_ACTIVE",
                f"mode={STATUS['current_mode']}",
            )
        elif action_ok:
            hold_active = False
            hold_target = None
        else:
            log_event(
                "WARN",
                "COMMAND_REJECTED_IF_INVALID",
                f"action={action.upper()} reason=precheck_or_execution_failed",
            )
            log_event(
                "WARN",
                "ACTION_EXECUTION_FAILED",
                f"action={action.upper()}",
            )

        secondary_status = monitor_secondary_link(
            command_master,
            target_system,
            target_component,
            hold_active,
            hold_target,
            observation_window=COMMAND_LOOP_OBSERVATION_WINDOW,
            announce_link=False,
        )
        if secondary_status == "secondary_lost":
            return {
                "hold_active": hold_active,
                "hold_target": hold_target,
                "session_result": "secondary_lost",
            }
        log_event(
            "INFO",
            "COMMAND_LOOP_CONTINUE",
            f"hold_active={'true' if hold_active else 'false'}",
        )


def monitor_heartbeat(monitor_master, command_master, target_system, target_component):
    last_heartbeat_time = monotonic_time()
    emergency_active = False
    recovery_logged = False
    hold_active = False
    hold_target = None
    last_hold_send_time = 0.0
    latest_monitor_global_position = None
    latest_command_global_position = None
    secondary_session_started = False
    secondary_monitor_only = False
    last_command_reconnect_attempt = 0.0
    security_block_logged = False

    STATUS["link_state"] = "MONITOR_OK"

    while True:
        current_time = monotonic_time()
        if should_reconnect_command_link(command_master):
            if (
                command_master is not None
                and command_signing_is_strict()
                and not command_link_is_trusted_for_control()
                and STATUS["command_connected_time"] is not None
                and current_time - STATUS["command_connected_time"]
                >= COMMAND_TRUST_ESTABLISH_TIMEOUT
                and not STATUS["command_trust_timeout_logged"]
            ):
                log_event(
                    "WARN",
                    "COMMAND_TRUST_ESTABLISH_TIMEOUT",
                    f"link=command timeout={COMMAND_TRUST_ESTABLISH_TIMEOUT:.1f}",
                )
                STATUS["command_trust_timeout_logged"] = True

            if current_time - last_command_reconnect_attempt >= COMMAND_RECONNECT_INTERVAL:
                close_master_safely(command_master)
                command_master = None
                reset_command_link_status()
                last_command_reconnect_attempt = current_time
                command_master = try_connect_command_link(
                    target_system,
                    target_component,
                    "reconnect",
                )
                secondary_monitor_only = False

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
                        "PRIMARY_LINK_RECOVERED",
                        "monitor_heartbeat_restored=true emergency_state_unchanged",
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
            secondary_session_started = False
            secondary_monitor_only = False
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

        if emergency_active and not secondary_session_started:
            if secondary_monitor_only:
                continue

            if command_master is None or not command_link_is_trusted_for_control():
                STATUS["link_state"] = "SECONDARY_UNAVAILABLE"
                if not security_block_logged:
                    log_event(
                        "ERROR",
                        "SECONDARY_CONTROL_UNAVAILABLE",
                        f"reason={command_control_block_reason()}",
                    )
                    log_event(
                        "ERROR",
                        "SECURITY_POLICY_BLOCKED_COMMAND",
                        f"reason={command_control_block_reason()}",
                    )
                    security_block_logged = True
                continue

            security_block_logged = False
            secondary_session_started = True
            session_state = secondary_command_loop(
                command_master,
                target_system,
                target_component,
                latest_monitor_global_position,
                latest_command_global_position,
                hold_active,
                hold_target,
            )
            hold_active = session_state["hold_active"]
            hold_target = session_state["hold_target"]
            if hold_active and hold_target is not None:
                last_hold_send_time = monotonic_time()

            secondary_session_started = False
            if session_state["session_result"] == "monitor_only":
                secondary_monitor_only = True
                continue

            if session_state["session_result"] == "secondary_lost":
                close_master_safely(command_master)
                command_master = None
                reset_command_link_status()
                secondary_monitor_only = False
                continue


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
        close_master_safely(monitor_master)
        close_master_safely(command_master)
        close_log_file()


if __name__ == "__main__":
    main()
