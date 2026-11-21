"""Adapters of the SMS sender port.

Features:
    US-WTY-07, F-32
"""

from meritum_backend.sms.adapters._sms_gate import SmsGateSender

__all__ = ["SmsGateSender"]
