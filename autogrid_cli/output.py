"""Output helpers for the AutoGrid CLI."""

from __future__ import annotations

import json
from typing import Iterable, Sequence

from rich.console import Console
from rich.table import Table

console = Console()


def print_json(data: object) -> None:
    payload = json.dumps(data, indent=2, default=str)
    console.print(payload)


def print_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    title: str | None = None,
) -> None:
    table = Table(title=title, show_header=True, header_style="bold")
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*[_format_cell(cell) for cell in row])
    console.print(table)


def print_kv(title: str, items: Sequence[tuple[str, object]]) -> None:
    table = Table(title=title, show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    for key, value in items:
        table.add_row(key, _format_cell(value))
    console.print(table)


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value)
