"""Create a new receipt CSV or append rows to an existing one."""

from __future__ import annotations

import csv
from pathlib import Path

from extractor import CSV_COLUMNS, ReceiptRow

HEADER = [title for _key, title in CSV_COLUMNS]


def save_rows(path: str | Path, rows: list[ReceiptRow], mode: str) -> dict[str, int]:
    """Write rows.

    mode "new" replaces the file. mode "append" adds rows under the existing
    header and skips receipt numbers that are already in the file.
    """
    destination = Path(path)
    if not destination.suffix:
        destination = destination.with_suffix(".csv")
    destination.parent.mkdir(parents=True, exist_ok=True)

    if mode not in {"new", "append"}:
        raise ValueError("Choose a new CSV file or add to an existing one.")

    existing_ids: set[str] = set()
    append = mode == "append" and destination.exists() and destination.stat().st_size > 0
    if append:
        _ensure_header(destination)
        existing_ids = _existing_receipt_numbers(destination)

    kept: list[ReceiptRow] = []
    skipped = 0
    for row in rows:
        receipt_id = row.receipt_number.strip()
        if append and receipt_id and receipt_id in existing_ids:
            skipped += 1
            continue
        kept.append(row)
        if receipt_id:
            existing_ids.add(receipt_id)

    file_mode = "a" if append else "w"
    encoding = "utf-8" if append else "utf-8-sig"
    with destination.open(file_mode, newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        if not append:
            writer.writeheader()
        for row in kept:
            payload = row.as_csv()
            writer.writerow({title: payload[key] for key, title in CSV_COLUMNS})

    return {"written": len(kept), "skipped": skipped}


def _ensure_header(path: Path) -> None:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
    if header is None:
        return
    if [cell.strip() for cell in header] != HEADER:
        expected = ", ".join(HEADER)
        found = ", ".join(header)
        raise ValueError(
            "That CSV uses different columns, so rows were not added.\n"
            f"Expected: {expected}\n"
            f"Found: {found}"
        )


def _existing_receipt_numbers(path: Path) -> set[str]:
    found: set[str] = set()
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            receipt_id = (record.get(HEADER[0]) or "").strip()
            if receipt_id:
                found.add(receipt_id)
    return found
