"""Sending email: a proposal, an invoice or a change order as a PDF, or a plain message."""
import logging

from django.conf import settings
from django.core.mail import EmailMessage

log = logging.getLogger(__name__)


def send(to, subject, body, attachment=None):
    """Send one email. `attachment` is (file name, the PDF's bytes). Returns True when it went out.

    With no email set up, the server only has somewhere to send it on a PC, where the email is
    written to the server window. A failure is logged and reported as False; it never breaks the page."""
    if not (to and settings.EMAIL_READY):
        return False
    message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [to] if isinstance(to, str) else list(to))
    if attachment:
        message.attach(attachment[0], attachment[1], "application/pdf")
    try:
        return message.send() == 1
    except Exception:                                              # a wrong password, no network, a refused address
        log.exception("Email to %s could not be sent", to)
        return False
