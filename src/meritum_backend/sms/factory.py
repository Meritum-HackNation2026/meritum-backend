"""Builds the SMS sender from settings.

Features:
    US-WTY-07, F-32
"""

from meritum_backend.settings import Settings
from meritum_backend.sms.adapters import SmsGateSender
from meritum_backend.sms.ports import SmsSender


def build_sms(settings: Settings) -> SmsSender | None:
    """Build the gateway sender when its credentials are configured.

    Args:
        settings: the app settings.

    Returns:
        The sms-gate.app sender, or None (the webhook then answers 404).

    Features:
        US-WTY-07, F-32
    """
    username = settings.sms_gateway_username or ""
    password = settings.sms_gateway_password
    secret = password.get_secret_value() if password is not None else ""
    if not (username and secret):
        return None
    return SmsGateSender(username, secret)
