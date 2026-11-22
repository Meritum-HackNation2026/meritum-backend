"""Select the staff account store from the app repositories."""

from meritum_core.moderation import StaffRepository
from meritum_core.observability import AppRepositories


def build_staff(repositories: AppRepositories) -> StaffRepository:
    """Use the staff store configured for the application.

    Args:
        repositories: the stores built for the configured database provider.

    Returns:
        The configured staff store.

    Features:
        US-MOD-05, F-25
    """
    return repositories.staff
