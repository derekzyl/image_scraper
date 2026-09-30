"""Read PalmPay receipt screenshots into structured rows."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

CSV_COLUMNS: list[tuple[str, str]] = [
    ("receipt_number", "Receipt Number"),
    ("name", "Name"),
    ("sender_name", "Sender Name"),
    ("recipient_number", "Recipient Number"),
    ("source_file", "Source File"),
]

_LABELS: list[tuple[str, re.Pattern[str]]] = [
    ("recipient", re.compile(r"recipient", re.IGNORECASE)),
    ("sender", re.compile(r"sender", re.IGNORECASE)),
    ("transaction_info", re.compile(r"transaction\s*info", re.IGNORECASE)),
    ("transaction_type", re.compile(r"transaction\s*type", re.IGNORECASE)),
    ("purpose", re.compile(r"what'?s\s*it\s*for", re.IGNORECASE)),
    ("transaction_id", re.compile(r"transaction\s*id", re.IGNORECASE)),
    ("session_id", re.compile(r"session\s*id", re.IGNORECASE)),
]

_ACCOUNT_RE = re.compile(
    r"^(?P<bank>.+?)(?:\s*\|\s*|\s+[Il1]\s+)(?P<acct>[0-9][0-9\s]{8,})$"
)
_ACCOUNT_LOOSE_RE = re.compile(
    r"^(?P<bank>[A-Za-z][A-Za-z .'\-]{1,40}?)\s+(?P<acct>[0-9][0-9\s]{8,})$"
)


@dataclass
class ReceiptRow:
    receipt_number: str = ""
    name: str = ""
    sender_name: str = ""
    recipient_number: str = ""
    source_file: str = ""
    source_path: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_csv(self) -> dict[str, str]:
        return {key: getattr(self, key) for key, _title in CSV_COLUMNS}

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        for key, title in CSV_COLUMNS:
            if key == "source_file":
                continue
            if not str(getattr(self, key)).strip():
                missing.append(title)
        return missing


class ReceiptExtractor:
    """Lazily loads the OCR engine, then parses one receipt at a time."""

    def __init__(self) -> None:
        self._ocr = None

    def extract(self, path: str | Path) -> ReceiptRow:
        image_path = Path(path)
        row = ReceiptRow(source_file=image_path.name, source_path=str(image_path))
        try:
            image = _prepare_image(image_path)
            parsed = _parse_ocr(self._read(image))
            if _needs_retry(parsed):
                fallback = _parse_ocr(self._read(_prepare_image(image_path, enhance=False)))
                parsed = _merge_parses(parsed, fallback)
            row.receipt_number = parsed["receipt_number"]
            row.name = parsed["name"]
            row.sender_name = parsed["sender_name"]
            row.recipient_number = parsed["recipient_number"]
            if row.missing_fields:
                row.error = "Some fields were not found. You can type them in before saving."
        except Exception as exc:  # noqa: BLE001 - show a readable row instead of aborting the batch
            row.error = f"Could not read this image ({exc})."
        return row

    def _read(self, image) -> list:
        result, _elapsed = self._engine()(image)
        return result or []

    def _engine(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr


def _prepare_image(path: Path, enhance: bool = True):
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    long_side = max(image.size)
    if enhance and long_side < 1800:
        scale = min(3, max(2, round(3000 / long_side)))
        image = image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )
        image = ImageEnhance.Contrast(image).enhance(1.8)
        image = image.filter(ImageFilter.SHARPEN)
        image = image.filter(ImageFilter.SHARPEN)
    import numpy as np

    return np.array(image)


def _needs_retry(parsed: dict[str, str]) -> bool:
    return not all(
        parsed.get(key)
        for key in ("receipt_number", "name", "sender_name", "recipient_number")
    )


def _merge_parses(primary: dict[str, str], fallback: dict[str, str]) -> dict[str, str]:
    merged = dict(primary)
    for key in ("receipt_number", "recipient_number"):
        if not merged.get(key):
            merged[key] = fallback.get(key, "")
    for key in ("name", "sender_name"):
        merged[key] = _prefer_name(merged.get(key, ""), fallback.get(key, ""))
    return merged


def _prefer_name(first: str, second: str) -> str:
    if not first:
        return second
    if not second:
        return first
    if first.count(" ") != second.count(" "):
        return first if first.count(" ") > second.count(" ") else second
    return first if len(first) >= len(second) else second


def _parse_ocr(result: list) -> dict[str, str]:
    lines = _group_lines(_items_from_result(result))
    indexes = _label_indexes(lines)

    name = _section_value(lines, indexes, "recipient", "sender", kind="name")
    sender = _section_value(lines, indexes, "sender", "transaction_info", kind="name")
    receipt = _transaction_id(lines, indexes)
    account = _account_digits(lines, indexes)
    return {
        "receipt_number": receipt,
        "name": name,
        "sender_name": sender,
        "recipient_number": to_recipient_number(account),
    }


def to_recipient_number(account_digits: str) -> str:
    """Turn the account after the bank name into the recipient number.

    PalmPay prints the 10-digit account without the leading 0. That 0 is
    added here. A value that already starts with 0 is left unchanged.
    """
    digits = re.sub(r"\D", "", account_digits or "")
    if not digits:
        return ""
    if digits.startswith("0"):
        return digits
    return "0" + digits


def _items_from_result(result: list) -> list[dict]:
    items = []
    for entry in result:
        if len(entry) < 3:
            continue
        box, text, score = entry[0], str(entry[1]), float(entry[2])
        if score < 0.45 or not str(text).strip():
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        items.append(
            {
                "text": _clean(str(text)),
                "score": score,
                "x": min(xs),
                "y": min(ys),
                "x2": max(xs),
                "y2": max(ys),
            }
        )
    return items


def _group_lines(items: list[dict]) -> list[dict]:
    if not items:
        return []
    heights = [max(8.0, item["y2"] - item["y"]) for item in items]
    tolerance = max(12.0, statistics.median(heights) * 0.45)
    items = sorted(items, key=lambda item: (item["y"], item["x"]))
    lines: list[dict] = []
    for item in items:
        center = (item["y"] + item["y2"]) / 2
        if lines and abs(center - lines[-1]["cy"]) <= tolerance:
            lines[-1]["items"].append(item)
            centers = [(entry["y"] + entry["y2"]) / 2 for entry in lines[-1]["items"]]
            lines[-1]["cy"] = sum(centers) / len(centers)
        else:
            lines.append({"cy": center, "items": [item]})
    for line in lines:
        line["items"].sort(key=lambda entry: entry["x"])
        line["text"] = _clean(" ".join(entry["text"] for entry in line["items"]))
    return lines


def _label_indexes(lines: list[dict]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, line in enumerate(lines):
        for name, pattern in _LABELS:
            if name in found:
                continue
            if _line_has_label(line, pattern):
                found[name] = index
    return found


def _line_has_label(line: dict, pattern: re.Pattern[str]) -> bool:
    if pattern.search(line["text"]):
        return True
    return any(pattern.search(item["text"]) for item in line["items"])


def _section_value(
    lines: list[dict],
    indexes: dict[str, int],
    start_label: str,
    end_label: str,
    kind: str,
) -> str:
    start = indexes.get(start_label)
    if start is None:
        return ""
    end = _next_index(indexes, start, end_label)
    pattern = dict(_LABELS)[start_label]
    same_line = _value_beside_label(lines[start], pattern)
    if kind == "name" and _looks_like_name(same_line):
        return same_line
    for line in lines[start + 1 : end]:
        if _looks_like_name(line["text"], strict_caps=True):
            return line["text"]
    return same_line if _looks_like_name(same_line) else ""


def _transaction_id(lines: list[dict], indexes: dict[str, int]) -> str:
    start = indexes.get("transaction_id")
    if start is None:
        return ""
    pattern = dict(_LABELS)["transaction_id"]
    candidates = [_value_beside_label(lines[start], pattern), lines[start]["text"]]
    end = _next_index(indexes, start, "session_id")
    if start + 1 < end:
        candidates.append(lines[start + 1]["text"])
    for candidate in candidates:
        token = _id_token(candidate)
        if token:
            return token
    return ""


def _account_digits(lines: list[dict], indexes: dict[str, int]) -> str:
    start = indexes.get("recipient")
    if start is None:
        return ""
    end = _next_index(indexes, start, "sender")
    # The account sits under the recipient name, above the sender.
    for line in lines[start : end]:
        if _line_has_label(line, dict(_LABELS)["recipient"]) and "*" in line["text"]:
            continue
        parsed = _parse_account(line["text"])
        if parsed:
            return parsed
    return ""


def _parse_account(text: str) -> str:
    raw = (
        text.replace("│", "|")
        .replace("ǀ", "|")
        .replace("∣", "|")
        .replace("¦", "|")
    )
    raw = _clean(raw)
    if "*" in raw or not raw:
        return ""
    match = _ACCOUNT_RE.match(raw) or _ACCOUNT_LOOSE_RE.match(raw)
    if not match:
        return ""
    bank = match.group("bank")
    if not re.search(r"[A-Za-z]", bank):
        return ""
    digits = re.sub(r"\D", "", match.group("acct"))
    if len(digits) not in (10, 11):
        return ""
    return digits


def _next_index(indexes: dict[str, int], start: int, preferred: str) -> int:
    candidates = [index for index in indexes.values() if index > start]
    if preferred in indexes and indexes[preferred] > start:
        return indexes[preferred]
    return min(candidates) if candidates else 10**9


def _value_beside_label(line: dict, pattern: re.Pattern[str]) -> str:
    values = [item["text"] for item in line["items"] if not pattern.search(item["text"])]
    if values:
        return _clean(" ".join(values))
    match = re.search(r":\s*(.+)$", line["text"])
    if match:
        return _clean(match.group(1))
    stripped = pattern.sub("", line["text"], count=1)
    stripped = re.sub(r"^[\s:.\-]+", "", stripped)
    return _clean(stripped)


def _looks_like_name(text: str, strict_caps: bool = False) -> bool:
    if not text or "*" in text or "|" in text:
        return False
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 3 or any(char.isdigit() for char in text):
        return False
    if not strict_caps:
        return True
    uppercase = sum(1 for char in letters if char.isupper())
    return uppercase / len(letters) >= 0.7


def _id_token(text: str) -> str:
    if not text:
        return ""
    without_label = re.sub(r"transaction\s*id", "", text, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", "", without_label)
    if re.fullmatch(r"[A-Za-z0-9]{6,40}", compact):
        return compact
    for token in re.findall(r"[A-Za-z0-9]{6,40}", without_label):
        if re.search(r"[A-Za-z]", token) and re.search(r"\d", token):
            return token
    return ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
