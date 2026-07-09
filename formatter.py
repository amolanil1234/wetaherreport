"""Format weather reports as plain text and HTML email bodies."""

from __future__ import annotations

from datetime import datetime
from html import escape

from config import OPEN_METEO_ATTRIBUTION
from quotes import DigestInspiration, fetch_digest_inspiration
from weather import CityWeather, CurrentConditions, DailyForecast, WeatherReport


def _format_number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)}{suffix}"
    return f"{value:.1f}{suffix}"


def _format_wind(speed: float | None, direction: float | None) -> str:
    speed_text = _format_number(speed, " km/h")
    if direction is None:
        return speed_text
    return f"{speed_text} from {_format_number(direction, '°')}"


def build_email_subject(report: WeatherReport) -> str:
    date_label = datetime.now().strftime("%d %b %Y")
    city_names = ", ".join(city.city_name for city in report.cities)
    return f"Daily Weather — {city_names} — {date_label}"


def format_current_section(current: CurrentConditions) -> list[str]:
    return [
        f"  Conditions: {current.weather_description}",
        f"  Temperature: {_format_number(current.temperature_c, '°C')} (feels like {_format_number(current.apparent_temperature_c, '°C')})",
        f"  Humidity: {_format_number(current.humidity_percent, '%')}",
        f"  Wind: {_format_wind(current.wind_speed_kmh, current.wind_direction_deg)}",
        f"  Precipitation: {_format_number(current.precipitation_mm, ' mm')}",
        f"  Cloud cover: {_format_number(current.cloud_cover_percent, '%')}",
        f"  Observed at: {current.observed_at or 'N/A'}",
    ]


def format_daily_section(daily: list[DailyForecast]) -> list[str]:
    lines: list[str] = []
    for day in daily:
        lines.append(
            f"  {day.date}: {day.weather_description}, "
            f"{_format_number(day.temp_min_c, '°C')} – {_format_number(day.temp_max_c, '°C')}, "
            f"rain {_format_number(day.precipitation_sum_mm, ' mm')}, "
            f"wind max {_format_number(day.wind_max_kmh, ' km/h')}"
        )
        if day.sunrise or day.sunset:
            lines.append(f"    Sunrise {day.sunrise or 'N/A'}, Sunset {day.sunset or 'N/A'}")
    return lines


def format_city_text(city: CityWeather) -> str:
    lines = [f"{city.city_name}"]
    if city.error:
        lines.append(f"  Error: {city.error}")
        return "\n".join(lines)

    if city.coordinates:
        coords = city.coordinates
        lines.append(
            f"  Location: {coords.name}, {coords.country} "
            f"({coords.latitude:.2f}, {coords.longitude:.2f})"
        )

    if city.current:
        lines.append("  Current:")
        lines.extend(format_current_section(city.current))

    if city.daily:
        lines.append("  3-day forecast:")
        lines.extend(format_daily_section(city.daily))

    return "\n".join(lines)


def _inspiration_text(inspiration: DigestInspiration | None) -> list[str]:
    if not inspiration:
        return []
    lines: list[str] = ["3 ideas from James Clear", ""]
    if inspiration.subject:
        lines.append(inspiration.subject)
        lines.append("")
    for index, idea in enumerate(inspiration.ideas, start=1):
        lines.append(f"{index}. {idea}")
        lines.append("")
    if inspiration.question:
        lines.append("1 Question For You")
        lines.append("")
        lines.append(inspiration.question)
        lines.append("")
    return lines


def _inspiration_html(inspiration: DigestInspiration | None) -> str:
    if not inspiration:
        return ""
    idea_items = "".join(
        f"<li style=\"margin:0 0 12px 0;line-height:1.5;\">{escape(idea)}</li>"
        for idea in inspiration.ideas
    )
    subject = (
        f'<p style="margin:0 0 12px 0;font-size:13px;color:#555;">{escape(inspiration.subject)}</p>'
        if inspiration.subject
        else ""
    )
    question_block = ""
    if inspiration.question:
        question_block = f"""
        <p style="margin:18px 0 8px 0;font-size:16px;font-weight:700;color:#0b6e4f;">
          1 Question For You
        </p>
        <p style="margin:0;font-size:15px;line-height:1.5;">
          {escape(inspiration.question)}
        </p>
        """
    return f"""
    <div style="margin:20px 0;padding:16px 20px;border-left:4px solid #0b6e4f;background:#f3faf7;">
      <p style="margin:0 0 8px 0;font-size:18px;font-weight:700;color:#0b6e4f;">
        3 ideas from James Clear
      </p>
      {subject}
      <ol style="margin:0;padding-left:20px;">
        {idea_items}
      </ol>
      {question_block}
    </div>
    """


def format_report_text(
    report: WeatherReport,
    inspiration: DigestInspiration | None = None,
) -> str:
    inspiration = inspiration if inspiration is not None else fetch_digest_inspiration()
    sections = [
        "Daily Weather Digest",
        f"Generated: {report.generated_at}",
        f"Timezone: {report.timezone}",
        "",
        *_inspiration_text(inspiration),
    ]
    for city in report.cities:
        sections.append(format_city_text(city))
        sections.append("")
    sections.append(OPEN_METEO_ATTRIBUTION)
    if inspiration:
        sections.append("From James Clear's 3-2-1 newsletter")
    return "\n".join(sections).strip()


def _city_html_block(city: CityWeather) -> str:
    if city.error:
        return (
            f"<h2>{city.city_name}</h2>"
            f'<p style="color:#b00020;"><strong>Error:</strong> {city.error}</p>'
        )

    coords = city.coordinates
    current = city.current
    location = ""
    if coords:
        location = (
            f"<p><strong>Location:</strong> {coords.name}, {coords.country} "
            f"({coords.latitude:.2f}, {coords.longitude:.2f})</p>"
        )

    current_rows = ""
    if current:
        current_rows = f"""
        <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;width:100%;max-width:640px;">
          <tr><th colspan="2">Current conditions</th></tr>
          <tr><td>Conditions</td><td>{current.weather_description}</td></tr>
          <tr><td>Temperature</td><td>{_format_number(current.temperature_c, '°C')} (feels like {_format_number(current.apparent_temperature_c, '°C')})</td></tr>
          <tr><td>Humidity</td><td>{_format_number(current.humidity_percent, '%')}</td></tr>
          <tr><td>Wind</td><td>{_format_wind(current.wind_speed_kmh, current.wind_direction_deg)}</td></tr>
          <tr><td>Precipitation</td><td>{_format_number(current.precipitation_mm, ' mm')}</td></tr>
          <tr><td>Cloud cover</td><td>{_format_number(current.cloud_cover_percent, '%')}</td></tr>
          <tr><td>Observed at</td><td>{current.observed_at or 'N/A'}</td></tr>
        </table>
        """

    daily_rows = ""
    if city.daily:
        rows = []
        for day in city.daily:
            rows.append(
                "<tr>"
                f"<td>{day.date}</td>"
                f"<td>{day.weather_description}</td>"
                f"<td>{_format_number(day.temp_min_c, '°C')} – {_format_number(day.temp_max_c, '°C')}</td>"
                f"<td>{_format_number(day.precipitation_sum_mm, ' mm')}</td>"
                f"<td>{_format_number(day.wind_max_kmh, ' km/h')}</td>"
                f"<td>{day.sunrise or 'N/A'} / {day.sunset or 'N/A'}</td>"
                "</tr>"
            )
        daily_rows = f"""
        <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;width:100%;max-width:640px;margin-top:12px;">
          <tr>
            <th>Date</th><th>Conditions</th><th>Min–Max</th>
            <th>Rain</th><th>Wind max</th><th>Sunrise/Sunset</th>
          </tr>
          {''.join(rows)}
        </table>
        """

    return f"<h2>{city.city_name}</h2>{location}{current_rows}{daily_rows}"


def format_report_html(
    report: WeatherReport,
    inspiration: DigestInspiration | None = None,
) -> str:
    inspiration = inspiration if inspiration is not None else fetch_digest_inspiration()
    city_blocks = "".join(_city_html_block(city) for city in report.cities)
    quote_attr = ""
    if inspiration:
        quote_attr = (
            '<p style="margin-top:8px;font-size:11px;color:#888;">'
            "From "
            '<a href="https://jamesclear.com/3-2-1" target="_blank">'
            "James Clear's 3-2-1 newsletter</a>"
            "</p>"
        )
    return f"""
    <html>
      <body style="font-family:Segoe UI,Arial,sans-serif;color:#222;">
        <h1>Daily Weather Digest</h1>
        <p><strong>Generated:</strong> {report.generated_at}<br/>
           <strong>Timezone:</strong> {report.timezone}</p>
        {_inspiration_html(inspiration)}
        {city_blocks}
        <p style="margin-top:24px;font-size:12px;color:#666;">
          <a href="https://open-meteo.com/">{OPEN_METEO_ATTRIBUTION}</a>
        </p>
        {quote_attr}
      </body>
    </html>
    """.strip()


def format_report_markdown(
    report: WeatherReport,
    inspiration: DigestInspiration | None = None,
) -> str:
    inspiration = inspiration if inspiration is not None else fetch_digest_inspiration()
    lines = [
        "# Daily Weather Digest",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Timezone:** {report.timezone}",
        "",
    ]
    if inspiration:
        lines.append("## 3 ideas from James Clear")
        lines.append("")
        if inspiration.subject:
            lines.append(f"*{inspiration.subject}*")
            lines.append("")
        for index, idea in enumerate(inspiration.ideas, start=1):
            lines.append(f"{index}. {idea}")
            lines.append("")
        if inspiration.question:
            lines.append("## 1 Question For You")
            lines.append("")
            lines.append(inspiration.question)
            lines.append("")

    for city in report.cities:
        lines.append(f"## {city.city_name}")
        if city.error:
            lines.append(f"**Error:** {city.error}")
            lines.append("")
            continue

        if city.coordinates:
            coords = city.coordinates
            lines.append(
                f"**Location:** {coords.name}, {coords.country} "
                f"({coords.latitude:.2f}, {coords.longitude:.2f})"
            )

        if city.current:
            current = city.current
            lines.append("### Current")
            lines.append(f"- **Conditions:** {current.weather_description}")
            lines.append(
                f"- **Temperature:** {_format_number(current.temperature_c, '°C')} "
                f"(feels like {_format_number(current.apparent_temperature_c, '°C')})"
            )
            lines.append(f"- **Humidity:** {_format_number(current.humidity_percent, '%')}")
            lines.append(
                f"- **Wind:** {_format_wind(current.wind_speed_kmh, current.wind_direction_deg)}"
            )
            lines.append(f"- **Precipitation:** {_format_number(current.precipitation_mm, ' mm')}")
            lines.append(f"- **Cloud cover:** {_format_number(current.cloud_cover_percent, '%')}")
            lines.append(f"- **Observed at:** {current.observed_at or 'N/A'}")

        if city.daily:
            lines.append("### 3-day forecast")
            for day in city.daily:
                lines.append(
                    f"- **{day.date}:** {day.weather_description}, "
                    f"{_format_number(day.temp_min_c, '°C')} – {_format_number(day.temp_max_c, '°C')}, "
                    f"rain {_format_number(day.precipitation_sum_mm, ' mm')}, "
                    f"wind max {_format_number(day.wind_max_kmh, ' km/h')}"
                )
                if day.sunrise or day.sunset:
                    lines.append(f"  - Sunrise {day.sunrise or 'N/A'}, Sunset {day.sunset or 'N/A'}")
        lines.append("")

    lines.append(f"*{OPEN_METEO_ATTRIBUTION}*")
    if inspiration:
        lines.append("*From James Clear's 3-2-1 newsletter*")
    return "\n".join(lines)
