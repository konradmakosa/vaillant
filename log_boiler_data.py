#!/usr/bin/env python3
"""
Vaillant boiler data logger.
Reads boiler parameters and appends a row to CSV file.
Designed to run every 5 minutes via GitHub Actions.
"""
import asyncio
import csv
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from myPyllant.api import MyPyllantAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USERNAME = os.environ["VAILLANT_USERNAME"]
PASSWORD = os.environ["VAILLANT_PASSWORD"]
BRAND = os.environ.get("VAILLANT_BRAND", "vaillant")
COUNTRY = os.environ.get("VAILLANT_COUNTRY", "poland")

CSV_DIR = Path(os.environ.get("CSV_DIR", "data"))
CSV_HEADERS = [
    "timestamp",
    "water_pressure_bar",
    "outdoor_temp_c",
    "flow_temp_c",
    "connected",
    "zone_name",
    "zone_current_temp_c",
    "zone_target_temp_c",
    "zone_humidity_pct",
    "zone_heating_state",
    "dhw_current_temp_c",
    "dhw_target_temp_c",
    "dhw_operation_mode",
]


async def read_boiler_data():
    """Read current boiler parameters and return list of row dicts."""
    rows = []
    async with MyPyllantAPI(USERNAME, PASSWORD, BRAND, COUNTRY) as api:
        async for system in api.get_systems(
            include_connection_status=True,
            include_rts=True,
            include_mpc=True,
        ):
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            pressure = system.water_pressure
            outdoor_temp = system.outdoor_temperature
            flow_temp = system.system_flow_temperature
            connected = system.connected

            zones = system.zones if system.zones else [None]
            dhw_list = system.domestic_hot_water if system.domestic_hot_water else [None]

            for zone in zones:
                for dhw in dhw_list:
                    row = {
                        "timestamp": now,
                        "water_pressure_bar": pressure,
                        "outdoor_temp_c": outdoor_temp,
                        "flow_temp_c": flow_temp,
                        "connected": connected,
                        "zone_name": zone.name if zone else None,
                        "zone_current_temp_c": zone.current_room_temperature if zone else None,
                        "zone_target_temp_c": zone.desired_room_temperature_setpoint if zone else None,
                        "zone_humidity_pct": zone.current_room_humidity if zone else None,
                        "zone_heating_state": zone.heating_state if zone else None,
                        "dhw_current_temp_c": dhw.current_dhw_temperature if dhw else None,
                        "dhw_target_temp_c": dhw.tapping_setpoint if dhw else None,
                        "dhw_operation_mode": dhw.operation_mode_dhw if dhw else None,
                    }
                    rows.append(row)
    return rows


def append_to_csv(rows):
    """Append rows to monthly CSV file (one file per month)."""
    CSV_DIR.mkdir(exist_ok=True)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    csv_path = CSV_DIR / f"boiler_{month}.csv"

    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info(f"Logged {len(rows)} row(s) to {csv_path}")
    return csv_path


def main():
    rows = asyncio.run(read_boiler_data())
    if not rows:
        logger.error("No data retrieved from boiler.")
        sys.exit(1)

    csv_path = append_to_csv(rows)

    for row in rows:
        logger.info(
            f"P={row['water_pressure_bar']} bar | "
            f"Out={row['outdoor_temp_c']}°C | "
            f"Flow={row['flow_temp_c']}°C | "
            f"{row['zone_name']}={row['zone_current_temp_c']}°C | "
            f"DHW={row['dhw_current_temp_c']}°C"
        )


if __name__ == "__main__":
    main()
