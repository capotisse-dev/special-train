# app/ui_operator.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from .ui_common import HeaderFrame
from .storage import safe_int, safe_float
from .db import (
    list_downtime_codes,
    list_lines,
    list_parts_for_line,
    list_parts_with_lines,
    list_cells_for_line,
    list_machines_for_cell,
    upsert_tool_entry,
    replace_shift_downtime_entries,
)
from .audit import log_audit


class OperatorUI(tk.Frame):
    """Operator entry screen for cell/parts and downtime capture."""

    def __init__(self, parent, controller, show_header=True):
        super().__init__(parent, bg=controller.colors["bg"])
        self.controller = controller

        if show_header:
            HeaderFrame(self, controller).pack(fill="x")

        body = tk.Frame(self, bg=self.controller.colors["bg"], padx=20, pady=20)
        body.pack(fill="both", expand=True)

        self._build_shift_production(body)

    def _toggle_downtime_fields(self, event=None):
        enabled = bool(self.downtime_var.get())
        state = "normal" if enabled else "disabled"
        for entry in (self.dt_total_entry, self.dt_occ_entry, self.dt_comment_entry):
            entry.configure(state=state)
            if not enabled:
                entry.delete(0, "end")

    def _build_shift_production(self, body):
        style = {"bg": self.controller.colors["bg"], "fg": self.controller.colors["fg"]}

        tk.Label(body, text="Shift Production", font=("Arial", 16, "bold"), **style).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 15)
        )

        tk.Label(body, text="Line:", **style).grid(row=1, column=0, sticky="e", pady=6)
        line_options = list_lines()
        if not line_options:
            line_options = ["U725", "JL"]
        self.shift_line_var = tk.StringVar(value=self.controller.user_line or line_options[0])
        self.shift_line_cb = ttk.Combobox(body, values=line_options, state="readonly", width=18)
        if self.shift_line_var.get() in line_options:
            self.shift_line_cb.set(self.shift_line_var.get())
        else:
            self.shift_line_cb.current(0)
        self.shift_line_cb.grid(row=1, column=1, sticky="w")
        self.shift_line_cb.bind("<<ComboboxSelected>>", self._refresh_line_dependent_fields)

        tk.Label(body, text="Shift:", **style).grid(row=1, column=2, sticky="e", pady=6)
        self.shift_var = tk.StringVar(value="1st")
        self.shift_cb = ttk.Combobox(body, values=["1st", "2nd", "3rd"], state="readonly", width=18)
        self.shift_cb.set(self.shift_var.get())
        self.shift_cb.grid(row=1, column=3, sticky="w")

        tk.Label(body, text="Cell:", **style).grid(row=2, column=0, sticky="e", pady=6)
        self.cell_var = tk.StringVar(value="")
        self.cell_cb = ttk.Combobox(body, values=[], state="readonly", width=18, textvariable=self.cell_var)
        self.cell_cb.grid(row=2, column=1, sticky="w")
        self.cell_cb.bind("<<ComboboxSelected>>", self._refresh_machine_options)

        tk.Label(body, text="Machine:", **style).grid(row=2, column=2, sticky="e", pady=6)
        self.machine_var = tk.StringVar(value="")
        self.machine_cb = ttk.Combobox(body, values=[], state="readonly", width=18, textvariable=self.machine_var)
        self.machine_cb.grid(row=2, column=3, sticky="w")

        tk.Label(body, text="Part Number:", **style).grid(row=3, column=0, sticky="e", pady=6)
        self.part_var = tk.StringVar(value="")
        self.part_cb = ttk.Combobox(body, values=[], state="readonly", width=24, textvariable=self.part_var)
        self.part_cb.grid(row=3, column=1, sticky="w")

        tk.Label(body, text="Production Qty:", **style).grid(row=3, column=2, sticky="e", pady=6)
        self.shift_qty_entry = tk.Entry(body, width=18)
        self.shift_qty_entry.grid(row=3, column=3, sticky="w")

        tk.Label(body, text="Downtime Code:", **style).grid(row=4, column=0, sticky="e", pady=6)
        self.downtime_var = tk.StringVar(value="")
        codes = list_downtime_codes()
        self.downtime_options = []
        self.downtime_map = {}
        for row in codes:
            code = row.get("code", "")
            desc = row.get("description", "")
            display = f"{code} - {desc}" if desc else code
            self.downtime_options.append(display)
            self.downtime_map[display] = code
        self.downtime_cb = ttk.Combobox(
            body,
            values=self.downtime_options,
            textvariable=self.downtime_var,
            state="readonly",
            width=32,
        )
        self.downtime_cb.grid(row=4, column=1, sticky="w")
        self.downtime_cb.bind("<<ComboboxSelected>>", self._toggle_downtime_fields)

        self.downtime_frame = tk.Frame(body, bg=self.controller.colors["bg"])
        self.downtime_frame.grid(row=4, column=2, columnspan=2, sticky="w", padx=20)

        tk.Label(self.downtime_frame, text="Total Time (min):", **style).grid(row=0, column=0, sticky="w")
        self.dt_total_entry = tk.Entry(self.downtime_frame, width=10)
        self.dt_total_entry.grid(row=0, column=1, padx=(6, 12))

        tk.Label(self.downtime_frame, text="# Occurrences:", **style).grid(row=0, column=2, sticky="w")
        self.dt_occ_entry = tk.Entry(self.downtime_frame, width=10)
        self.dt_occ_entry.grid(row=0, column=3, padx=(6, 12))

        tk.Label(self.downtime_frame, text="Comments:", **style).grid(row=0, column=4, sticky="w")
        self.dt_comment_entry = tk.Entry(self.downtime_frame, width=28)
        self.dt_comment_entry.grid(row=0, column=5, padx=(6, 0))

        tk.Button(
            self.downtime_frame,
            text="Add Downtime",
            command=self.add_downtime_entry,
            bg="#17a2b8",
            fg="white",
        ).grid(row=0, column=6, padx=(12, 0))

        tk.Button(
            self.downtime_frame,
            text="Remove Selected",
            command=self.remove_downtime_entry,
            bg="#dc3545",
            fg="white",
        ).grid(row=0, column=7, padx=(8, 0))

        self.downtime_tree = ttk.Treeview(
            body,
            columns=("code", "minutes", "occurrences", "comments"),
            show="headings",
            height=6,
        )
        for col, width in (
            ("code", 160),
            ("minutes", 100),
            ("occurrences", 110),
            ("comments", 240),
        ):
            self.downtime_tree.heading(col, text=col.upper())
            self.downtime_tree.column(col, width=width)
        self.downtime_tree.grid(row=5, column=0, columnspan=4, sticky="we", pady=(6, 10))

        self._toggle_downtime_fields()
        self._refresh_line_dependent_fields()

        tk.Button(
            body,
            text="Submit Shift Report",
            command=self.submit_shift_report,
            bg="#28a745",
            fg="white",
            font=("Arial", 12, "bold"),
            width=20,
        ).grid(row=6, column=0, columnspan=4, pady=20, sticky="w")

    def add_downtime_entry(self):
        downtime_display = self.downtime_var.get().strip()
        downtime_code = self.downtime_map.get(downtime_display, "")
        if not downtime_code:
            messagebox.showerror("Missing Info", "Select a downtime code.")
            return
        minutes = safe_float(self.dt_total_entry.get(), 0.0)
        if minutes <= 0:
            messagebox.showerror("Missing Info", "Enter downtime minutes.")
            return
        occurrences = safe_int(self.dt_occ_entry.get(), 0)
        comments = self.dt_comment_entry.get().strip()

        self.downtime_tree.insert(
            "",
            "end",
            values=(
                downtime_code,
                f"{minutes:.1f}",
                str(occurrences),
                comments,
            ),
        )
        self.downtime_var.set("")
        self._toggle_downtime_fields()

    def remove_downtime_entry(self):
        sel = self.downtime_tree.selection()
        if not sel:
            return
        for item in sel:
            self.downtime_tree.delete(item)

    def _collect_downtime_entries(self):
        entries = []
        for item in self.downtime_tree.get_children():
            code, minutes, occurrences, comments = self.downtime_tree.item(item, "values")
            entries.append({
                "code": code,
                "downtime_mins": safe_float(minutes, 0.0),
                "occurrences": safe_int(occurrences, 0),
                "comments": comments,
            })
        return entries

    def _refresh_line_dependent_fields(self, event=None):
        line = self.shift_line_cb.get().strip()
        parts = list_parts_for_line(line)
        if not parts:
            parts = [p.get("part_number", "") for p in list_parts_with_lines()]
        self.part_cb.configure(values=parts)
        if parts:
            self.part_cb.set(parts[0])
        else:
            self.part_cb.set("")

        cells = list_cells_for_line(line)
        self.cell_cb.configure(values=cells)
        if cells:
            self.cell_cb.set(cells[0])
        else:
            self.cell_cb.set("")
        self._refresh_machine_options()

    def _refresh_machine_options(self, event=None):
        line = self.shift_line_cb.get().strip()
        cell = self.cell_cb.get().strip()
        machines = list_machines_for_cell(line, cell)
        self.machine_cb.configure(values=machines)
        if machines:
            self.machine_cb.set(machines[0])
        else:
            self.machine_cb.set("")

    def submit_shift_report(self):
        line = self.shift_line_cb.get().strip()
        cell = self.cell_cb.get().strip()
        part_number = self.part_cb.get().strip()
        qty = safe_int(self.shift_qty_entry.get(), 0)
        downtime_entries = self._collect_downtime_entries()
        if not line:
            messagebox.showerror("Missing Info", "Select a line.")
            return
        if not cell:
            messagebox.showerror("Missing Info", "Select a cell.")
            return
        if not part_number:
            messagebox.showerror("Missing Info", "Select a part number.")
            return
        if qty <= 0:
            messagebox.showerror("Missing Info", "Enter the production quantity.")
            return

        dt_total = sum(item["downtime_mins"] for item in downtime_entries)

        now = datetime.now()
        entry_id = f"SP-{now.strftime('%Y%m%d-%H%M%S')}"
        new_row = {
            "ID": entry_id,
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
            "Shift": self.shift_cb.get(),
            "Line": line,
            "Cell": cell,
            "Machine": self.machine_cb.get().strip(),
            "Part_Number": part_number,
            "Tool_Num": "",
            "Reason": "Shift Production",
            "Downtime_Mins": dt_total,
            "Downtime_Code": "",
            "Downtime_Occurrences": 0,
            "Downtime_Comments": "",
            "Production_Qty": float(qty),
            "Cost": 0.0,
            "Tool_Life": 0.0,
            "Tool_Changer": self.controller.user or "",
            "Defects_Present": "No",
            "Defect_Qty": 0,
            "Sort_Done": "No",
            "Defect_Reason": "",
            "Quality_Verified": "N/A",
            "Quality_User": "",
            "Quality_Time": "",
            "Leader_Sign": "Pending",
            "Leader_User": "",
            "Leader_Time": "",
            "Serial_Numbers": "",
        }
        upsert_tool_entry(new_row)
        replace_shift_downtime_entries(entry_id, downtime_entries)
        log_audit(self.controller.user, f"Shift production entry {entry_id} saved")

        messagebox.showinfo("Saved", "Shift production report submitted for leader signoff.")
        self.shift_qty_entry.delete(0, "end")
        self.downtime_var.set("")
        self._toggle_downtime_fields()
        for item in self.downtime_tree.get_children():
            self.downtime_tree.delete(item)
