"""Desktop window for turning receipt screenshots into a CSV."""

from __future__ import annotations

import platform
import queue
import subprocess
import sys
import threading
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path
from urllib.parse import unquote, urlparse

import customtkinter as ctk

from csv_export import save_rows
from extractor import CSV_COLUMNS, ReceiptExtractor, ReceiptRow

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_READY = True
except Exception:  # noqa: BLE001
    DND_FILES = None
    TkinterDnD = None
    _DND_READY = False

BG = "#F4F6FB"
CARD = "#FFFFFF"
INK = "#16181D"
MUTED = "#5C6575"
LINE = "#E6E9F0"
ACCENT = "#5B35F2"
ACCENT_HOVER = "#4726D4"
SOFT = "#F3F0FF"
SOFT_BORDER = "#DDD6FE"
WARN = "#B45309"
FIELD_BG = "#F8F9FC"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
EDITABLE = [key for key, _title in CSV_COLUMNS if key != "source_file"]


def run() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()


class App(ctk.CTk, *(() if not _DND_READY else (TkinterDnD.DnDWrapper,))):
    def __init__(self) -> None:
        super().__init__()
        if _DND_READY:
            self.TkdndVersion = TkinterDnD._require(self)

        self.title("Receipt Extractor")
        self.configure(fg_color=BG)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1180, max(760, screen_w - 60))
        height = min(900, max(520, screen_h - 100))
        self.geometry(f"{width}x{height}")
        self.minsize(min(640, screen_w - 20), min(420, screen_h - 80))
        self._narrow = False

        self.extractor = ReceiptExtractor()
        self.files: list[Path] = []
        self.rows: list[ReceiptRow] = []
        self.row_widgets: list[_ResultRow] = []
        self.file_widgets: dict[Path, ctk.CTkFrame] = {}
        self.events: queue.Queue = queue.Queue()
        self.working = False
        self._polling = False

        documents = Path.home() / "Documents"
        folder = documents if documents.is_dir() else Path.home()
        self.output_path = ctk.StringVar(value=str(folder / "receipts.csv"))
        self.mode = "new"

        self._build()
        self._refresh_actions()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.page = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self.page.grid(row=0, column=0, sticky="nsew")
        self.page.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.page, fg_color=BG)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        ctk.CTkLabel(
            header,
            text="Receipt Extractor",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=INK,
            anchor="w",
        ).pack(anchor="w")
        self.subtitle = ctk.CTkLabel(
            header,
            text=(
                "Upload one or many PalmPay receipts. The app reads the transaction ID, "
                "recipient name, and sender name. The recipient number is the account "
                "after the bank name, with a 0 added in front (7077177416 becomes 07077177416)."
            ),
            font=ctk.CTkFont(size=13),
            text_color=MUTED,
            wraplength=720,
            justify="left",
            anchor="w",
        )
        self.subtitle.pack(anchor="w", pady=(4, 0))

        self.body = ctk.CTkFrame(self.page, fg_color=BG)
        self.body.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        self.body.grid_columnconfigure(0, weight=3)
        self.body.grid_columnconfigure(1, weight=2)

        self._build_uploads(self.body)
        self._build_output(self.body)
        self._build_results()
        self.bind("<Configure>", self._on_window_resize, add="+")

    def _build_uploads(self, parent) -> None:
        card = _card(parent)
        self.uploads_card = card
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="Uploads",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=INK,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.drop = ctk.CTkFrame(
            card,
            fg_color=SOFT,
            corner_radius=14,
            border_width=1,
            border_color=SOFT_BORDER,
        )
        self.drop.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        ctk.CTkLabel(
            self.drop,
            text="Drop receipt images here",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=INK,
        ).pack(pady=(16, 2))
        self.drop_hint = ctk.CTkLabel(
            self.drop,
            text="PNG, JPG, or WEBP. You can add more at any time.",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.drop_hint.pack(pady=(0, 10))
        ctk.CTkButton(
            self.drop,
            text="Add images",
            command=self.add_images,
            height=36,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=10,
        ).pack(pady=(0, 16))

        self.file_list = _NestedScroll(card, fg_color=CARD, corner_radius=0, height=168)
        self.file_list.page_scroll = self.page
        self.file_list.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self.empty_files = ctk.CTkLabel(
            self.file_list,
            text="No images yet.",
            text_color=MUTED,
            font=ctk.CTkFont(size=13),
        )
        self.empty_files.pack(anchor="w", padx=8, pady=8)

        actions = ctk.CTkFrame(card, fg_color=CARD)
        actions.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.clear_files_button = ctk.CTkButton(
            actions,
            text="Clear images",
            command=self.clear_files,
            fg_color="#EEF0F6",
            hover_color="#E2E5EF",
            text_color=INK,
            height=32,
            corner_radius=10,
        )
        self.clear_files_button.pack(side="left")
        self.file_count = ctk.CTkLabel(actions, text="", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.file_count.pack(side="right")

        self._register_drop(self.drop)
        self._register_drop(self.file_list)
        self._register_drop(self)

    def _build_output(self, parent) -> None:
        card = _card(parent)
        self.output_card = card
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="CSV file",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=INK,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.mode_switch = ctk.CTkSegmentedButton(
            card,
            values=["New file", "Add to same file"],
            command=self._set_mode,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color="#EEF0F6",
            unselected_hover_color="#E2E5EF",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.mode_switch.set("New file")
        self.mode_switch.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.mode_hint = ctk.CTkLabel(
            card,
            text="Save creates a new CSV and replaces that file if it already exists.",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
            wraplength=340,
            justify="left",
            anchor="w",
        )
        self.mode_hint.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        path_row = ctk.CTkFrame(card, fg_color=CARD)
        path_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        path_row.grid_columnconfigure(0, weight=1)
        self.path_entry = ctk.CTkEntry(
            path_row,
            textvariable=self.output_path,
            height=36,
            corner_radius=10,
            border_color=LINE,
            fg_color=FIELD_BG,
            text_color=INK,
        )
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            path_row,
            text="Browse",
            width=88,
            height=36,
            command=self.browse_output,
            fg_color="#EEF0F6",
            hover_color="#E2E5EF",
            text_color=INK,
            corner_radius=10,
        ).grid(row=0, column=1)

        self.extract_button = ctk.CTkButton(
            card,
            text="Extract receipts",
            command=self.extract,
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=12,
        )
        self.extract_button.grid(row=4, column=0, sticky="ew", padx=16, pady=(12, 8))

        self.progress = ctk.CTkProgressBar(card, height=8, progress_color=ACCENT)
        self.progress.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 4))
        self.progress.set(0)
        self.progress.grid_remove()

        self.progress_label = ctk.CTkLabel(
            card,
            text="Add images, then extract. You can correct the table before saving.",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
            wraplength=340,
            justify="left",
            anchor="w",
        )
        self.progress_label.grid(row=6, column=0, sticky="ew", padx=16, pady=(4, 14))

    def _build_results(self) -> None:
        card = _card(self.page)
        card.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 20))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(card, fg_color=CARD)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        ctk.CTkLabel(
            top,
            text="Results",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=INK,
        ).pack(side="left")
        self.result_count = ctk.CTkLabel(top, text="", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.result_count.pack(side="left", padx=(10, 0))

        self.results_x = ctk.CTkScrollableFrame(
            card,
            orientation="horizontal",
            fg_color=CARD,
            corner_radius=0,
            height=300,
        )
        self.results_x.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        self.results = _NestedScroll(self.results_x, fg_color=CARD, corner_radius=0, height=270, width=980)
        self.results.page_scroll = self.page
        self.results.pack(anchor="nw")
        self.header = ctk.CTkFrame(self.results, fg_color="#F8F9FC", corner_radius=10)
        self.header.pack(fill="x", padx=4, pady=(0, 4))
        _layout_columns(self.header)
        for index, (_key, title) in enumerate(CSV_COLUMNS):
            ctk.CTkLabel(
                self.header,
                text=title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=MUTED,
                anchor="w",
            ).grid(row=0, column=index, sticky="ew", padx=6, pady=8)
        ctk.CTkLabel(self.header, text="", width=40).grid(row=0, column=len(CSV_COLUMNS), padx=(0, 6))
        self.empty_results = ctk.CTkLabel(
            self.results,
            text="Extracted rows show up here. Edit any cell, then save.",
            text_color=MUTED,
            font=ctk.CTkFont(size=13),
        )
        self.empty_results.pack(anchor="w", padx=8, pady=12)

        footer = ctk.CTkFrame(card, fg_color=CARD)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.clear_results_button = ctk.CTkButton(
            footer,
            text="Clear results",
            command=self.clear_results,
            fg_color="#EEF0F6",
            hover_color="#E2E5EF",
            text_color=INK,
            height=36,
            corner_radius=10,
        )
        self.clear_results_button.pack(side="left")
        self.open_button = ctk.CTkButton(
            footer,
            text="Open folder",
            command=self.open_output_folder,
            fg_color="#EEF0F6",
            hover_color="#E2E5EF",
            text_color=INK,
            height=36,
            corner_radius=10,
        )
        self.open_button.pack(side="left", padx=(8, 0))
        self.save_button = ctk.CTkButton(
            footer,
            text="Save CSV",
            command=self.save,
            height=36,
            width=140,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=10,
        )
        self.save_button.pack(side="right")

    def _on_window_resize(self, event) -> None:
        if event.widget is not self:
            return
        self.subtitle.configure(wraplength=max(280, event.width - 72))
        hint_width = max(220, event.width - 80) if event.width < 900 else max(220, int((event.width - 90) * 0.36))
        self.mode_hint.configure(wraplength=hint_width)
        self.progress_label.configure(wraplength=hint_width)
        narrow = event.width < 900
        if narrow == self._narrow:
            return
        self._narrow = narrow
        if narrow:
            self.uploads_card.grid_configure(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 10))
            self.output_card.grid_configure(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        else:
            self.uploads_card.grid_configure(row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 8), pady=0)
            self.output_card.grid_configure(row=0, column=1, columnspan=1, sticky="nsew", padx=(8, 0), pady=0)

    def _register_drop(self, widget) -> None:
        if not _DND_READY:
            self.drop_hint.configure(text="PNG, JPG, or WEBP. Use Add images to choose several files.")
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DropEnter>>", lambda _event: self.drop.configure(fg_color="#E9E4FF"))
            widget.dnd_bind("<<DropLeave>>", lambda _event: self.drop.configure(fg_color=SOFT))
        except Exception:
            pass

    def _set_mode(self, value: str) -> None:
        self.mode = "append" if value == "Add to same file" else "new"
        if self.mode == "append":
            self.mode_hint.configure(
                text="Save adds these rows to the bottom of the CSV. Receipt numbers already in the file are skipped."
            )
        else:
            self.mode_hint.configure(
                text="Save creates a new CSV and replaces that file if it already exists."
            )

    def add_images(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Choose receipt images",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        self._add_paths(list(selected))

    def _on_drop(self, event) -> None:
        self.drop.configure(fg_color=SOFT)
        try:
            raw_paths = self.tk.splitlist(event.data)
        except Exception:
            raw_paths = [event.data]
        self._add_paths([_drop_path(item) for item in raw_paths])

    def _add_paths(self, paths: list[str]) -> None:
        added = 0
        skipped = 0
        known = {path.resolve() for path in self.files}
        for raw in paths:
            if not raw:
                continue
            path = Path(raw).expanduser()
            if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
                skipped += 1
                continue
            resolved = path.resolve()
            if resolved in known:
                continue
            known.add(resolved)
            self.files.append(path)
            self._add_file_row(path)
            added += 1
        if added:
            self.empty_files.pack_forget()
        if skipped:
            self.progress_label.configure(
                text=f"Skipped {skipped} item{'s' if skipped != 1 else ''} that {'are' if skipped != 1 else 'is'} not an image."
            )
        self._refresh_actions()

    def _add_file_row(self, path: Path) -> None:
        row = ctk.CTkFrame(self.file_list, fg_color=FIELD_BG, corner_radius=10)
        row.pack(fill="x", padx=4, pady=3)
        ctk.CTkLabel(
            row,
            text=path.name,
            text_color=INK,
            anchor="w",
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=10, pady=8, fill="x", expand=True)
        ctk.CTkButton(
            row,
            text="Remove",
            width=72,
            height=28,
            command=lambda current=path: self.remove_file(current),
            fg_color=CARD,
            hover_color="#E7E9F0",
            text_color=MUTED,
            corner_radius=8,
        ).pack(side="right", padx=8, pady=6)
        self.file_widgets[path] = row

    def remove_file(self, path: Path) -> None:
        if path in self.files:
            self.files.remove(path)
        widget = self.file_widgets.pop(path, None)
        if widget is not None:
            widget.destroy()
        if not self.files:
            self.empty_files.pack(anchor="w", padx=8, pady=8)
        self._refresh_actions()

    def clear_files(self) -> None:
        for widget in self.file_widgets.values():
            widget.destroy()
        self.file_widgets.clear()
        self.files.clear()
        self.empty_files.pack(anchor="w", padx=8, pady=8)
        self._refresh_actions()

    def extract(self) -> None:
        if self.working or not self.files:
            return
        self.working = True
        self._refresh_actions()
        self.progress.grid()
        self.progress.set(0)
        self.progress_label.configure(text="Preparing text recognition…")
        paths = [str(path) for path in self.files]
        threading.Thread(target=self._extract_worker, args=(paths,), daemon=True).start()
        if not self._polling:
            self._polling = True
            self.after(80, self._poll)

    def _extract_worker(self, paths: list[str]) -> None:
        total = len(paths)
        try:
            for index, path in enumerate(paths, start=1):
                self.events.put(("progress", index, total, Path(path).name))
                row = self.extractor.extract(path)
                self.events.put(("row", row))
            self.events.put(("done", total))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("failed", str(exc)))

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _index, total, name = event[1], event[2], event[3]
                    self.progress.set(_index / total)
                    self.progress_label.configure(text=f"Reading {_index} of {total} — {name}")
                elif kind == "row":
                    self._upsert_row(event[1])
                elif kind == "done":
                    self.working = False
                    self.progress.set(1)
                    count = len(self.rows)
                    self.progress_label.configure(
                        text=f"Finished {event[1]} image{'s' if event[1] != 1 else ''}. {count} row{'s' if count != 1 else ''} ready to review."
                    )
                    self._refresh_actions()
                    self._polling = False
                    return
                elif kind == "failed":
                    self.working = False
                    self.progress_label.configure(text="Extraction stopped.")
                    messagebox.showerror("Could not read receipts", event[1])
                    self._refresh_actions()
                    self._polling = False
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _upsert_row(self, row: ReceiptRow) -> None:
        for index, existing in enumerate(self.rows):
            if existing.source_path == row.source_path:
                self.rows[index] = row
                self.row_widgets[index].load(row)
                self._refresh_actions()
                return
        self.rows.append(row)
        widget = _ResultRow(self.results, row, self._remove_result, self._refresh_actions)
        widget.pack(fill="x", padx=4, pady=3)
        self.row_widgets.append(widget)
        self.empty_results.pack_forget()
        self._refresh_actions()

    def _remove_result(self, widget: _ResultRow) -> None:
        if widget.row in self.rows:
            index = self.rows.index(widget.row)
            self.rows.pop(index)
            self.row_widgets.pop(index)
        widget.destroy()
        if not self.rows:
            self.empty_results.pack(anchor="w", padx=8, pady=12)
        self._refresh_actions()

    def clear_results(self) -> None:
        if self.rows and not messagebox.askyesno(
            "Clear results",
            "Remove every extracted row from the table? The CSV file is not changed.",
        ):
            return
        for widget in self.row_widgets:
            widget.destroy()
        self.row_widgets.clear()
        self.rows.clear()
        self.empty_results.pack(anchor="w", padx=8, pady=12)
        self._refresh_actions()

    def browse_output(self) -> None:
        current = self.output_path.get().strip()
        initial = str(Path(current).parent) if current else str(Path.home())
        if self.mode == "append":
            chosen = filedialog.askopenfilename(
                title="Choose the CSV to add to",
                initialdir=initial,
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
        else:
            chosen = filedialog.asksaveasfilename(
                title="Save CSV as",
                initialdir=initial,
                initialfile=Path(current).name if current else "receipts.csv",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
            )
        if chosen:
            self.output_path.set(chosen)

    def save(self) -> None:
        if not self.rows:
            return
        self._pull_edits()
        destination = Path(self.output_path.get().strip()).expanduser()
        if not str(destination):
            messagebox.showwarning("Choose a file", "Pick where the CSV should be saved.")
            return
        if destination.suffix.lower() != ".csv":
            destination = destination.with_suffix(".csv")
            self.output_path.set(str(destination))

        incomplete = sum(1 for row in self.rows if row.missing_fields or row.error)
        if incomplete and not messagebox.askyesno(
            "Some rows are incomplete",
            f"{incomplete} row{'s are' if incomplete != 1 else ' is'} missing a field or could not be read fully. Save anyway?",
        ):
            return

        if self.mode == "new" and destination.exists() and destination.stat().st_size > 0:
            if not messagebox.askyesno(
                "Replace file",
                f"{destination.name} already exists. Replace it with these rows?",
            ):
                return

        try:
            summary = save_rows(destination, self.rows, self.mode)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save", str(exc))
            return

        written = summary["written"]
        skipped = summary["skipped"]
        detail = f"Saved {written} row{'s' if written != 1 else ''} to\n{destination}"
        if skipped:
            detail += f"\n\nSkipped {skipped} receipt number{'s' if skipped != 1 else ''} already in the file."
        self.progress_label.configure(text=detail.replace("\n\n", " ").replace("\n", " "))
        messagebox.showinfo("CSV saved", detail)

    def open_output_folder(self) -> None:
        raw = self.output_path.get().strip()
        if not raw:
            return
        folder = Path(raw).expanduser()
        folder = folder.parent if folder.suffix else folder
        if not folder.exists():
            messagebox.showwarning("Folder not found", f"{folder} does not exist yet.")
            return
        system = platform.system()
        try:
            if system == "Windows":
                import os

                os.startfile(folder)  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.run(["open", str(folder)], check=False)
            else:
                subprocess.run(["xdg-open", str(folder)], check=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open folder", str(exc))

    def _pull_edits(self) -> None:
        for widget in self.row_widgets:
            widget.write_back()

    def _refresh_actions(self) -> None:
        file_total = len(self.files)
        self.file_count.configure(
            text=f"{file_total} image{'s' if file_total != 1 else ''}" if file_total else ""
        )
        row_total = len(self.rows)
        needs_edit = sum(1 for row in self._current_rows() if row.missing_fields or row.error)
        if row_total:
            note = f"{row_total} row{'s' if row_total != 1 else ''}"
            if needs_edit:
                note += f" · {needs_edit} to check"
            self.result_count.configure(text=note)
        else:
            self.result_count.configure(text="")

        self.extract_button.configure(
            state="disabled" if self.working or not self.files else "normal",
            text="Extracting…" if self.working else "Extract receipts",
        )
        self.save_button.configure(state="disabled" if self.working or not self.rows else "normal")
        self.clear_files_button.configure(state="disabled" if self.working or not self.files else "normal")
        self.clear_results_button.configure(state="disabled" if self.working or not self.rows else "normal")

    def _current_rows(self) -> list[ReceiptRow]:
        if self.row_widgets:
            for widget in self.row_widgets:
                widget.write_back()
        return self.rows


class _ResultRow(ctk.CTkFrame):
    def __init__(self, master, row: ReceiptRow, on_remove, on_change) -> None:
        super().__init__(master, fg_color=FIELD_BG, corner_radius=10)
        self.row = row
        self.on_remove = on_remove
        self.on_change = on_change
        self.entries: dict[str, ctk.CTkEntry] = {}
        _layout_columns(self)

        for index, (key, _title) in enumerate(CSV_COLUMNS):
            if key == "source_file":
                ctk.CTkLabel(
                    self,
                    text=row.source_file,
                    anchor="w",
                    text_color=MUTED,
                    font=ctk.CTkFont(size=12),
                ).grid(row=0, column=index, sticky="ew", padx=6, pady=8)
                continue
            entry = ctk.CTkEntry(
                self,
                height=32,
                corner_radius=8,
                border_width=1,
                fg_color=CARD,
                text_color=INK,
                border_color=LINE,
            )
            entry.grid(row=0, column=index, sticky="ew", padx=6, pady=8)
            entry.bind("<KeyRelease>", lambda _event: self._changed())
            self.entries[key] = entry

        ctk.CTkButton(
            self,
            text="×",
            width=32,
            height=32,
            command=lambda: self.on_remove(self),
            fg_color="transparent",
            hover_color="#E7E9F0",
            text_color=MUTED,
            corner_radius=8,
        ).grid(row=0, column=len(CSV_COLUMNS), padx=(0, 6))

        self.note = ctk.CTkLabel(
            self,
            text="",
            text_color=WARN,
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.load(row)

    def load(self, row: ReceiptRow) -> None:
        self.row = row
        for key, entry in self.entries.items():
            entry.delete(0, "end")
            entry.insert(0, getattr(row, key))
        self._paint()

    def write_back(self) -> None:
        for key, entry in self.entries.items():
            setattr(self.row, key, entry.get().strip())

    def _changed(self) -> None:
        self.write_back()
        self._paint()
        self.on_change()

    def _paint(self) -> None:
        for key, entry in self.entries.items():
            value = entry.get().strip()
            warn = not value
            if key == "recipient_number" and value and not value.startswith("0"):
                warn = True
            entry.configure(border_color="#F5C16C" if warn else LINE)
        if self.row.missing_fields and self.row.error:
            self.note.configure(text=self.row.error, text_color=WARN)
            self.note.grid(row=1, column=0, columnspan=5, sticky="ew", padx=8, pady=(0, 8))
        else:
            self.note.grid_remove()


class _NestedScroll(ctk.CTkScrollableFrame):
    """A list inside the page. If the list already fits, the wheel scrolls the page."""

    page_scroll: ctk.CTkScrollableFrame | None = None

    def _mouse_wheel_all(self, event) -> None:
        if not self._check_if_valid_scroll(event.widget):
            return
        if self._parent_canvas.yview() == (0.0, 1.0) and self.page_scroll is not None:
            _scroll_canvas(self.page_scroll._parent_canvas, event)
            return
        super()._mouse_wheel_all(event)


def _layout_columns(frame) -> None:
    minimums = [160, 220, 220, 150, 140]
    for index, minsize in enumerate(minimums):
        frame.grid_columnconfigure(index, weight=minsize, minsize=minsize)
    frame.grid_columnconfigure(len(minimums), weight=0, minsize=40)


def _scroll_canvas(canvas, event) -> None:
    if canvas.yview() == (0.0, 1.0):
        return
    if sys.platform.startswith("win"):
        canvas.yview_scroll(-int(event.delta / 6), "units")
    elif sys.platform == "darwin":
        canvas.yview_scroll(-int(event.delta), "units")
    else:
        canvas.yview_scroll(-1 if getattr(event, "num", 5) == 4 else 1, "units")


def _card(parent) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent,
        fg_color=CARD,
        corner_radius=16,
        border_width=1,
        border_color=LINE,
    )


def _drop_path(value: str) -> str:
    text = str(value).strip()
    if not text.startswith("file:"):
        return text
    parsed = urlparse(text)
    path = unquote(parsed.path)
    if platform.system() == "Windows" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return path
