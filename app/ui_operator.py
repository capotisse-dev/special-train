# app/ui_operator.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from .ui_common import HeaderFrame
from .storage import safe_int, safe_float
from .db import list_downtime_codes, list_lines, upsert_operator_entry, upsert_tool_entry
from .audit import log_audit


class OperatorUI(tk.Frame):
    """Operator entry screen for cell/parts and downtime capture."""

    def __init__(self, parent, controller, show_header=True):
        super().__init__(parent, bg=controller.colors["bg"])
        self.controller = controller

        if show_header:
            HeaderFrame(self, controller).pack(fill="x")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        tab_operator = tk.Frame(nb, bg=controller.colors["bg"])
        tab_shift = tk.Frame(nb, bg=controller.colors["bg"])
        nb.add(tab_operator, text="Operator Entry")
        nb.add(tab_shift, text="Shift Production")

        self._build_operator_entry(tab_operator)
        self._build_shift_production(tab_shift)

    def _build_operator_entry(self, parent):
        body = tk.Frame(parent, bg=self.controller.colors["bg"], padx=20, pady=20)
        body.pack(fill="both", expand=True)

        style = {"bg": self.controller.colors["bg"], "fg": self.controller.colors["fg"]}

        tk.Label(body, text="Operator Entry", font=("Arial", 16, "bold"), **style).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 15)
        )

        # Line selection
        tk.Label(body, text="Line:", **style).grid(row=1, column=0, sticky="e", pady=6)
        line_options = list_lines()
        if not line_options:
            line_options = ["U725", "JL"]
        self.line_var = tk.StringVar(value=self.controller.user_line or "Both")
        self.line_cb = ttk.Combobox(body, values=line_options, state="readonly", width=18)
        if self.line_var.get() in line_options:
            self.line_cb.set(self.line_var.get())
        else:
            self.line_cb.current(0)
        self.line_cb.grid(row=1, column=1, sticky="w")

        # Cell ran
        tk.Label(body, text="Cell Ran:", **style).grid(row=2, column=0, sticky="e", pady=6)
        self.cell_entry = tk.Entry(body, width=24)
        self.cell_entry.grid(row=2, column=1, sticky="w")

        # Parts ran
        tk.Label(body, text="Parts Ran:", **style).grid(row=3, column=0, sticky="e", pady=6)
        self.parts_entry = tk.Entry(body, width=24)
        self.parts_entry.grid(row=3, column=1, sticky="w")

        # Downtime selection
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

        self._toggle_downtime_fields()

        tk.Button(
            body,
            text="Submit",
            command=self.submit,
            bg="#28a745",
            fg="white",
            font=("Arial", 12, "bold"),
            width=16,
        ).grid(row=6, column=0, columnspan=4, pady=20, sticky="w")

    def _build_shift_production(self, parent):
        body = tk.Frame(parent, bg=self.controller.colors["bg"], padx=20, pady=20)
        body.pack(fill="both", expand=True)

        style = {"bg": self.controller.colors["bg"], "fg": self.controller.colors["fg"]}

        tk.Label(body, text="Shift Production", font=("Arial", 16, "bold"), **style).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 15)
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

        tk.Label(body, text="Shift:", **style).grid(row=2, column=0, sticky="e", pady=6)
        self.shift_var = tk.StringVar(value="1st")
        self.shift_cb = ttk.Combobox(body, values=["1st", "2nd", "3rd"], state="readonly", width=18)
        self.shift_cb.set(self.shift_var.get())
        self.shift_cb.grid(row=2, column=1, sticky="w")

        tk.Label(body, text="Production Qty:", **style).grid(row=3, column=0, sticky="e", pady=6)
        self.shift_qty_entry = tk.Entry(body, width=18)
        self.shift_qty_entry.grid(row=3, column=1, sticky="w")

        tk.Label(body, text="Downtime (min):", **style).grid(row=4, column=0, sticky="e", pady=6)
        self.shift_downtime_entry = tk.Entry(body, width=18)
        self.shift_downtime_entry.insert(0, "0")
        self.shift_downtime_entry.grid(row=4, column=1, sticky="w")

        tk.Button(
            body,
            text="Submit Shift Report",
            command=self.submit_shift_report,
            bg="#28a745",
            fg="white",
            font=("Arial", 12, "bold"),
            width=20,
        ).grid(row=6, column=0, columnspan=3, pady=20, sticky="w")

    def _toggle_downtime_fields(self, event=None):
        enabled = bool(self.downtime_var.get())
        state = "normal" if enabled else "disabled"
        for entry in (self.dt_total_entry, self.dt_occ_entry, self.dt_comment_entry):
            entry.configure(state=state)
            if not enabled:
                entry.delete(0, "end")

    def submit(self):
        cell = self.cell_entry.get().strip()
        parts = self.parts_entry.get().strip()
        if not cell:
            messagebox.showerror("Missing Info", "Enter the cell ran.")
            return
        if not parts:
            messagebox.showerror("Missing Info", "Enter the parts ran.")
            return

        downtime_display = self.downtime_var.get().strip()
        downtime_code = self.downtime_map.get(downtime_display, "")
        dt_total = safe_float(self.dt_total_entry.get(), 0.0) if downtime_code else 0.0
        dt_occ = safe_int(self.dt_occ_entry.get(), 0) if downtime_code else 0
        dt_comments = self.dt_comment_entry.get().strip() if downtime_code else ""

        now = datetime.now()
        entry_id = f"OP-{now.strftime('%Y%m%d-%H%M%S')}"
        upsert_operator_entry({
            "id": entry_id,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "username": self.controller.user or "",
            "line": self.line_cb.get(),
            "cell_ran": cell,
            "parts_ran": parts,
            "downtime_code": downtime_code,
            "downtime_total_time": dt_total,
            "downtime_occurrences": dt_occ,
            "downtime_comments": dt_comments,
        })

        messagebox.showinfo("Saved", "Operator entry saved.")
        self.cell_entry.delete(0, "end")
        self.parts_entry.delete(0, "end")
        self.downtime_var.set("")
        self._toggle_downtime_fields()

    def submit_shift_report(self):
        qty = safe_int(self.shift_qty_entry.get(), 0)
        if qty <= 0:
            messagebox.showerror("Missing Info", "Enter the production quantity.")
            return
        downtime = safe_float(self.shift_downtime_entry.get(), 0.0)
        now = datetime.now()
        entry_id = f"SP-{now.strftime('%Y%m%d-%H%M%S')}"
        new_row = {
            "ID": entry_id,
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
            "Shift": self.shift_cb.get(),
            "Line": self.shift_line_cb.get(),
            "Machine": "",
            "Part_Number": "",
            "Tool_Num": "",
            "Reason": "Shift Production",
            "Downtime_Mins": downtime,
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
        log_audit(self.controller.user, f"Shift production entry {entry_id} saved")

        messagebox.showinfo("Saved", "Shift production report submitted for leader signoff.")
        self.shift_qty_entry.delete(0, "end")
        self.shift_downtime_entry.delete(0, "end")
        self.shift_downtime_entry.insert(0, "0")
