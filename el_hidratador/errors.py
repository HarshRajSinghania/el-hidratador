"""Typed error taxonomy for El Hidratador.

Every refusal is explicit. Nothing in this package fails silently, and no error
carries provider credentials, transcripts, or private identifiers.
"""

from __future__ import annotations


class HidratadorError(Exception):
    """Base class for every error raised by this package."""


class ValidationError(HidratadorError, ValueError):
    """Input did not satisfy a documented precondition."""


class Conflict(HidratadorError, ValueError):
    """An ownership, budget, or lifecycle constraint refused an operation."""


class NotFound(HidratadorError, KeyError):
    """A referenced task, session, or checkpoint does not exist."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.args[0]) if self.args else self.__class__.__name__


class BudgetExceeded(Conflict):
    """The task token budget is exhausted."""


class LeaseExpired(Conflict):
    """The session lease is no longer valid."""


class AdapterError(HidratadorError):
    """An external adapter (GitHub CLI, Docker, dashboard) failed or refused."""
