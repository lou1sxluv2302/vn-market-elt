"""Google Cloud credentials without keys (D12).

The owner's application-default credentials mint short-lived tokens for a
narrow service account (impersonation; the owner holds Token Creator on it).
The owner's own ADC file is never modified, so Terraform keeps working with it.
"""

from __future__ import annotations

from typing import Any


def impersonated(target_service_account: str, scope: str, lifetime_seconds: int) -> Any:
    """Credentials acting as `target_service_account`; they refresh themselves when they expire."""
    import google.auth
    from google.auth import impersonated_credentials

    owner, _ = google.auth.default(scopes=[scope])
    return impersonated_credentials.Credentials(
        source_credentials=owner,
        target_principal=target_service_account,
        target_scopes=[scope],
        lifetime=lifetime_seconds,
    )
