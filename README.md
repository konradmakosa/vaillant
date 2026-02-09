# Vaillant Boiler Pressure Monitor

Automated water pressure monitoring for Vaillant boilers via **GitHub Actions**. Uses the [myPyllant](https://github.com/signalkraft/myPyllant) library to connect to the myVAILLANT API and sends email alerts when pressure drops below threshold.

## How It Works

1. GitHub Actions runs `monitor_pressure.py` **every 15 minutes**
2. Script logs into myVAILLANT API and reads `system.water_pressure`
3. If pressure < 1.0 bar (warning) or < 0.8 bar (critical) → sends email to `konrad@makosa.org`
4. Full status report (zones, DHW, temperatures) is available in the GitHub Actions run log

## Setup — GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:

| Secret Name | Value |
|---|---|
| `VAILLANT_USERNAME` | Your myVaillant email |
| `VAILLANT_PASSWORD` | Your myVaillant password |
| `SMTP_USERNAME` | Gmail address for sending alerts (e.g. your-alerts@gmail.com) |
| `SMTP_PASSWORD` | Gmail App Password (NOT your regular password — see below) |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (from console.twilio.com) |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `TWILIO_WHATSAPP_FROM` | Twilio sandbox number, e.g. `+14155238886` |
| `WHATSAPP_RECIPIENTS` | Comma-separated phone numbers, e.g. `+48123456789,+48987654321` |

### Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and "Other (Custom name)" → name it "Vaillant Monitor"
3. Copy the 16-character password → use it as `SMTP_PASSWORD`
4. Requires 2FA enabled on the Gmail account

### WhatsApp via Twilio (free trial)

1. Sign up at https://www.twilio.com/try-twilio (free $15 credit)
2. Go to **Messaging** → **Try it out** → **Send a WhatsApp message**
3. Twilio gives you a sandbox number and a join code (e.g. `join bright-fox`)
4. **Each family member** sends that join code to the sandbox number on WhatsApp — this subscribes them
5. Copy **Account SID**, **Auth Token**, and **sandbox number** from the Twilio console
6. Add them as GitHub Secrets (see table above)
7. Set `WHATSAPP_RECIPIENTS` to all family phone numbers (with country code), comma-separated

> **Tip:** You can use any SMTP server — just update `server_address` and `server_port` in `.github/workflows/pressure-monitor.yml`

## Pressure Thresholds

Configurable in the workflow file (`.github/workflows/pressure-monitor.yml`):

| Variable | Default | Description |
|---|---|---|
| `PRESSURE_WARNING` | 1.0 bar | Email alert sent |
| `PRESSURE_CRITICAL` | 0.8 bar | Email alert sent (urgent) |

Typical boiler operating range is **1.0 – 2.0 bar**.

## Files

- **`monitor_pressure.py`** — Main monitoring script (used by GitHub Actions)
- **`.github/workflows/pressure-monitor.yml`** — GitHub Actions workflow (cron every 15 min)
- **`test_boiler.py`** — Interactive script to explore all available boiler data
- **`export_data.py`** — Export system data to JSON

## Local Testing

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test the monitor locally
export VAILLANT_USERNAME="your@email.com"
export VAILLANT_PASSWORD="your-password"
export VAILLANT_COUNTRY="poland"
python monitor_pressure.py

# Explore all available data interactively
python test_boiler.py
```

## Manual Trigger

You can trigger the check manually from GitHub: **Actions** → **Vaillant Pressure Monitor** → **Run workflow**
