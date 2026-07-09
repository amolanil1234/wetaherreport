"""
MCP server for daily weather digest (Delhi, Nagpur).
Run: python server.py  (stdio transport for Cursor)
"""

# what does this line do?
# it tells the Python interpreter to use the future features of the language
# it is a good practice to use this line at the beginning of the file
# it is not necessary to use this line, but it is a good practice
# it is used to make the code compatible with future versions of the language
# it is used to make the code more readable
# it is used to make the code more maintainable
# it is used to make the code more scalable
# it is used to make the code more efficient
# it is used to make the code more secure
# it is used to make the code more reliable
from __future__ import annotations

# what does traceback do?
# it is used to print the traceback of the error
#give exmaple of traceback in this code
# example of traceback in this code is:
# example of traceback in this code is:
# Traceback (most recent call last):
#   File "server.py", line 23, in <module>
#     print(power)
# NameError: name 'power' is not defined
#without this line, the error will not be printed
# it will be printed as:
# NameError: name 'power' is not defined
# without this line, the error will not be printed
import traceback

from mcp.server.fastmcp import FastMCP

from config import DEFAULT_CITIES, CityConfig, get_digest_timezone
from emailer import send_weather_email
from formatter import format_report_markdown
from quotes import fetch_digest_inspiration
from weather import build_weather_report, fetch_city_weather

mcp = FastMCP("Weather Email")


@mcp.tool()
def get_weather_report() -> str:
    """
    Fetch and return a formatted weather report for Delhi and Nagpur.
    Does not send email.
    """
    try:
        report = build_weather_report(DEFAULT_CITIES, get_digest_timezone())
        return format_report_markdown(report)
    except Exception as exc:
        return (
            "# Weather Report — FAILED\n\n"
            f"Unexpected server error: {exc}\n\n"
            f"```\n{traceback.format_exc()}\n```"
        )


@mcp.tool()
def send_weather_email_now() -> str:
    """
    Fetch weather for Delhi and Nagpur and send the digest email immediately.
    Requires SMTP/SendGrid configured in .env.
    """
    try:
        report = build_weather_report(DEFAULT_CITIES, get_digest_timezone())
        if report.all_failed:
            return (
                "# Weather Digest — FAILED\n\n"
                "Could not fetch weather for any city. Nothing was sent.\n\n"
                + format_report_markdown(report)
            )
        lines = ["# Weather Digest — RESULTS", ""]
        inspiration = fetch_digest_inspiration(mark_used=True)
        try:
            lines.append(
                f"- Email: {send_weather_email(report, inspiration=inspiration)}"
            )
        except Exception as email_exc:
            lines.append(f"- Email: FAILED — {email_exc}")
        lines.append("")
        lines.append(format_report_markdown(report, inspiration))
        return "\n".join(lines)
    except Exception as exc:
        return (
            "# Weather Digest — FAILED\n\n"
            f"Unexpected server error: {exc}\n\n"
            f"```\n{traceback.format_exc()}\n```"
        )


@mcp.tool()
def get_city_weather(city_name: str, country_code: str = "IN") -> str:
    """
    Fetch weather for a single city by name.
    Defaults to India (country_code=IN).
    """
    try:
        city = CityConfig(name=city_name, country_code=country_code)
        result = fetch_city_weather(city)
        report = build_weather_report((city,), get_digest_timezone())
        report.cities = [result]
        return format_report_markdown(report)
    except Exception as exc:
        return (
            f"# Weather for {city_name} — FAILED\n\n"
            f"Unexpected server error: {exc}\n\n"
            f"```\n{traceback.format_exc()}\n```"
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
