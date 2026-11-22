"""Builds the external notifier and the case announcer.

Features:
    US-POW-05, US-MOD-01, F-26
"""

from collections.abc import Sequence

from meritum_core.observability import AppRepositories

from meritum_backend.auth.constants import LOCAL_URL, PUBLIC_URLS
from meritum_backend.constants import LOCAL_ENV
from meritum_backend.notifications.adapters import (
    EmailWorkerNotifier,
    GoogleChatNotifier,
    MemoryNotifierConfigStore,
    PostgresNotifierConfigStore,
    WebhookNotifier,
)
from meritum_backend.notifications.announcer import CaseAnnouncer
from meritum_backend.notifications.models import NotifierConfig
from meritum_backend.notifications.ports import ExternalNotifier, NotifierConfigStore
from meritum_backend.settings import Settings


def build_notifier(
    config: NotifierConfig, settings: Settings, recipients: Sequence[str]
) -> ExternalNotifier | None:
    """The sender for the administrator's choice.

    Args:
        config: the stored target.
        settings: the app settings (the e-mail Worker's address and secret).
        recipients: the moderators' addresses, for e-mail.

    Returns:
        The sender, or None for e-mail while the Worker is not configured.

    Features:
        US-POW-05, US-MOD-01, F-26
    """
    secret = config.secret.get_secret_value() if config.secret is not None else ""
    if config.kind == "email":
        worker_secret = settings.email_worker_signing_secret
        if settings.email_worker_url is None or worker_secret is None:
            return None
        return EmailWorkerNotifier(
            settings.email_worker_url, worker_secret.get_secret_value(), recipients
        )
    url = config.url or ""
    if config.kind == "google_chat":
        return GoogleChatNotifier(url)
    return WebhookNotifier(url, secret)


def build_config_store(settings: Settings) -> NotifierConfigStore:
    """Use the shared API schema outside local development.

    Args:
        settings: environment and API database connection.

    Returns:
        PostgreSQL in deployed environments, memory locally.

    Features:
        US-POW-05, US-MOD-01, F-26
    """
    if settings.env == LOCAL_ENV:
        return MemoryNotifierConfigStore()
    return PostgresNotifierConfigStore(settings.database_url)


def build_announcer(
    settings: Settings, repositories: AppRepositories, configs: NotifierConfigStore
) -> CaseAnnouncer:
    """Wire the announcer over the app repositories.

    Args:
        settings: the app settings.
        repositories: the stores of the app schema.
        configs: the administrator's target.

    Returns:
        The announcer the hand-off endpoints call.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def make(
        config: NotifierConfig, recipients: Sequence[str]
    ) -> ExternalNotifier | None:
        return build_notifier(config, settings, recipients)

    base = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    return CaseAnnouncer(
        repositories.cases,
        repositories.staff,
        settings.admin_emails,
        repositories.notifications,
        configs,
        make,
        base,
    )
