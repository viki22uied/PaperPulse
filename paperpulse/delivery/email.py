"""Email delivery over SMTP.

Credentials come from the environment so they never touch the repo:
``PAPERPULSE_SMTP_HOST``, ``PAPERPULSE_SMTP_PORT`` (default 587),
``PAPERPULSE_SMTP_USER``, ``PAPERPULSE_SMTP_PASSWORD``.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_email(
    markdown: str,
    *,
    to: str,
    subject: str = "PaperPulse digest",
    sender: str | None = None,
) -> None:
    host = os.getenv("PAPERPULSE_SMTP_HOST")
    if not host:
        raise RuntimeError(
            "set PAPERPULSE_SMTP_HOST (and _PORT/_USER/_PASSWORD) to send email."
        )
    port = int(os.getenv("PAPERPULSE_SMTP_PORT", "587"))
    user = os.getenv("PAPERPULSE_SMTP_USER")
    password = os.getenv("PAPERPULSE_SMTP_PASSWORD")
    sender = sender or user or "paperpulse@localhost"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(markdown)
    # A minimal HTML alternative so mail clients render the markdown as text.
    message.add_alternative(
        f"<pre style='font-family:ui-monospace,monospace'>{markdown}</pre>",
        subtype="html",
    )

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)
