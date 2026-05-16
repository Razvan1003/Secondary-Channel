# Test Plan

## Baseline Connectivity

1. Start ArduPilot SITL.
2. Start Mission Planner and connect on UDP `14550`.
3. Start the secondary channel.
4. Confirm heartbeat and telemetry are observed.

## Failover Test

1. Arm the simulated vehicle.
2. Take off to a safe simulated altitude.
3. Block the monitor endpoint on UDP `14560`.
4. Confirm `LINK_TIMEOUT` and secondary-channel activation are logged.
5. Trigger `RTL`, `LAND` or `HOLD`.
6. Verify command acknowledgement and observed vehicle mode.

## Restore Test

1. Remove the firewall rule that blocks UDP `14560`.
2. Confirm telemetry resumes.
3. Check that logs show the restored state.

## Evidence To Keep

- terminal log from `secondary_channel_v4.py`
- Mission Planner screenshot before and after failover
- selected emergency action and command acknowledgement
- observed mode, arm state and altitude
