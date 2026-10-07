"""Standard-library core for ihav-openrouter-pareto: OpenRouter quality-or-usage versus price, with Pareto frontiers."""

from __future__ import annotations

__version__ = "0.1.0"


class ParetoError(Exception):
    """A user-facing failure; `code` becomes the JSON error code and `exit_code` the process status."""

    def __init__(self, message: str, code: str = "error", exit_code: int = 1):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
