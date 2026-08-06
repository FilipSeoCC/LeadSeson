"""Resend email client for outreach sends.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md modul 5 (sekcja 2) proponuje Amazon SES
jako tanszy kanal wysylki (~0.10 USD/1000 maili). Ten repo uzywa zamiast tego
Resend, konsekwentnie z istniejaca integracja w repo `startupai` (audit-request
form, RESEND_API_KEY/RESEND_FROM_EMAIL) -- ta sama rodzina projektow (ai-ops.pl),
prosty REST call, zero konfiguracji domeny/sandboxa SES od zera. Migracja na SES
jest mozliwa pozniej czysto kosztowo (sekcja 11), nie zmienia nic w
outreach/send/outreach_email.py, ktore zna tylko send_email().

Wymaga RESEND_API_KEY w .env. RESEND_FROM_EMAIL opcjonalny (domyslnie
"AI-Ops <kontakt@ai-ops.pl>").
"""
import base64
import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_TIMEOUT = 30


class ResendConfigError(RuntimeError):
    """Raised when RESEND_API_KEY is missing."""


class ResendAPIError(RuntimeError):
    """Wraps a Resend error response with its actual message."""


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachment_path: str | None = None,
    attachment_filename: str | None = None,
    reply_to: str | None = None,
) -> dict:
    """Sends one email via Resend. Returns {"id": <resend message id>}.

    Raises ResendConfigError if RESEND_API_KEY is missing, and ResendAPIError
    on any non-2xx response (invalid domain, quota, bad attachment) -- caller
    decides how to record that as a failed OutreachEvent.
    """
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise ResendConfigError(
            "RESEND_API_KEY nie jest ustawiony w .env. Zdobądź klucz na resend.com "
            "(ten sam Resend, którego repo startupai już używa do formularza audytu)."
        )

    sender = os.getenv("RESEND_FROM_EMAIL", "AI-Ops <kontakt@ai-ops.pl>")
    payload = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body
    if reply_to:
        payload["reply_to"] = reply_to
    if attachment_path:
        with open(attachment_path, "rb") as handle:
            content_b64 = base64.b64encode(handle.read()).decode("ascii")
        payload["attachments"] = [
            {"filename": attachment_filename or os.path.basename(attachment_path), "content": content_b64}
        ]

    resp = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": os.urandom(16).hex(),
        },
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if not resp.ok:
        try:
            message = resp.json().get("message", resp.text)
        except ValueError:
            message = resp.text
        raise ResendAPIError(f"Resend {resp.status_code}: {message}")

    data = resp.json()
    if not data.get("id"):
        raise ResendAPIError(f"Resend zwrocil odpowiedz bez id wiadomosci: {data}")
    return data
