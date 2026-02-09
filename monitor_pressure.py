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
from twilio.rest import Client as TwilioClient

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

            # Determine status
            if pressure is None:
                status = "UNKNOWN"
                status_line = "CISNIENIE WODY: nie mozna odczytac"
            elif pressure < PRESSURE_CRITICAL:
                status = "CRITICAL"
                status_line = f"CISNIENIE WODY KRYTYCZNE: {pressure:.2f} bar"
            elif pressure < PRESSURE_WARNING:
                status = "WARNING"
                status_line = f"NISKIE CISNIENIE WODY: {pressure:.2f} bar"
            else:
                status = "OK"
                status_line = f"Cisnienie OK: {pressure:.2f} bar"

            report = (
                f"{status_line}\n"
                f"Temp. zewn.: {outdoor_temp}°C\n"
                f"Temp. przeplywu: {flow_temp}°C\n"
            )
            for zone in system.zones:
                report += (
                    f"{zone.name}: {zone.current_room_temperature}°C "
                    f"(cel: {zone.desired_room_temperature_setpoint}°C)\n"
                )
            for dhw in system.domestic_hot_water:
                report += (
                    f"CWU: {dhw.current_dhw_temperature}°C "
                    f"(cel: {dhw.tapping_setpoint}°C)\n"
                )
            report += f"{now} | {system_name} | {'online' if connected else 'OFFLINE'}"

            return pressure, status, report

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


def send_whatsapp_alerts(report):
    """
    Send WhatsApp messages via Twilio to all configured family numbers.
    WHATSAPP_RECIPIENTS should be comma-separated phone numbers, e.g. "+48123456789,+48987654321"
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM", "+14155238886")  # Twilio sandbox default
    recipients = os.environ.get("WHATSAPP_RECIPIENTS", "")

    if not all([account_sid, auth_token, recipients]):
        logger.warning("Twilio/WhatsApp not configured — skipping WhatsApp alerts.")
        return

    client = TwilioClient(account_sid, auth_token)
    short_msg = report[:1600]  # WhatsApp message limit

    for number in recipients.split(","):
        number = number.strip()
        if not number:
            continue
        try:
            message = client.messages.create(
                body=short_msg,
                from_=f"whatsapp:{from_number}",
                to=f"whatsapp:{number}",
            )
            logger.info(f"WhatsApp sent to {number}: SID {message.sid}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp to {number}: {e}")


def main():
    pressure, status, report = asyncio.run(check_pressure())

    print(report)
    write_github_output(pressure, status, report)

    if status in ("CRITICAL", "WARNING", "UNKNOWN"):
        send_whatsapp_alerts(report)

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
