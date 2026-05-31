"""Structured type reference parsing for codebase graphs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TypeRef:
    """Structured reference to a type extracted from a type signature string."""
    name: str
    template_args: list[TypeRef] = field(default_factory=list)
    is_builtin: bool = False
    original_text: str = ""
    qualifiers: list[str] = field(default_factory=list)
