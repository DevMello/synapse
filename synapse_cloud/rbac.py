"""Role-based access control helpers.

Roles (membership_role enum): owner > admin > operator > viewer. Most write
actions and all daemon commands require operator+. HITL approval / revoke /
membership changes require admin+ (units refine as needed).
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    owner = "owner"
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


_ORDER = {Role.viewer: 0, Role.operator: 1, Role.admin: 2, Role.owner: 3}


def role_at_least(role: str, minimum: Role) -> bool:
    try:
        return _ORDER[Role(role)] >= _ORDER[minimum]
    except (KeyError, ValueError):
        return False


def can_write(role: str) -> bool:
    return role_at_least(role, Role.operator)


def can_admin(role: str) -> bool:
    return role_at_least(role, Role.admin)
