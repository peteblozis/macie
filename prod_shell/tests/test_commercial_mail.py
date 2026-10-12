"""Verify MACIE C sends real-format transactional email over verified TLS.

This is an isolated local SMTP fixture, NOT proof of delivery by a live mail
provider. No emails are sent, no provider account configured or contacted.
"""
from email.message import EmailMessage

import pytest

from prod_shell.src import commercial_mail as m


@pytest.fixture
def fake_smtp(monkeypatch):
    sent=[]
    class SMTP:
        def __init__(self,host,port,timeout):
            sent.append(("connect",host,port,timeout))
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def ehlo(self):sent.append(("ehlo",))
        def starttls(self,context=None):
            assert context is not None
            sent.append(("tls",))
        def login(self,user,password):
            sent.append(("login",user,password))
        def send_message(self,message):
            assert isinstance(message,EmailMessage)
            sent.append(("message",message))
    monkeypatch.setattr(m.smtplib,"SMTP",SMTP)
    for key,value in {
        "MACIE_C_SMTP_HOST":"smtp.existing-relay.example",
        "MACIE_C_SMTP_USERNAME":"ci-user",
        "MACIE_C_SMTP_PASSWORD":"ci-only-not-real",
        "MACIE_C_EMAIL_FROM":"no-reply@commercial.example",
        "MACIE_C_PUBLIC_ORIGIN":"https://example.invalid",
    }.items():
        monkeypatch.setenv(key,value)
    return sent


@pytest.mark.parametrize("port",["587","2525"])
def test_verification_link_sent_only_after_authenticated_starttls(monkeypatch,fake_smtp,port):
    monkeypatch.setenv("MACIE_C_SMTP_PORT",port)
    m.send_token_message("person@example.invalid","test-link-token","verify")
    events=[x[0] for x in fake_smtp]
    assert events==["connect","ehlo","tls","ehlo","login","message"]
    assert fake_smtp[0][2]==int(port)
    message=fake_smtp[-1][1]
    content=message.get_content()
    assert "#verify=test-link-token" in content
    assert "?verify=" not in content
    assert message["To"]=="person@example.invalid"


def test_password_reset_uses_shorter_ttl_and_fragment(monkeypatch,fake_smtp):
    monkeypatch.setenv("MACIE_C_SMTP_PORT","2525")
    m.send_token_message("person@example.invalid","test-reset-token","reset")
    text=fake_smtp[-1][1].get_content()
    assert "#reset=test-reset-token" in text
    assert "thirty minutes" in text


def test_never_sends_unprotected_smtp(fake_smtp,monkeypatch):
    monkeypatch.setenv("MACIE_C_SMTP_PORT","25")
    with pytest.raises(RuntimeError):
        m.send_token_message("person@example.invalid","test-token","verify")
    assert fake_smtp==[]


def test_missing_email_credentials_fails_closed(monkeypatch):
    monkeypatch.delenv("MACIE_C_SMTP_HOST",raising=False)
    assert not m.mail_configured()
    with pytest.raises(RuntimeError,match="not been configured"):
        m.send_token_message("person@example.invalid","test-token","verify")
