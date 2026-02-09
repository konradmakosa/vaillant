#!/usr/bin/env python3
"""
Vaillant boiler water pressure monitor.
Checks water pressure via myVAILLANT API and exits with code 1 if pressure is too low.
Designed to run in GitHub Actions with email notifications.
"""
import asyncio
import json
import os
import sys
import logging
from datetime import datetime

from myPyllant.api import MyPyllantAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Pressure thresholds (bar)
PRESSURE_WARNING = float(os.environ.get("PRESSURE_WARNING", "1.0"))
PRESSURE_CRITICAL = float(os.environ.get("PRESSURE_CRITICAL", "0.8"))

# Credentials from environment
USERNAME = os.environ["VAILLANT_USERNAME"]
PASSWORD = os.environ["VAILLANT_PASSWORD"]
BRAND = os.environ.get("VAILLANT_BRAND", "vaillant")
COUNTRY = os.environ.get("VAILLANT_COUNTRY", "poland")


async def check_pressure():
    """
    Connect to myVaillant API, read water pressure, and return status report.
    Returns (pressure_value, status, full_report_text)
    """
    async with MyPyllantAPI(USERNAME, PASSWORD, BRAND, COUNTRY) as api:
        async for system in api.get_systems(
            include_connection_status=True,
            include_rts=True,
            include_mpc=True,
        ):
            pressure = system.water_pressure
            outdoor_temp = system.outdoor_temperature
            flow_temp = system.system_flow_temperature
            connected = system.connected
            system_name = system.system_name
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Gather zone info
            zones_info = []
            for zone in system.zones:
                zones_info.append(
                    f"  {zone.name}: {zone.current_room_temperature}°C "
                    f"(target: {zone.desired_room_temperature_setpoint}°C, "
                    f"heating: {zone.heating_state})"
                )

            # Gather DHW info
            dhw_info = []
            for dhw in system.domestic_hot_water:
                dhw_info.append(
                    f"  DHW: {dhw.current_dhw_temperature}°C "
                    f"(target: {dhw.tapping_setpoint}°C, mode: {dhw.operation_mode_dhw})"
                )

            # Determine status
            if pressure is None:
                status = "UNKNOWN"
                status_line = "⚠️ WATER PRESSURE: UNKNOWN (could not read)"
            elif pressure < PRESSURE_CRITICAL:
                status = "CRITICAL"
                status_line = f"🔴 WATER PRESSURE CRITICAL: {pressure:.2f} bar (threshold: {PRESSURE_CRITICAL} bar)"
            elif pressure < PRESSURE_WARNING:
                status = "WARNING"
                status_line = f"🟡 WATER PRESSURE LOW: {pressure:.2f} bar (threshold: {PRESSURE_WARNING} bar)"
            else:
                status = "OK"
                status_line = f"🟢 Water pressure OK: {pressure:.2f} bar"

            report = f"""
{'='*60}
VAILLANT BOILER STATUS REPORT
{'='*60}
Time:               {now}
System:             {system_name}
Connected:          {connected}

{status_line}

--- System Readings ---
Water Pressure:     {pressure} bar
Outdoor Temp:       {outdoor_temp}°C
Flow Temperature:   {flow_temp}°C

--- Zones ---
{chr(10).join(zones_info) if zones_info else '  (no zones)'}

--- Hot Water ---
{chr(10).join(dhw_info) if dhw_info else '  (no DHW)'}
{'='*60}
"""
            return pressure, status, report.strip()

    return None, "ERROR", "Could not retrieve any system data."


def write_github_output(pressure, status, report):
    """Write results to GitHub Actions output and step summary."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"pressure={pressure}\n")
            f.write(f"status={status}\n")

    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        with open(github_summary, "a") as f:
            f.write(f"## Vaillant Boiler Pressure Check\n\n")
            f.write(f"```\n{report}\n```\n")


def main():
    pressure, status, report = asyncio.run(check_pressure())

    print(report)
    write_github_output(pressure, status, report)

    if status == "CRITICAL":
        logger.critical("Water pressure is critically low! Immediate action required.")
        sys.exit(1)
    elif status == "WARNING":
        logger.warning("Water pressure is below recommended level.")
        sys.exit(1)
    elif status == "UNKNOWN":
        logger.warning("Could not read water pressure.")
        sys.exit(1)
    else:
        logger.info("Water pressure is normal.")
        sys.exit(0)


if __name__ == "__main__":
    main()
