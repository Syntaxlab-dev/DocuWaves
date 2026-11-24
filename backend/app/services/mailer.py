"""Sending e-mail, for the notifications in services/mail_notifications.py.

Off unless SMTP_HOST is set. DocuWaves has no mail server of its own and
never guesses one: an instance that was not given an SMTP server sends
nothing, and the account settings do not offer notifications at all --
rather than a checkbox that silently does nothing.

WHAT IT MUST NEVER DO, as with webhooks: slow a save down or fail it.
Messages go out on a small background pool with a timeout; a mail server
that is down is a log line, not an error the author sees. Nothing is
queued across a restart -- a notification is a courtesy, not a delivery
guarantee, and a durable queue would be a second database to back up.

The password is never logged, and neither is a recipient's address (logs
get pasted into issue threads): a failure names the SMTP host only.
"""
import logging
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.settings import settings

log = logging.getLogger("docuwaves")

_TIMEOUT_SECONDS = 15
SECURITY = ("starttls", "ssl", "none")
_DEFAULT_PORTS = {"starttls": 587, "ssl": 465, "none": 25}

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mail")


def is_enabled() -> bool:
    return bool(settings.smtp_host) and bool(sender())


def sender() -> str:
    return settings.smtp_from or (settings.smtp_username if "@" in settings.smtp_username else "")


def _security() -> str:
    return settings.smtp_security if settings.smtp_security in SECURITY else "starttls"


def build(to: str, subject: str, text: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender()
    message["To"] = to
    # One line, whatever a page title contained: a header with a line
    # break in it is a header injection.
    message["Subject"] = " ".join(subject.split())[:200]
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender().rsplit("@", 1)[-1].strip(">") or None)
    # Automatic, so an out-of-office reply is not sent back to it.
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(text)
    return message


class _SSL(smtplib.SMTP_SSL):
    """SMTP_SSL that checks the certificate against `tls_name` rather than
    the address it connects to (SMTP_TLS_SERVER_NAME)."""

    tls_name = ""

    def _get_socket(self, host, port, timeout):
        plain = smtplib.SMTP._get_socket(self, host, port, timeout)
        return self.context.wrap_socket(plain, server_hostname=self.tls_name or host)


def deliver(message: EmailMessage) -> None:
    """Sends one message now, in this thread. Raises on failure."""
    security = _security()
    port = settings.smtp_port or _DEFAULT_PORTS[security]
    context = ssl.create_default_context()
    tls_name = settings.smtp_tls_server_name
    if security == "ssl" and tls_name:
        server: smtplib.SMTP = _SSL(timeout=_TIMEOUT_SECONDS, context=context)
        server.tls_name = tls_name
        server.connect(settings.smtp_host, port)
    elif security == "ssl":
        server = smtplib.SMTP_SSL(settings.smtp_host, port, timeout=_TIMEOUT_SECONDS, context=context)
    else:
        server = smtplib.SMTP(settings.smtp_host, port, timeout=_TIMEOUT_SECONDS)
    with server:
        if security == "starttls":
            if tls_name:
                # starttls() checks the certificate against _host, the name
                # connected to; the configured name replaces it for that.
                server._host = tls_name
            server.starttls(context=context)
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def _deliver_logged(message: EmailMessage) -> None:
    try:
        deliver(message)
    except Exception as exc:  # noqa: BLE001 -- any failure is a log line, never a crash
        log.warning("E-mail via %s failed: %s", settings.smtp_host, type(exc).__name__)


def send(to: str, subject: str, text: str) -> None:
    """Queues one message. Returns at once; does nothing while e-mail is off."""
    if not is_enabled() or not to:
        return
    _pool.submit(_deliver_logged, build(to, subject, text))
