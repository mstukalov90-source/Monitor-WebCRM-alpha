"""Errors for the statistics report constructor."""

from __future__ import annotations


class ReportError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
