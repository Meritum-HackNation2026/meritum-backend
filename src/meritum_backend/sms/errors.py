"""Errors of the SMS channel.

Features:
    US-WTY-07, F-32
"""


class SmsNotSentError(Exception):
    """The gateway refused the message, did not answer, or answered oddly.

    Features:
        US-WTY-07, F-32
    """
