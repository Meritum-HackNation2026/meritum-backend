"""Errors of the voice message download.

Features:
    US-SPR-11, US-WTY-06, F-08, F-03
"""


class VoiceDownloadError(Exception):
    """The attachment could not be fetched: a technical failure, not a verdict.

    Features:
        US-SPR-11, F-08
    """


class VoiceTooLargeError(VoiceDownloadError):
    """The attachment is over MAX_AUDIO_BYTES: the person is told to send less.

    Features:
        US-SPR-11, F-08
    """
