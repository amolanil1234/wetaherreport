"""Send weather digest emails via SendGrid or SMTP (Gmail)."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from config import (
    get_email_provider,
    get_from_email,
    get_sendgrid_api_key,
    get_smtp_config,
    get_to_email,
)
from formatter import build_email_subject, format_report_html, format_report_text
from quotes import fetch_digest_inspiration
from weather import WeatherReport


def _send_via_sendgrid(
    report: WeatherReport,
    recipient: str,
    from_email: str,
) -> str:
    inspiration = fetch_digest_inspiration()
    message = Mail(
        from_email=from_email,
        to_emails=recipient,
        subject=build_email_subject(report),
        plain_text_content=format_report_text(report, inspiration),
        html_content=format_report_html(report, inspiration),
    )
    try:
        client = SendGridAPIClient(get_sendgrid_api_key())
        response = client.send(message)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to send email via SendGrid: {exc}. "
            "Verify SENDGRID_API_KEY and that FROM_EMAIL is a verified sender."
        ) from exc
    return f"Email sent to {recipient} via SendGrid (status {response.status_code})"


def _send_via_smtp(
    report: WeatherReport,
    recipient: str,
    from_email: str,
) -> str:
    smtp = get_smtp_config()
    inspiration = fetch_digest_inspiration()
    subject = build_email_subject(report)
    text_body = format_report_text(report, inspiration)
    html_body = format_report_html(report, inspiration)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if smtp.secure:
            server = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=30)
        else:
            server = smtplib.SMTP(smtp.host, smtp.port, timeout=30)
            server.starttls()
        with server:
            server.login(smtp.user, smtp.password)
            server.sendmail(from_email, [recipient], msg.as_string())
    except Exception as exc:
        raise RuntimeError(
            f"Failed to send email via SMTP ({smtp.host}): {exc}. "
            "For Gmail, use an App Password: https://myaccount.google.com/apppasswords"
        ) from exc

    return f"Email sent to {recipient} via SMTP ({smtp.host})"


def send_weather_email(report: WeatherReport, to_email: str | None = None) -> str:
    recipient = to_email or get_to_email()
    from_email = get_from_email()
    provider = get_email_provider()

    if provider == "sendgrid":
        return _send_via_sendgrid(report, recipient, from_email)
    return _send_via_smtp(report, recipient, from_email)
