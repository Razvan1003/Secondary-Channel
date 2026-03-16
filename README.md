# Secondary-Channel

Version 1 of a secondary emergency channel for a MAVLink-based drone.

## What V1 does

- Connects to a MAVLink stream with `pymavlink`
- Monitors `HEARTBEAT` messages
- Detects heartbeat loss after 5 seconds
- Prints clear console alerts
- Sends one RTL command for each detected loss event

## File

- `secondary_channel_v1.py`

## Requirements

- Python 3
- `pymavlink`

Install dependency:

```bash
pip install pymavlink
```

## Run

```bash
python secondary_channel_v1.py
```

## Notes

- This V1 script was tested in simulation with ArduPilot SITL.
- The default connection is configured for a setup where MAVProxy runs in WSL
  and the Python script runs on Windows.
