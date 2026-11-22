"""Models of the external notifications: what is sent and where.

Features:
    US-POW-05, US-MOD-01, F-26
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

type TargetKind = Literal["webhook", "google_chat", "email"]
"""Where moderators are told: a signed JSON webhook, Google Chat or e-mail."""


class CaseAlert(BaseModel):
    """A new or updated case, as told outside the panel.

    Holds no personal data and no channel user id: only the case number, why it
    exists and where to open it.

    Attributes:
        case_id: the case number, e.g. ``#S-12``.
        reasons: why the case exists.
        panel_url: the absolute link to the case in the panel.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    model_config = ConfigDict(frozen=True)

    case_id: Annotated[str, Field(pattern=r"^#S-\d+$")]
    reasons: list[str]
    panel_url: str

    @property
    def case_number(self) -> str:
        """The number without ``#``: the form the e-mail Worker accepts.

        Returns:
            For example ``S-12``.
        """
        return self.case_id.removeprefix("#")


class NotifierConfig(BaseModel):
    """The administrator's choice of target for moderator notifications.

    Attributes:
        kind: webhook, google_chat or email.
        url: the https address of the webhook or Google Chat space; none for
            e-mail (the Worker's address comes from the settings).
        secret: signs the webhook body (HMAC-SHA256); never returned by the API.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    model_config = ConfigDict(extra="forbid")

    kind: TargetKind
    url: Annotated[str | None, Field(pattern=r"^https://\S+$", max_length=2000)] = None
    secret: SecretStr | None = None

    @model_validator(mode="after")
    def _webhook_and_chat_need_a_url(self) -> NotifierConfig:
        if self.kind != "email" and self.url is None:
            msg = f"{self.kind} needs a url"
            raise ValueError(msg)
        return self


class NotifierConfigView(BaseModel):
    """What the API shows of the configuration: the secret only as set or not.

    Attributes:
        kind: webhook, google_chat or email.
        url: the target address, if any.
        secret_set: whether a signing secret is stored.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    kind: TargetKind
    url: str | None
    secret_set: bool
