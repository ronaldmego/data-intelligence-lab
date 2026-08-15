"""Write the generated tables to CSV.

CSV, not parquet, on purpose: the files are meant to be *auditable* — a reviewer
can open them, and ``git diff`` catches any accidental change to the generator's
output. Headers come from the union of keys in the first row of each table.
"""

from __future__ import annotations

import csv
from pathlib import Path


def write_tables(tables: dict[str, list[dict]], out_dir: str | Path) -> dict[str, int]:
    """Write each table to ``out_dir/<name>.csv``. Returns row counts per table."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, rows in tables.items():
        path = out / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            if not rows:
                fh.write("")
                counts[name] = 0
                continue
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        counts[name] = len(rows)
    return counts
