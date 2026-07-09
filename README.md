# Weather Email MCP Server

Daily weather digest for **Delhi**, **Mumbai**, and **Nagpur** using [Open-Meteo](https://open-meteo.com/), delivered to **amol.eng@gmail.com** via **SendGrid**.

Includes:
- **MCP server** (`server.py`) — on-demand weather tools in Cursor
- **Scheduler script** (`send_daily_digest.py`) — for Windows Task Scheduler or cloud cron

**Team documentation:** See [DESIGN.md](DESIGN.md) for architecture, classes, APIs, and data flow.

## Setup

### 1. Install dependencies

```powershell
cd C:\SB\MCP
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and choose one email provider.

**Option A — Gmail SMTP (recommended for amol.eng@gmail.com):**

1. Enable 2-Step Verification on your Google account
2. Create an App Password at [Google App Passwords](https://myaccount.google.com/apppasswords)
3. Set in `.env`:

```env
EMAIL_PROVIDER=gmail
SMTP_USER=amol.eng@gmail.com
SMTP_PASS=your_16_char_app_password
FROM_EMAIL=amol.eng@gmail.com
TO_EMAIL=amol.eng@gmail.com
```

**Option B — SendGrid:**

```env
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG.your_api_key_here
FROM_EMAIL=verified-sender@yourdomain.com
TO_EMAIL=amol.eng@gmail.com
```

SendGrid requires a verified sender at [SendGrid Sender Authentication](https://app.sendgrid.com/settings/sender_auth).

### 3. Register MCP in Cursor

Already configured in `~\.cursor\mcp.json`:

```json
"weather-email": {
  "command": "C:\\SB\\MCP\\.venv\\Scripts\\python.exe",
  "args": ["C:\\SB\\MCP\\server.py"]
}
```

Restart Cursor or reload MCP servers to pick up the new server.

## MCP tools

| Tool | Description |
|------|-------------|
| `get_weather_report` | Fetch formatted weather for all 3 cities (no email) |
| `send_weather_email_now` | Fetch and email the digest immediately |
| `get_city_weather` | Fetch weather for a single city |

## Daily email (local PC)

### Manual test

```powershell
cd C:\SB\MCP
.venv\Scripts\python.exe send_daily_digest.py
```

Check `logs\digest.log` for run history.

### Smoke tests (no email unless configured)

```powershell
.venv\Scripts\python.exe examples\run_tests.py
```

To send a live test email during smoke tests:

```env
SEND_LIVE_EMAIL=1
```

### Windows Task Scheduler (7:00 AM IST daily)

**Option A — PowerShell script (recommended)**

Run once as Administrator or as your user:

```powershell
cd C:\SB\MCP
powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1
```

**Option B — Manual setup**

1. Open **Task Scheduler** → **Create Task**
2. **General:** Name `WeatherEmailDigest`, run whether user is logged on or not
3. **Triggers:** Daily at **7:00 AM**, timezone **(UTC+05:30) Chennai, Kolkata, Mumbai, New Delhi**
4. **Actions:** Start a program
   - Program: `C:\SB\MCP\.venv\Scripts\python.exe`
   - Arguments: `C:\SB\MCP\send_daily_digest.py`
   - Start in: `C:\SB\MCP`
5. **Conditions:** Uncheck "Start only if on AC power" if on laptop; optionally enable "Wake the computer to run this task"
6. **Settings:** Allow task to run on demand; if missed, run as soon as possible

**Note:** The PC must be on and awake at the scheduled time. For reliable delivery when the PC is off, use cloud cron (below).

## Cloud migration (Phase 2)

The same `send_daily_digest.py` runs in GitHub Actions. See [`.github/workflows/daily-weather.yml`](.github/workflows/daily-weather.yml).

### GitHub secrets required

| Secret | Value |
|--------|-------|
| `SENDGRID_API_KEY` | Your SendGrid API key |
| `FROM_EMAIL` | Verified SendGrid sender |
| `TO_EMAIL` | `amol.eng@gmail.com` (optional; defaults in code) |

Schedule: **7:00 AM IST** (`30 1 * * *` UTC).

## Project layout

```
server.py              # FastMCP tools
weather.py             # Open-Meteo client
formatter.py           # Text/HTML/Markdown formatting
emailer.py             # SendGrid delivery
send_daily_digest.py   # Scheduler entry point
config.py              # Cities and env loading
examples/run_tests.py  # Smoke tests
scripts/register_scheduled_task.ps1
logs/digest.log        # Runtime log (created on first run)
```

## Attribution

Open-Meteo data is used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The email footer includes required attribution.
