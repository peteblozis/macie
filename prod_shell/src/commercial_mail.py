"""Self-service MACIE C verification and password-reset email delivery.

SMTP configuration is runtime-only. No registration links or tokens are
written to logs or displayed in the customer's HTTP signup response.

Production must configure a dedicated transactional email sender and
delivery/abuse controls before enabling the commercial registration UI.
"""
from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib
import ssl
from urllib.parse import quote


def mail_configured() -> bool:
    return all(os.environ.get(name) for name in (
        "MACIE_C_SMTP_HOST",
        "MACIE_C_SMTP_USERNAME",
        "MACIE_C_SMTP_PASSWORD",
        "MACIE_C_EMAIL_FROM",
        "MACIE_C_PUBLIC_ORIGIN",
    )) and os.environ["MACIE_C_PUBLIC_ORIGIN"].startswith("https://")


def send_token_message(email: str, token: str, purpose: str) -> None:
    if not mail_configured():
        raise RuntimeError("Commercial email delivery has not been configured.")
    if purpose not in ("verify", "reset"):
        raise ValueError("Invalid email action.")
    public_origin=os.environ["MACIE_C_PUBLIC_ORIGIN"].rstrip("/")
    if not public_origin.startswith("https://"):
        raise RuntimeError("Commercial product origin must be HTTPS.")
    # Fragment is NOT transmitted to an HTTP server, its query logs or referrers.
    # Customer-side JS sends the token once via POST in the request body.
    link=(public_origin+"/macie/c/commercial/#"
          + ("verify=" if purpose=="verify" else "reset=")
          + quote(token,safe=""))
    action="Verify your email" if purpose=="verify" else "Reset your password"
    message=EmailMessage()
    message["Subject"]="MACIE C — "+action
    message["From"]=os.environ["MACIE_C_EMAIL_FROM"]
    message["To"]=email
    message.set_content(
        f"{action} using this secure link:\n\n{link}\n\n"
        + ("This verification link expires in one hour."
           if purpose=="verify" else
           "This password reset link expires in thirty minutes.")
        + "\n\nIf you did not request this, you can ignore this message. "
        "Do not forward the link or your AI provider key.\n"
    )
    port=int(os.environ.get("MACIE_C_SMTP_PORT","587"))
    # Render FREE web services block outbound SMTP 25/465/587.
    # Port 2525 can work ONLY when the customer's existing SMTP relay
    # explicitly supports authenticated STARTTLS on that port. It is not
    # a universal substitute and must be tested with the configured relay.
    if port not in (587,2525):
        raise RuntimeError("SMTP authenticated STARTTLS port 587 or 2525 is required.")
    with smtplib.SMTP(os.environ["MACIE_C_SMTP_HOST"],port,timeout=15) as client:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        client.login(
            os.environ["MACIE_C_SMTP_USERNAME"],
            os.environ["MACIE_C_SMTP_PASSWORD"],
        )
        client.send_message(message)
