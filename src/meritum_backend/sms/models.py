"""Webhook body of the sms-gate.app gateway.

Features:
    US-WTY-07, F-32
"""

from pydantic import BaseModel, ConfigDict, Field

from meritum_backend.sms.constants import MMS_DOWNLOADED, SMS_RECEIVED


class ReceivedSms(BaseModel):
    """The ``payload`` of an ``sms:received`` or ``mms:downloaded`` event.

    Only the fields Meritum reads; MMS attachments are never parsed or kept.

    Attributes:
        message: the SMS text.
        body: the MMS text (RCS chats arrive as MMS); None when it has no text.
        sender: the sender's number (E.164); hashed before anything keeps it.

    Features:
        US-WTY-07, F-32
    """

    model_config = ConfigDict(frozen=True)

    message: str = ""
    body: str | None = None
    sender: str = Field(min_length=1, max_length=32)


class GatewayEvent(BaseModel):
    """One webhook call; ``device_id`` and ``id`` name it across the gateway's retries.

    Attributes:
        device_id: the gateway phone.
        event: the event type, e.g. ``sms:received``.
        id: the event id; a retry repeats it.
        payload: the message, for ``sms:received`` and ``mms:downloaded``.

    Features:
        US-WTY-07, F-32
    """

    model_config = ConfigDict(frozen=True)

    device_id: str = Field(alias="deviceId", pattern=r"^[\w-]{1,64}$")
    event: str
    id: str = Field(pattern=r"^[\w-]{1,64}$")
    payload: ReceivedSms | None = None

    @property
    def text(self) -> str | None:
        """The text to check: ``message`` of an SMS, ``body`` of an MMS.

        Returns:
            The text, or None for other events and for an MMS without text.

        Features:
            US-WTY-07, F-32
        """
        if self.payload is None:
            return None
        if self.event == SMS_RECEIVED:
            return self.payload.message
        if self.event == MMS_DOWNLOADED and (self.payload.body or "").strip():
            return self.payload.body
        return None
