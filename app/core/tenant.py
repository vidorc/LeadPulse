"""Tenant context — the principal + org scope threaded through every request.

Per the architecture review's §6, no service or query runs "unscoped": the
type signature carries the tenant. ``TenantContext`` is built once per request
by the auth pipeline (app/api/deps.py) from the verified JWT and passed
explicitly to services and repositories.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import Role


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable per-request principal + tenant scope."""

    org_id: int
    user_id: int
    email: str
    role: Role

    def require_role(self, minimum: Role) -> None:
        """Raise PermissionError if the principal is below ``minimum``.

        Callers in the API layer translate this into a 403; raising a plain
        exception here keeps the domain layer free of HTTP concerns.
        """
        if not self.role.at_least(minimum):
            raise PermissionError(
                f"Requires role >= {minimum.value}; principal has {self.role.value}"
            )

    @property
    def is_admin(self) -> bool:
        return self.role.at_least(Role.ADMIN)
