"""Rich-based output helpers for the KubeGuard CLI."""

from __future__ import annotations

import json
import sys
from typing import Any, List, Optional

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

def _supports_unicode() -> bool:
    """Return True if stdout can safely render Unicode characters without encoding errors."""
    try:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        "✓".encode(encoding)
        return True
    except (UnicodeEncodeError, AttributeError, TypeError):
        return False


_UNICODE_SUPPORTED = _supports_unicode()
_OK = "✓" if _UNICODE_SUPPORTED else "[OK]"
_DOT = "·" if _UNICODE_SUPPORTED else "*"
_WARN = "⚠" if _UNICODE_SUPPORTED else "!"


def get_symbol(unicode_sym: str, ascii_sym: str) -> str:
    """Return unicode_sym if stdout supports Unicode, else ascii_sym."""
    return unicode_sym if _UNICODE_SUPPORTED else ascii_sym


console = Console()
err_console = Console(stderr=True, style="bold red")

# ---------------------------------------------------------------------------
# Basic print helpers
# ---------------------------------------------------------------------------

def print_success(message: str) -> None:
    """Print a green success tick with message."""
    console.print(f"[bold green]{_OK}[/bold green] {message}")


def print_info(message: str) -> None:
    """Print an info line."""
    console.print(f"[cyan]{_DOT}[/cyan] {message}")


def print_warning(message: str) -> None:
    """Print a yellow warning."""
    console.print(f"[bold yellow]{_WARN}[/bold yellow] {message}", style="yellow")


def print_error(message: str, hint: Optional[str] = None) -> None:
    """Print a red error and an optional hint, then exit 1."""
    err_console.print(f"\n[bold red]Error:[/bold red] {message}")
    if hint:
        console.print(f"\n[dim]Hint:[/dim] {hint}")
    sys.exit(1)


def print_json(data: Any) -> None:
    """Dump data as pretty-printed JSON."""
    console.print_json(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Section header
# ---------------------------------------------------------------------------

def print_header(title: str) -> None:
    """Print a bold section header."""
    console.print(f"\n[bold white]{title}[/bold white]")
    console.print("─" * max(len(title), 30), style="dim")


# ---------------------------------------------------------------------------
# Key-value status block
# ---------------------------------------------------------------------------

def print_kv(rows: List[tuple], title: Optional[str] = None) -> None:
    """Print a key→value block, right-padding keys.

    Args:
        rows: list of (key, value, style) or (key, value).
        title: optional section heading.
    """
    if title:
        print_header(title)

    max_key = max((len(r[0]) for r in rows), default=10)
    for row in rows:
        key = row[0]
        value = row[1]
        style = row[2] if len(row) > 2 else "white"
        padded = f"{key:<{max_key}}"
        console.print(f"  [dim]{padded}[/dim] : [{style}]{value}[/{style}]")
    console.print()


# ---------------------------------------------------------------------------
# Table printer
# ---------------------------------------------------------------------------

def print_table(
    columns: List[str],
    rows: List[List[str]],
    title: Optional[str] = None,
    column_styles: Optional[List[str]] = None,
) -> None:
    """Render a rich table.

    Args:
        columns: list of column header strings.
        rows: list of row value lists.
        title: optional table title.
        column_styles: optional per-column rich style strings.
    """
    table = Table(
        title=title,
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        pad_edge=False,
    )

    for i, col in enumerate(columns):
        style = column_styles[i] if column_styles and i < len(column_styles) else "white"
        table.add_column(col, style=style, no_wrap=True)

    for row in rows:
        table.add_row(*[str(c) for c in row])

    console.print(table)


# ---------------------------------------------------------------------------
# Risk level colouring
# ---------------------------------------------------------------------------
RISK_STYLES = {
    "LOW": "bold green",
    "MEDIUM": "bold yellow",
    "HIGH": "bold red",
    "CRITICAL": "bold red",
}


def styled_risk(level: str) -> str:
    """Return a rich markup string for a risk level."""
    style = RISK_STYLES.get(level.upper(), "white")
    return f"[{style}]{level.upper()}[/{style}]"
