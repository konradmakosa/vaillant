#!/usr/bin/env python3
"""
Trigger domestic hot water boost via myVAILLANT API.
Starts boost, waits BOOST_DURATION minutes, then cancels.
Designed to run from GitHub Actions via repository_dispatch.
"""
import asyncio
import os
import sys
import logging
import time

from myPyllant.api import MyPyllantAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USERNAME = os.environ["VAILLANT_USERNAME"]
PASSWORD = os.environ["VAILLANT_PASSWORD"]
BRAND = os.environ.get("VAILLANT_BRAND", "vaillant")
COUNTRY = os.environ.get("VAILLANT_COUNTRY", "poland")
BOOST_DURATION = int(os.environ.get("BOOST_DURATION_MIN", "30"))


async def start_boost():
    async with MyPyllantAPI(USERNAME, PASSWORD, BRAND, COUNTRY) as api:
        async for system in api.get_systems():
            if not system.domestic_hot_water:
                logger.error("No domestic hot water device found.")
                return False

            dhw = system.domestic_hot_water[0]
            logger.info(f"DHW current temp: {dhw.current_dhw_temperature}°C, "
                        f"target: {dhw.tapping_setpoint}°C, "
                        f"boosting: {dhw.is_cylinder_boosting}")

            if dhw.is_cylinder_boosting:
                logger.info("DHW boost already active — skipping start.")
                return True

            logger.info("Starting DHW boost...")
            await api.boost_domestic_hot_water(dhw)
            logger.info("DHW boost activated.")
            return True

    return False


async def cancel_boost():
    async with MyPyllantAPI(USERNAME, PASSWORD, BRAND, COUNTRY) as api:
        async for system in api.get_systems():
            if not system.domestic_hot_water:
                logger.error("No domestic hot water device found.")
                return False

            dhw = system.domestic_hot_water[0]
            logger.info(f"Cancelling DHW boost (current temp: {dhw.current_dhw_temperature}°C)...")
            await api.cancel_hot_water_boost(dhw)
            logger.info("DHW boost cancelled.")
            return True

    return False


def run_with_retry(coro_fn, label):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            success = asyncio.run(coro_fn())
            if success:
                return True
            else:
                logger.error(f"{label} failed.")
                return False
        except Exception as e:
            if ('403' in str(e) or '401' in str(e)) and attempt < max_retries - 1:
                wait = 60 * (attempt + 1)
                logger.warning(f"{label} API error, retrying in {wait}s "
                               f"(attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(wait)
            else:
                logger.error(f"{label} failed: {e}")
                return False
    return False


def main():
    if not run_with_retry(start_boost, "Boost start"):
        sys.exit(1)

    logger.info(f"Waiting {BOOST_DURATION} minutes before cancelling boost...")
    time.sleep(BOOST_DURATION * 60)

    if not run_with_retry(cancel_boost, "Boost cancel"):
        sys.exit(1)

    logger.info("DHW boost cycle complete.")


if __name__ == "__main__":
    main()
