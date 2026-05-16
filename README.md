# UAV Emergency Communication - Secondary Channel

Python-based secondary safety channel for UAV emergency communication experiments using MAVLink and ArduPilot SITL.

The project validates how a separate software channel can monitor a UAV link, detect loss of communication and trigger emergency actions in simulation.

## What It Does

- Monitors MAVLink heartbeat and telemetry over a dedicated UDP endpoint
- Detects primary-link loss using timeout-based monitoring
- Sends emergency actions through a separate command path
- Supports RTL, LAND, GUIDED HOLD, ARM/DISARM, TAKEOFF and altitude-change workflows
- Logs operational events, command acknowledgements and observed vehicle state
- Includes optional MAVLink 2 signing configuration for security-oriented testing
- Provides a PySide6 desktop orchestrator for Windows-based lab runs

## Architecture

```text
ArduPilot SITL / MAVProxy
        |
        | UDP 14550
        v
Mission Planner

ArduPilot SITL / MAVProxy
        |
        | UDP 14560
        v
Secondary monitor path

Secondary channel script
        |
        | TCP command path
        v
ArduPilot command interface
```

The desktop application starts and supervises the main lab components:

- ArduPilot SITL through WSL
- `secondary_channel_v4.py` on Windows
- PowerShell failover and restore commands
- optional Mission Planner launch
- live stdout/stderr panels and parsed status values

## Repository Structure

```text
app.py                    # PySide6 application entry point
main_window.py            # desktop UI
process_manager.py        # QProcess orchestration and log parsing
commands.py               # command builders for SITL, failover and secondary script
config.py                 # environment-based configuration
secondary_channel_v4.py   # current main secondary-channel implementation
secondary_channel_v*.py   # incremental experiment versions
widgets/                  # UI panels
docs/                     # architecture and validation notes
```

## Requirements

- Windows
- Python 3
- WSL with ArduPilot SITL configured
- Mission Planner, optional but recommended for visual validation
- Python packages:
  - `pymavlink`
  - `PySide6`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

Start the desktop orchestrator:

```bash
py app.py
```

Run the current secondary-channel script directly:

```bash
py secondary_channel_v4.py
```

Example SITL command:

```bash
sim_vehicle.py -w -v ArduCopter -f quad --map --console --out=<WINDOWS_HOST_IP>:14550 --out=<WINDOWS_HOST_IP>:14560 -A "--serial2=tcp:5782"
```

## Configuration

The application reads configuration from environment variables through `config.py`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `ARDUPILOT_WSL_PATH` | ArduPilot path inside WSL | `~/ardupilot/ArduCopter` |
| `SECONDARY_WINDOWS_HOST_IP` | Windows host IP used by SITL outputs | `172.30.208.1` |
| `SECONDARY_MONITOR_UDP_PORT` | UDP port for monitor link | `14560` |
| `MISSION_PLANNER_UDP_PORT` | UDP port for Mission Planner | `14550` |
| `SECONDARY_COMMAND_HOST` | host for command path | `127.0.0.1` |
| `SECONDARY_COMMAND_TCP_PORT` | TCP command port | `5782` |
| `SECONDARY_CHANNEL_SIGNING_ENABLED` | enables MAVLink signing config | `false` in script |
| `SECONDARY_CHANNEL_COMMAND_UNSIGNED_POLICY` | command unsigned-message policy | `reject` |

Do not commit real signing keys or operational secrets.

## Test Scenario

1. Start ArduPilot SITL.
2. Connect Mission Planner to UDP `14550`.
3. Start the secondary-channel script or desktop orchestrator.
4. Arm the vehicle in simulation and take off to a safe test altitude.
5. Simulate monitor-link failure by blocking UDP `14560`.
6. Confirm that the secondary channel detects link loss.
7. Select or trigger an emergency action: RTL, LAND or HOLD.
8. Validate the result through command acknowledgements, logs and Mission Planner state.

## Current Limitations

- Simulation-only project; no real RF or LoRa hardware is integrated
- Not flight-certified and not intended for real aircraft operation
- Failover is validated in ArduPilot SITL, not in a physical UAV environment
- Some status parsing is based on process output and should be replaced with structured telemetry for a production-grade tool

## Roadmap

- Add a clean architecture diagram under `docs/`
- Add repeatable test logs and screenshots
- Move older experiment versions into a dedicated `experiments/` directory
- Add basic lint/compile checks
- Document MAVLink signing test cases more explicitly
