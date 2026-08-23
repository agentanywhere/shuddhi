"""Errors that are the user's to fix, not bugs to report.

Lives in its own module so library code can raise a well-explained error
without importing the CLI (which imports the library — the other direction
is a cycle).
"""

from __future__ import annotations


class UserError(Exception):
    """Caused by input or environment, not by a defect in Shuddhi.

    The CLI prints `message`, then `hint` if there is one, and exits 2 —
    no traceback, because a traceback tells the user nothing they can act
    on. Anything NOT raised as this keeps its traceback, because an
    unexpected exception is a bug and hiding it wastes the report.
    """

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint
