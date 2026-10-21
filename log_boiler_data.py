#!/usr/bin/env python3
"""
Vaillant boiler data logger + pressure monitor.
Single API call: logs data to CSV, checks pressure, sends Pushover alert if needed.
Designed to run every ~16 minutes via GitHub Actions.
"""
import asyncio
import csv
import json
import os
import sys
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from myPyllant.api import MyPyllantAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USERNAME = os.environ["VAILLANT_USERNAME"]
PASSWORD = os.environ["VAILLANT_PASSWORD"]
BRAND = os.environ.get("VAILLANT_BRAND", "vaillant")
COUNTRY = os.environ.get("VAILLANT_COUNTRY", "poland")

STALE_FAIL_SECONDS = int(os.environ.get("STALE_FAIL_SECONDS", "7200"))  # fail (→ e-mail) only after 2 h without data
WORKER_URL = os.environ.get("WORKER_URL", "https://vaillant-trigger.konrad-makosa.workers.dev")

PRESSURE_WARNING = float(os.environ.get("PRESSURE_WARNING", "1.0"))
PRESSURE_CRITICAL = float(os.environ.get("PRESSURE_CRITICAL", "0.8"))

MIN_INTERVAL_SECONDS = int(os.environ.get("MIN_INTERVAL_SECONDS", "900"))  # 15 min

WARSAW_TZ = ZoneInfo("Europe/Warsaw")
STATUS_SEVERITY = {"OK": 0, "UNKNOWN": 1, "WARNING": 2, "CRITICAL": 3}
CSV_DIR = Path(os.environ.get("CSV_DIR", "data"))
CSV_HEADERS = [
    "timestamp",
    "water_pressure_bar",
    "outdoor_temp_c",
    "circuit_flow_temp_c",
    "energy_manager_state",
    "circuit_state",
    "connected",
    "zone_name",
    "zone_current_temp_c",
    "zone_target_temp_c",
    "zone_humidity_pct",
    "zone_heating_state",
    "dhw_current_temp_c",
    "dhw_target_temp_c",
    "dhw_operation_mode",
    "dhw_current_special_function",
]


async def read_boiler_data():
    """Read current boiler parameters. Returns (rows, system_info)."""
    rows = []
    info = {}
    async with MyPyllantAPI(USERNAME, PASSWORD, BRAND, COUNTRY) as api:
        async for system in api.get_systems(
            include_connection_status=True,
        ):
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            pressure = system.water_pressure
            outdoor_temp = system.outdoor_temperature
            connected = system.connected
            energy_state = system.energy_manager_state

            circuits = system.circuits if system.circuits else []
            circuit_flow = circuits[0].current_circuit_flow_temperature if circuits else None
            circuit_state = circuits[0].circuit_state if circuits else None

            zones = system.zones if system.zones else [None]
            dhw_list = system.domestic_hot_water if system.domestic_hot_water else [None]

            for zone in zones:
                for dhw in dhw_list:
                    row = {
                        "timestamp": now,
                        "water_pressure_bar": pressure,
                        "outdoor_temp_c": outdoor_temp,
                        "circuit_flow_temp_c": circuit_flow,
                        "energy_manager_state": energy_state,
                        "circuit_state": circuit_state,
                        "connected": connected,
                        "zone_name": zone.name if zone else None,
                        "zone_current_temp_c": zone.current_room_temperature if zone else None,
                        "zone_target_temp_c": zone.desired_room_temperature_setpoint if zone else None,
                        "zone_humidity_pct": zone.current_room_humidity if zone else None,
                        "zone_heating_state": zone.heating_state if zone else None,
                        "dhw_current_temp_c": dhw.current_dhw_temperature if dhw else None,
                        "dhw_target_temp_c": dhw.tapping_setpoint if dhw else None,
                        "dhw_operation_mode": dhw.operation_mode_dhw if dhw else None,
                        "dhw_current_special_function": dhw.current_special_function if dhw else None,
                    }
                    rows.append(row)

            info = {
                "pressure": pressure,
                "outdoor_temp": outdoor_temp,
                "circuit_flow": circuit_flow,
                "connected": connected,
                "system_name": system.system_name,
                "zones": system.zones,
                "dhw": system.domestic_hot_water,
            }
    return rows, info


def is_auth_blocked(e):
    """True if the exception looks like a Vaillant WAF/auth block (403/LoginEndpointInvalid)."""
    if type(e).__name__ == "LoginEndpointInvalid":
        return True
    msg = f"{e} {getattr(e, '__cause__', '')}"
    return "403" in msg or "401" in msg


def read_via_worker():
    """Fallback read via the Cloudflare Worker (different egress IP than GitHub Actions).
    The worker does login + ALTCHA itself. Returns (rows, info) like read_boiler_data()."""
    req = urllib.request.Request(
        f"{WORKER_URL}/data",
        data=b'{"commit": false}',
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.load(resp)
    if payload.get("status") != "ok":
        raise RuntimeError(f"Worker /data failed: {payload}")
    data = payload["data"]
    data["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    info = {
        "pressure": data.get("water_pressure_bar"),
        "outdoor_temp": data.get("outdoor_temp_c"),
        "circuit_flow": data.get("circuit_flow_temp_c"),
        "connected": data.get("connected"),
        "system_name": "(worker fallback)",
        "zones": [],
        "dhw": [],
    }
    return [data], info


def last_csv_line():
    """Return the last data line of the current (or previous) month's CSV, or None."""
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    for _ in range(2):
        csv_path = CSV_DIR / f"boiler_{year:04d}-{month:02d}.csv"
        if csv_path.exists():
            try:
                with open(csv_path, "r") as f:
                    lines = [l for l in f.read().splitlines() if l.strip()]
                if len(lines) >= 2:
                    return lines[-1]
            except Exception as e:
                logger.warning(f"Could not read {csv_path}: {e}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return None


def previous_reading():
    """Return (timestamp_utc, pressure) of the last logged reading, or (None, None)."""
    line = last_csv_line()
    if not line:
        return None, None
    try:
        cols = line.split(",")
        ts = datetime.strptime(cols[0].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        pressure = float(cols[1]) if len(cols) > 1 and cols[1].strip() else None
        return ts, pressure
    except Exception as e:
        logger.warning(f"Could not parse last CSV row: {e}")
        return None, None


def too_soon():
    """Return True if last CSV entry is less than MIN_INTERVAL_SECONDS ago."""
    line = last_csv_line()
    if not line:
        return False
    try:
        last_ts = datetime.strptime(line.split(",")[0].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
        logger.info(f"Last reading {elapsed:.0f}s ago (min interval: {MIN_INTERVAL_SECONDS}s)")
        return elapsed < MIN_INTERVAL_SECONDS
    except Exception as e:
        logger.warning(f"Could not check last timestamp: {e}")
        return False


def append_to_csv(rows):
    """Append rows to monthly CSV file (one file per month)."""
    CSV_DIR.mkdir(exist_ok=True)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    csv_path = CSV_DIR / f"boiler_{month}.csv"

    file_exists = csv_path.exists()

    # Migrate header if new columns were added
    if file_exists:
        with open(csv_path, "r") as f:
            first_line = f.readline().strip()
        existing_headers = first_line.split(",")
        if len(existing_headers) < len(CSV_HEADERS):
            logger.info(f"Migrating CSV header: {len(existing_headers)} → {len(CSV_HEADERS)} columns")
            with open(csv_path, "r") as f:
                all_lines = f.readlines()
            all_lines[0] = ",".join(CSV_HEADERS) + "\n"
            with open(csv_path, "w", newline="") as f:
                f.writelines(all_lines)

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info(f"Logged {len(rows)} row(s) to {csv_path}")
    return csv_path


def status_for(pressure):
    """Return pressure status: UNKNOWN / CRITICAL / WARNING / OK."""
    if pressure is None:
        return "UNKNOWN"
    if pressure < PRESSURE_CRITICAL:
        return "CRITICAL"
    if pressure < PRESSURE_WARNING:
        return "WARNING"
    return "OK"


def should_alert(status, prev_ts, prev_pressure, now=None):
    """Alert if not OK and (no previous reading, severity increased, or new Warsaw day)."""
    if status == "OK":
        return False
    if prev_ts is None:
        return True
    if STATUS_SEVERITY[status] > STATUS_SEVERITY[status_for(prev_pressure)]:
        return True
    now = now or datetime.now(timezone.utc)
    return prev_ts.astimezone(WARSAW_TZ).date() != now.astimezone(WARSAW_TZ).date()


def check_pressure(info):
    """Check pressure and return (status, report)."""
    pressure = info.get("pressure")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = status_for(pressure)

    if status == "UNKNOWN":
        status_line = "CISNIENIE WODY: nie mozna odczytac"
    elif status == "CRITICAL":
        status_line = f"CISNIENIE WODY KRYTYCZNE: {pressure:.2f} bar"
    elif status == "WARNING":
        status_line = f"NISKIE CISNIENIE WODY: {pressure:.2f} bar"
    else:
        status_line = f"Cisnienie OK: {pressure:.2f} bar"

    report = (
        f"{status_line}\n"
        f"Temp. zewn.: {info.get('outdoor_temp')}°C\n"
        f"Temp. przeplywu: {info.get('circuit_flow')}°C\n"
    )
    for zone in (info.get("zones") or []):
        report += (
            f"{zone.name}: {zone.current_room_temperature}°C "
            f"(cel: {zone.desired_room_temperature_setpoint}°C)\n"
        )
    for dhw in (info.get("dhw") or []):
        report += (
            f"CWU: {dhw.current_dhw_temperature}°C "
            f"(cel: {dhw.tapping_setpoint}°C)\n"
        )
    connected = info.get("connected")
    system_name = info.get("system_name", "")
    report += f"{now} | {system_name} | {'online' if connected else 'OFFLINE'}"

    return status, report


def send_pushover_alert(report, status):
    """Send push notification via Pushover API."""
    token = os.environ.get("PUSHOVER_APP_TOKEN")
    users = os.environ.get("PUSHOVER_USER_KEY", "")

    if not all([token, users]):
        logger.warning("Pushover not configured — skipping push notification.")
        return

    priority = 1 if status == "CRITICAL" else 0
    title = "Vaillant: " + ("KRYTYCZNE!" if status == "CRITICAL" else "Niskie cisnienie")

    for user_key in users.split(","):
        user_key = user_key.strip()
        if not user_key:
            continue
        data = urllib.parse.urlencode({
            "token": token,
            "user": user_key,
            "title": title,
            "message": report[:1024],
            "priority": priority,
            "sound": "siren" if status == "CRITICAL" else "pushover",
            "url": "https://konradmakosa.github.io/vaillant/",
            "url_title": "Wykres diagnostyczny",
        }).encode()

        try:
            req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
            with urllib.request.urlopen(req) as resp:
                logger.info(f"Pushover sent to {user_key[:8]}...: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send Pushover to {user_key[:8]}...: {e}")


def write_github_summary(status, report):
    """Write results to GitHub Actions step summary."""
    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        with open(github_summary, "a") as f:
            f.write(f"## Vaillant Boiler — {status}\n\n```\n{report}\n```\n")


def main():
    if too_soon():
        logger.info("Skipping — too soon since last reading.")
        return

    def fail_soft(msg):
        # a single missed reading is not worth a failure e-mail; fail the run only
        # when the data gap gets long (then GitHub's failure e-mail is meaningful)
        prev_ts, _ = previous_reading()
        gap = (datetime.now(timezone.utc) - prev_ts).total_seconds() if prev_ts else None
        if gap is not None and gap < STALE_FAIL_SECONDS:
            logger.warning(f"{msg} — skipping this reading (last reading {gap / 60:.0f} min ago)")
            sys.exit(0)
        logger.error(f"{msg} — no reading for {'?' if gap is None else f'{gap / 3600:.1f} h'}")
        sys.exit(1)

    rows, info = [], {}
    try:
        rows, info = asyncio.run(read_boiler_data())
    except Exception as e:
        if "Quota" in f"{e} {e.__cause__}":
            # per-account API quota — the worker uses the same account, fallback would fail too
            fail_soft(f"Vaillant API quota exceeded ({e})")
        if is_auth_blocked(e):
            # WAF/auth block on this IP — retrying won't help; read via the worker
            logger.warning(f"Vaillant auth blocked ({type(e).__name__}: {e}) — falling back to worker")
            try:
                rows, info = read_via_worker()
                logger.info("Reading obtained via Cloudflare Worker fallback")
            except Exception as e2:
                fail_soft(f"Worker fallback failed: {e2}")
        else:
            import traceback
            logger.error(f"Failed to read boiler data: {e}\n{traceback.format_exc()}")
            sys.exit(1)

    if not rows:
        logger.error("No data retrieved from boiler.")
        sys.exit(1)

    # 1. Log to CSV (grab previous reading first for alert de-duplication)
    prev_ts, prev_pressure = previous_reading()
    csv_path = append_to_csv(rows)

    for row in rows:
        logger.info(
            f"P={row['water_pressure_bar']} bar | "
            f"Out={row['outdoor_temp_c']}°C | "
            f"Flow={row['circuit_flow_temp_c']}°C | "
            f"{row['zone_name']}={row['zone_current_temp_c']}°C | "
            f"DHW={row['dhw_current_temp_c']}°C"
        )

    # 2. Check pressure + alert
    status, report = check_pressure(info)
    print(report)
    write_github_summary(status, report)

    if status in ("CRITICAL", "WARNING", "UNKNOWN"):
        if should_alert(status, prev_ts, prev_pressure):
            send_pushover_alert(report, status)
            logger.warning(f"Pressure status: {status} — alert sent")
        else:
            logger.warning(f"Pressure {status} persists, alert already sent today")
    else:
        logger.info(f"Pressure status: {status}")


if __name__ == "__main__":
    main()
