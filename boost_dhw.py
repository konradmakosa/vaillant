#!/usr/bin/env python3
"""
Trigger domestic hot water boost via myVAILLANT API.
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


async def boost():
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
                logger.info("DHW boost already active — skipping.")
                return True

            logger.info("Starting DHW boost...")
            result = await api.boost_domestic_hot_water(dhw)
            logger.info(f"DHW boost activated. Status: {result.current_special_function}")
            return True

    return False


def main():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            success = asyncio.run(boost())
            if success:
                logger.info("DHW boost completed successfully.")
                sys.exit(0)
            else:
                logger.error("DHW boost failed.")
                sys.exit(1)
        except Exception as e:
            if ('403' in str(e) or '401' in str(e)) and attempt < max_retries - 1:
                wait = 60 * (attempt + 1)
                logger.warning(f"API error, retrying in {wait}s (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(wait)
            else:
                logger.error(f"Failed: {e}")
                sys.exit(1)


if __name__ == "__main__":
    main()
