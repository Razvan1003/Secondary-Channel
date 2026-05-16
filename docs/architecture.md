# Architecture Notes

This project validates a simulated secondary safety channel for UAV emergency communication.

## Lab Components

- ArduPilot SITL runs the simulated vehicle.
- MAVProxy exports MAVLink traffic to Mission Planner and to the secondary monitor endpoint.
- Mission Planner is used for operational visual validation.
- `secondary_channel_v4.py` monitors link health and sends emergency actions through a separate command path.
- The PySide6 desktop app starts the lab processes and exposes failover/restore actions.

## Data Paths

```text
SITL -> UDP 14550 -> Mission Planner
SITL -> UDP 14560 -> Secondary monitor
Secondary channel -> TCP 5782 -> command path
```

## Safety Boundary

The repository is a simulation and validation project. It does not integrate real RF hardware and must not be treated as certified flight software.
