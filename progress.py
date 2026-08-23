"""Terminal progress and structured events.

Two audiences, one source of truth, because they diverge badly if you let
them:

  * a person at a terminal wants a live bar, a rate, and an ETA;
  * `docker logs`, CI, and a file want timestamped lines they can grep and
    replay, with no cursor tricks and no escape codes.

So this module renders the same events differently depending on whether it
is attached to a TTY, and — regardless of either — appends every phase,
warning and error to `events.jsonl` in the output directory. That file is
what `factory.py ui` reads, which means the UI is never a second
implementation of progress: it is a view over the log the run already wrote.

Honouring the environment: NO_COLOR and TERM=dumb disable colour, a
non-UTF-8 stdout falls back to ASCII bar characters, and SHUDDHI_PROGRESS
(auto|tty|plain|none) overrides the automatic choice.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time

_RESET, _DIM, _BOLD = "\033[0m", "\033[2m", "\033[1m"
_BLUE, _GREEN, _YELLOW, _RED = "\033[34m", "\033[32m", "\033[33m", "\033[31m"

_BLOCKS = "▏▎▍▌▋▊▉█"


def _supports_colour(stream) -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "") in ("dumb", ""):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def _supports_unicode(stream) -> bool:
    enc = (getattr(stream, "encoding", "") or "").lower()
    return "utf" in enc


def human(n: float) -> str:
    """Bytes in units a person reads without counting digits."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000:
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1000
    return f"{n:,.1f} PB"


def duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


class EventLog:
    """Append-only JSONL of everything that happened, for the UI and for replay."""

    def __init__(self, out_dir: str | None):
        self.path = os.path.join(out_dir, "events.jsonl") if out_dir else None
        if self.path:
            os.makedirs(out_dir, exist_ok=True)

    def emit(self, kind: str, **fields) -> None:
        if not self.path:
            return
        rec = {"ts": time.time(), "kind": kind, **fields}
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass  # telemetry must never break a build


class Reporter:
    """Progress for a person, structured lines for a machine."""

    def __init__(self, out_dir: str | None = None, stream=None, mode: str | None = None):
        self.stream = stream or sys.stderr
        self.events = EventLog(out_dir)
        mode = mode or os.environ.get("SHUDDHI_PROGRESS", "auto")
        if mode == "auto":
            mode = "tty" if getattr(self.stream, "isatty", lambda: False)() else "plain"
        self.mode = mode
        self.colour = mode == "tty" and _supports_colour(self.stream)
        self.unicode = _supports_unicode(self.stream)
        self._phase = ""
        self._t0 = time.time()
        self._last_render = 0.0
        self._last_plain = 0.0
        self._open_line = False

    # -- styling ---------------------------------------------------------
    def _c(self, text: str, colour: str) -> str:
        return f"{colour}{text}{_RESET}" if self.colour else text

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            pass

    def _clear_line(self) -> None:
        if self._open_line and self.mode == "tty":
            self._write("\r\033[2K")
            self._open_line = False

    # -- public API ------------------------------------------------------
    def phase(self, title: str, index: int | None = None, total: int | None = None) -> None:
        self._clear_line()
        self._phase = title
        self._t0 = time.time()
        prefix = f"[{index}/{total}] " if index and total else ""
        if self.mode == "none":
            pass
        elif self.mode == "tty":
            self._write(f"\n{self._c('▸', _BLUE)} {self._c(prefix + title, _BOLD)}\n")
        else:
            self._write(f"{self._stamp()} phase  {prefix}{title}\n")
        self.events.emit("phase", title=title, index=index, total=total)

    def _stamp(self) -> str:
        return time.strftime("%H:%M:%S", time.gmtime())

    def update(self, done: int, total: int | None = None, *, unit: str = "docs",
               bytes_done: int | None = None, note: str = "") -> None:
        now = time.time()
        elapsed = max(1e-9, now - self._t0)
        rate = done / elapsed
        if self.mode == "none":
            return
        if self.mode == "tty":
            if now - self._last_render < 0.1:
                return
            self._last_render = now
            self._write("\r\033[2K" + self._line(done, total, unit, bytes_done, rate, elapsed, note))
            self._open_line = True
        else:
            # docker logs / CI: a line every 15s, never a cursor trick
            if now - self._last_plain < 15:
                return
            self._last_plain = now
            pct = f" {done / total:6.1%}" if total else ""
            thr = f" {human(bytes_done / elapsed)}/s" if bytes_done else f" {rate:,.0f} {unit}/s"
            self._write(f"{self._stamp()} progress{pct} {done:,} {unit}{thr}"
                        f"{' ' + note if note else ''}\n")
        self.events.emit("progress", done=done, total=total, bytes=bytes_done, note=note)

    def _line(self, done, total, unit, bytes_done, rate, elapsed, note) -> str:
        parts = []
        if total:
            frac = min(1.0, done / total)
            parts.append(self._bar(frac))
            parts.append(self._c(f"{frac:5.1%}", _BOLD))
        parts.append(f"{done:,} {unit}")
        if bytes_done:
            parts.append(self._c(f"{human(bytes_done / elapsed)}/s", _DIM))
        else:
            parts.append(self._c(f"{rate:,.0f} {unit}/s", _DIM))
        if total and rate > 0:
            parts.append(self._c(f"eta {duration((total - done) / rate)}", _DIM))
        if note:
            parts.append(self._c(note, _DIM))
        return "  ".join(parts)

    def _bar(self, frac: float, width: int = 24) -> str:
        cols = shutil.get_terminal_size((80, 24)).columns
        width = max(8, min(width, cols // 3))
        if self.unicode:
            filled = frac * width
            whole = int(filled)
            rem = filled - whole
            bar = "█" * whole
            if whole < width:
                bar += _BLOCKS[int(rem * 8)] if rem > 0 else " "
                bar += " " * (width - whole - 1)
        else:
            whole = int(frac * width)
            bar = "#" * whole + "-" * (width - whole)
        return self._c(bar, _BLUE)

    def finish(self, summary: str = "", **fields) -> None:
        self._clear_line()
        took = duration(time.time() - self._t0)
        if self.mode == "tty":
            self._write(f"{self._c('✓', _GREEN)} {summary} {self._c(f'({took})', _DIM)}\n")
        elif self.mode == "plain":
            self._write(f"{self._stamp()} done   {summary} in {took}\n")
        self.events.emit("finish", summary=summary, seconds=time.time() - self._t0, **fields)

    def warn(self, message: str) -> None:
        self._clear_line()
        if self.mode != "none":
            tag = self._c("WARNING", _YELLOW)
            stamp = "" if self.mode == "tty" else self._stamp() + " "
            self._write(f"{stamp}{tag}  {message}\n")
        self.events.emit("warning", message=message)

    def error(self, message: str) -> None:
        self._clear_line()
        if self.mode != "none":
            tag = self._c("ERROR", _RED)
            stamp = "" if self.mode == "tty" else self._stamp() + " "
            self._write(f"{stamp}{tag}  {message}\n")
        self.events.emit("error", message=message)

    def info(self, message: str) -> None:
        self._clear_line()
        if self.mode != "none":
            stamp = "" if self.mode == "tty" else self._stamp() + " "
            self._write(f"{stamp}{self._c(message, _DIM) if self.mode == 'tty' else message}\n")
        self.events.emit("info", message=message)
