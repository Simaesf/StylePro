"""
stylepro.core.permissions
--------------------------
Role-based access control.  Implemented in Phase 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Role(str, Enum):
    ADMIN = "admin"
    """Full access: edit global themes, save, delete."""

    USER = "user"
    """Can edit and save personal themes only."""

    GUEST = "guest"
    """View only — editor button hidden."""


class Permission(str, Enum):
    EDIT_GLOBAL = "edit_global"
    EDIT_PERSONAL = "edit_personal"
    SAVE_THEME = "save_theme"
    DELETE_THEME = "delete_theme"
    VIEW_EDITOR = "view_editor"


# Table-driven role -> permission mapping.
# Intentionally module-level and mutable so callers can extend it
# without patching library internals.
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        Permission.EDIT_GLOBAL,
        Permission.EDIT_PERSONAL,
        Permission.SAVE_THEME,
        Permission.DELETE_THEME,
        Permission.VIEW_EDITOR,
    },
    Role.USER: {
        Permission.EDIT_PERSONAL,
        Permission.VIEW_EDITOR,
    },
    Role.GUEST: set(),
}


@dataclass
class AccessContext:
    """Carries the identity and role of the current user."""

    role: Role
    user_id: Optional[str] = None
    session_id: Optional[str] = None


def check_permission(ctx: AccessContext, permission: Permission) -> bool:
    """Return True if *ctx.role* holds *permission*."""
    return permission in ROLE_PERMISSIONS.get(ctx.role, set())


def require_permission(ctx: AccessContext, permission: Permission) -> None:
    """
    Raise PermissionError with a descriptive message if the role
    does not hold *permission*.
    """
    if not check_permission(ctx, permission):
        raise PermissionError(
            f"Role '{ctx.role.value}' does not have permission '{permission.value}'. "
            f"Required role must hold: {permission.value!r}."
        )
