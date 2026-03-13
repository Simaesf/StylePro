"""
Tests for stylepro.core.permissions.
"""

import pytest
from stylepro.core.permissions import (
    Role,
    Permission,
    AccessContext,
    ROLE_PERMISSIONS,
    check_permission,
    require_permission,
)


def test_role_values():
    assert Role.ADMIN.value == "admin"
    assert Role.USER.value == "user"
    assert Role.GUEST.value == "guest"


def test_admin_has_all_permissions():
    ctx = AccessContext(role=Role.ADMIN)
    for perm in Permission:
        assert check_permission(ctx, perm), f"ADMIN should have {perm}"


def test_guest_has_no_permissions():
    ctx = AccessContext(role=Role.GUEST)
    for perm in Permission:
        assert not check_permission(ctx, perm), f"GUEST should not have {perm}"


def test_user_permissions():
    ctx = AccessContext(role=Role.USER)
    assert check_permission(ctx, Permission.EDIT_PERSONAL)
    assert check_permission(ctx, Permission.SAVE_THEME)
    assert check_permission(ctx, Permission.VIEW_EDITOR)
    assert not check_permission(ctx, Permission.EDIT_GLOBAL)
    assert not check_permission(ctx, Permission.DELETE_THEME)


def test_require_permission_raises_for_guest():
    ctx = AccessContext(role=Role.GUEST)
    with pytest.raises(PermissionError):
        require_permission(ctx, Permission.VIEW_EDITOR)


def test_require_permission_passes_for_admin():
    ctx = AccessContext(role=Role.ADMIN)
    require_permission(ctx, Permission.DELETE_THEME)  # must not raise


def test_role_permissions_is_mutable():
    """Callers can extend the permission table without patching internals."""
    original = set(ROLE_PERMISSIONS[Role.GUEST])
    ROLE_PERMISSIONS[Role.GUEST].add(Permission.VIEW_EDITOR)
    assert check_permission(AccessContext(role=Role.GUEST), Permission.VIEW_EDITOR)
    # Restore to avoid cross-test contamination.
    ROLE_PERMISSIONS[Role.GUEST] = original
