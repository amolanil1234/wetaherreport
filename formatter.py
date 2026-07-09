"""Format weather reports as plain text and HTML email bodies."""

from __future__ import annotations

from datetime import datetime
from html import escape

from quotes import DigestInspiration, fetch_digest_inspiration
from weather import CityWeather, CurrentConditions, WeatherReport


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


def _current_or_none(city: CityWeather) -> CurrentConditions | None:
    return None if city.error else city.current


def _city_metric_value(city: CityWeather, key: str) -> str:
    if city.error:
        return f"Error: {city.error}"
    current = city.current
    if not current:
        return "N/A"
    if key == "conditions":
        return current.weather_description
    if key == "temperature":
        return (
            f"{_format_number(current.temperature_c, '°C')} "
            f"(feels {_format_number(current.apparent_temperature_c, '°C')})"
        )
    if key == "humidity":
        return _format_number(current.humidity_percent, "%")
    if key == "wind":
        return _format_wind(current.wind_speed_kmh, current.wind_direction_deg)
    if key == "precipitation":
        return _format_number(current.precipitation_mm, " mm")
    if key == "cloud":
        return _format_number(current.cloud_cover_percent, "%")
    if key == "observed":
        return current.observed_at or "N/A"
    return "N/A"


_METRIC_ROWS: tuple[tuple[str, str], ...] = (
    ("conditions", "Conditions"),
    ("temperature", "Temperature"),
    ("humidity", "Humidity"),
    ("wind", "Wind"),
    ("precipitation", "Precipitation"),
    ("cloud", "Cloud cover"),
    ("observed", "Observed at"),
)


def _cities_comparison_text(cities: list[CityWeather]) -> list[str]:
    if not cities:
        return []
    lines = ["Current weather", ""]
    header = "Metric".ljust(14) + "".join(city.city_name.ljust(28) for city in cities)
    lines.append(header)
    lines.append("-" * len(header))
    for key, label in _METRIC_ROWS:
        row = label.ljust(14)
        for city in cities:
            row += _city_metric_value(city, key)[:26].ljust(28)
        lines.append(row)
    lines.append("")
    return lines


_ROMAN = ("I", "II", "III", "IV", "V")


def _idea_paragraphs(text: str) -> list[str]:
    """Split a long idea into reading-page paragraphs."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    sentences = [
        s.strip()
        for s in cleaned.replace("? ", "?|").replace(". ", ".|").split("|")
        if s.strip()
    ]
    if len(sentences) <= 2:
        return [cleaned]
    paragraphs: list[str] = []
    bucket: list[str] = []
    for sentence in sentences:
        bucket.append(sentence)
        joined = " ".join(bucket)
        # Keep paragraphs long enough to read like the newsletter.
        if len(joined) >= 280 or len(bucket) >= 3:
            paragraphs.append(joined)
            bucket = []
    if bucket:
        if paragraphs and len(" ".join(bucket)) < 80:
            paragraphs[-1] = f"{paragraphs[-1]} {' '.join(bucket)}"
        else:
            paragraphs.append(" ".join(bucket))
    return paragraphs or [cleaned]


def _inspiration_text(inspiration: DigestInspiration | None) -> list[str]:
    if not inspiration:
        return []
    lines: list[str] = ["3 Ideas From Me", ""]
    if inspiration.subject:
        lines.append(inspiration.subject)
        lines.append("")
    for index, idea in enumerate(inspiration.ideas):
        roman = _ROMAN[index] if index < len(_ROMAN) else str(index + 1)
        lines.append(f"{roman}.")
        lines.append("")
        paragraphs = _idea_paragraphs(idea)
        lines.append(f'"{paragraphs[0]}')
        for paragraph in paragraphs[1:]:
            lines.append("")
            lines.append(paragraph)
        if lines[-1].endswith('"'):
            pass
        else:
            lines[-1] = f'{lines[-1]}"'
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

    idea_blocks: list[str] = []
    for index, idea in enumerate(inspiration.ideas):
        roman = _ROMAN[index] if index < len(_ROMAN) else str(index + 1)
        paragraphs = _idea_paragraphs(idea)
        para_html: list[str] = []
        for i, paragraph in enumerate(paragraphs):
            prefix = "&ldquo;" if i == 0 else ""
            suffix = "&rdquo;" if i == len(paragraphs) - 1 else ""
            para_html.append(
                f'<p style="margin:0 0 16px 0;font-size:17px;line-height:1.75;color:#222;">'
                f"{prefix}{escape(paragraph)}{suffix}</p>"
            )
        idea_blocks.append(
            f"""
            <div style="margin:0 0 40px 0;text-align:center;">
              <p style="margin:0 0 16px 0;font-size:16px;font-weight:700;letter-spacing:0.05em;color:#111;">
                {roman}.
              </p>
              <div style="margin:0 auto;max-width:540px;font-style:italic;">
                {"".join(para_html)}
              </div>
            </div>
            """
        )

    subject = (
        f'<p style="margin:8px 0 28px 0;font-size:13px;color:#666;text-align:center;">'
        f"{escape(inspiration.subject)}</p>"
        if inspiration.subject
        else ""
    )
    question_block = ""
    if inspiration.question:
        question_block = f"""
        <div style="margin:8px auto 0 auto;max-width:540px;text-align:center;">
          <p style="margin:0 0 14px 0;font-size:18px;font-weight:700;color:#111;">
            1 Question For You
          </p>
          <p style="margin:0;font-size:17px;line-height:1.75;color:#222;font-style:italic;">
            {escape(inspiration.question)}
          </p>
        </div>
        """

    return f"""
    <div style="margin:28px auto;padding:28px 24px;max-width:640px;background:#fafafa;
                border:1px solid #ececec;font-family:Georgia,'Times New Roman',serif;">
      <p style="margin:0 0 6px 0;font-size:22px;font-weight:700;text-align:center;
                font-family:Segoe UI,Arial,sans-serif;color:#111;">
        3 Ideas From Me
      </p>
      {subject}
      {"".join(idea_blocks)}
      {question_block}
    </div>
    """


def _cities_comparison_html(cities: list[CityWeather]) -> str:
    if not cities:
        return ""
    header_cells = "".join(
        f'<th style="padding:8px;border:1px solid #ccc;background:#f5f5f5;text-align:left;">'
        f"{escape(city.city_name)}</th>"
        for city in cities
    )
    rows: list[str] = []
    for key, label in _METRIC_ROWS:
        value_cells = "".join(
            f'<td style="padding:8px;border:1px solid #ccc;">{escape(_city_metric_value(city, key))}</td>'
            for city in cities
        )
        rows.append(
            "<tr>"
            f'<td style="padding:8px;border:1px solid #ccc;font-weight:600;">{escape(label)}</td>'
            f"{value_cells}"
            "</tr>"
        )
    return f"""
    <h2 style="margin:24px 0 12px 0;">Current weather</h2>
    <table cellpadding="0" cellspacing="0" border="0"
           style="border-collapse:collapse;width:100%;max-width:720px;font-size:14px;">
      <tr>
        <th style="padding:8px;border:1px solid #ccc;background:#f5f5f5;text-align:left;">Metric</th>
        {header_cells}
      </tr>
      {''.join(rows)}
    </table>
    """


def format_report_text(
    report: WeatherReport,
    inspiration: DigestInspiration | None = None,
) -> str:
    inspiration = inspiration if inspiration is not None else fetch_digest_inspiration(
        mark_used=False
    )
    sections = [
        "Daily Weather Digest",
        f"Generated: {report.generated_at}",
        f"Timezone: {report.timezone}",
        "",
        *_inspiration_text(inspiration),
        *_cities_comparison_text(list(report.cities)),
    ]
    return "\n".join(sections).strip()


def format_report_html(
    report: WeatherReport,
    inspiration: DigestInspiration | None = None,
) -> str:
    inspiration = inspiration if inspiration is not None else fetch_digest_inspiration(
        mark_used=False
    )
    return f"""
    <html>
      <body style="font-family:Segoe UI,Arial,sans-serif;color:#222;">
        <h1>Daily Weather Digest</h1>
        <p><strong>Generated:</strong> {report.generated_at}<br/>
           <strong>Timezone:</strong> {report.timezone}</p>
        {_inspiration_html(inspiration)}
        {_cities_comparison_html(list(report.cities))}
      </body>
    </html>
    """.strip()


def format_report_markdown(
    report: WeatherReport,
    inspiration: DigestInspiration | None = None,
) -> str:
    inspiration = inspiration if inspiration is not None else fetch_digest_inspiration(
        mark_used=False
    )
    lines = [
        "# Daily Weather Digest",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Timezone:** {report.timezone}",
        "",
    ]
    if inspiration:
        lines.append("## 3 Ideas From Me")
        lines.append("")
        if inspiration.subject:
            lines.append(f"*{inspiration.subject}*")
            lines.append("")
        for index, idea in enumerate(inspiration.ideas):
            roman = _ROMAN[index] if index < len(_ROMAN) else str(index + 1)
            lines.append(f"**{roman}.**")
            lines.append("")
            paragraphs = _idea_paragraphs(idea)
            for i, paragraph in enumerate(paragraphs):
                prefix = '"' if i == 0 else ""
                suffix = '"' if i == len(paragraphs) - 1 else ""
                lines.append(f"> {prefix}{paragraph}{suffix}")
                lines.append("")
        if inspiration.question:
            lines.append("## 1 Question For You")
            lines.append("")
            lines.append(f"> {inspiration.question}")
            lines.append("")

    lines.append("## Current weather")
    lines.append("")
    header = "| Metric | " + " | ".join(city.city_name for city in report.cities) + " |"
    divider = "| --- | " + " | ".join("---" for _ in report.cities) + " |"
    lines.append(header)
    lines.append(divider)
    for key, label in _METRIC_ROWS:
        values = " | ".join(_city_metric_value(city, key) for city in report.cities)
        lines.append(f"| {label} | {values} |")
    return "\n".join(lines).strip()
