"""Ports of the external notifications: the sender and the configuration store.

Features:
    US-POW-05, US-MOD-01, F-26
"""

from typing import Protocol

from meritum_backend.notifications.models import CaseAlert, NotifierConfig


class NotifyError(Exception):
    """The target refused the alert or did not answer.

    Features:
        US-POW-05, US-MOD-01, F-26
    """


class ExternalNotifier(Protocol):
    """Tells moderators about a case outside the panel (port).

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    async def send(self, alert: CaseAlert) -> None:
        """Deliver one alert.

        Args:
            alert: the case to announce.

        Raises:
            NotifyError: the target refused it or did not answer.
        """
        ...


class NotifierConfigStore(Protocol):
    """Keeps the administrator's target (port).

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    async def get(self) -> NotifierConfig | None:
        """Read the target.

        Returns:
            The configuration, or None when none was set.
        """
        ...

    async def save(self, config: NotifierConfig) -> None:
        """Replace the target.

        Args:
            config: the new configuration.
        """
        ...

    async def delete(self) -> None:
        """Remove the target."""
        ...
