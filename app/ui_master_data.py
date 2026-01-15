# app/ui_master_data.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import shutil
import pandas as pd

from .storage import safe_float, safe_int
from .db import (
    list_tools_simple,
    upsert_tool_inventory,
    deactivate_tool,
    list_tools_for_line,
    list_lines,
    get_tool_lines,
    set_tool_lines,
    list_tool_inserts,
    replace_tool_inserts,
    get_tool_parts,
    set_tool_parts,
    list_parts_with_lines,
    upsert_part,
    deactivate_part,
    set_scrap_cost,
    get_scrap_costs_simple,
    list_downtime_codes,
    upsert_downtime_code,
    deactivate_downtime_code,
    ensure_lines,
    list_production_goals,
    upsert_production_goal,
    list_cells_for_line,
    list_cells_with_machines,
    list_machines_for_cell,
    upsert_cell,
    upsert_machine,
    delete_cell,
    delete_machine,
    list_parts_for_line,
)
from .audit import log_audit
from .config import DB_PATH



class MasterDataUI(tk.Frame):
    """
    Super/Admin Master Data:
      - Tool pricing
      - Parts + line assignments
      - Scrap pricing by part
    Robust against legacy JSON shapes.
    """

    def __init__(self, parent, controller, show_header=True):
        super().__init__(parent, bg=controller.colors["bg"])
        self.controller = controller
        self.readonly = not controller.can_edit_screen("Master Data")

        top_controls = tk.Frame(self, bg=controller.colors["bg"], padx=10, pady=10)
        top_controls.pack(fill="x")

        tk.Label(
            top_controls,
            text="Master Data",
            bg=controller.colors["bg"],
            fg=controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        self.db_export_btn = tk.Button(top_controls, text="Export Database", command=self._export_database)
        self.db_export_btn.pack(side="right")
        self.db_import_btn = tk.Button(top_controls, text="Import Database", command=self._import_database)
        self.db_import_btn.pack(side="right", padx=8)
        self.md_export_btn = tk.Button(top_controls, text="Export Master Data", command=self._export_master_data)
        self.md_export_btn.pack(side="right", padx=8)
        self.md_import_btn = tk.Button(top_controls, text="Import Master Data", command=self._import_master_data)
        self.md_import_btn.pack(side="right", padx=8)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        tab_tools = tk.Frame(nb, bg=controller.colors["bg"])
        tab_parts = tk.Frame(nb, bg=controller.colors["bg"])
        tab_scrap = tk.Frame(nb, bg=controller.colors["bg"])
        tab_downtime = tk.Frame(nb, bg=controller.colors["bg"])
        tab_goals = tk.Frame(nb, bg=controller.colors["bg"])
        tab_cells = tk.Frame(nb, bg=controller.colors["bg"])

        nb.add(tab_tools, text="Tool Pricing")
        nb.add(tab_parts, text="Parts & Lines")
        nb.add(tab_scrap, text="Scrap Pricing")
        nb.add(tab_downtime, text="Downtime Codes")
        nb.add(tab_goals, text="Production Goals")
        nb.add(tab_cells, text="Cells & Machines")

        self._build_tool_pricing(tab_tools)
        self._build_parts(tab_parts)
        self._build_scrap(tab_scrap)
        self._build_downtime(tab_downtime)
        self._build_production_goals(tab_goals)
        self._build_cells(tab_cells)
        self._apply_readonly_master_data()

    def _apply_readonly_master_data(self):
        if not self.readonly:
            return
        self.db_import_btn.configure(state="disabled")
        self.db_export_btn.configure(state="disabled")
        self.md_import_btn.configure(state="disabled")
        self.md_export_btn.configure(state="disabled")

    # -------------------- TOOL PRICING --------------------
    def _build_tool_pricing(self, parent):
        top = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(
            top,
            text="Tool Pricing",
            bg=self.controller.colors["bg"],
            fg=self.controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        tk.Button(top, text="Refresh", command=self.refresh_tools).pack(side="right")
        self.tool_add_btn = tk.Button(top, text="Add Tool", command=lambda: self._open_tool_editor())
        self.tool_add_btn.pack(side="right", padx=8)

        filter_frame = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=6)
        filter_frame.pack(fill="x")

        tk.Label(filter_frame, text="Line Filter:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).pack(side="left")
        self.tool_line_filter = tk.StringVar(value="All")
        line_options = ["All"] + (list_lines() or [])
        self.tool_line_combo = ttk.Combobox(
            filter_frame,
            values=line_options,
            textvariable=self.tool_line_filter,
            state="readonly",
            width=18,
        )
        self.tool_line_combo.pack(side="left", padx=8)
        self.tool_line_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_tools())

        self.tool_del_btn = tk.Button(filter_frame, text="Deactivate Selected", command=self.delete_selected_tool)
        self.tool_del_btn.pack(side="right")

        cols = ("tool", "name", "unit_cost", "stock_qty", "lines", "parts")
        self.tool_tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for c in cols:
            self.tool_tree.heading(c, text=c.upper())
            if c == "unit_cost":
                self.tool_tree.column(c, width=140)
            elif c == "stock_qty":
                self.tool_tree.column(c, width=140)
            elif c in ("lines", "parts"):
                self.tool_tree.column(c, width=220)
            else:
                self.tool_tree.column(c, width=220)
        self.tool_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tool_tree.bind("<Double-1>", lambda e: self._open_tool_editor(self._selected_tool()))

        self.refresh_tools()
        self._apply_readonly_tool()

    def _apply_readonly_tool(self):
        if not self.readonly:
            return
        self.tool_add_btn.configure(state="disabled")
        self.tool_del_btn.configure(state="disabled")

    def refresh_tools(self):
        for i in self.tool_tree.get_children():
            self.tool_tree.delete(i)

        line_filter = self.tool_line_filter.get() if hasattr(self, "tool_line_filter") else "All"
        tool_rows = list_tools_simple()
        if line_filter and line_filter != "All":
            allowed = set(list_tools_for_line(line_filter, include_unassigned=False))
            tool_rows = [t for t in tool_rows if t.get("tool_num") in allowed]

        for tool in tool_rows:
            tool_num = tool.get("tool_num", "")
            self.tool_tree.insert("", "end", values=(
                tool_num,
                tool.get("name", ""),
                tool.get("unit_cost", 0.0),
                tool.get("stock_qty", 0),
                ", ".join(get_tool_lines(tool_num)),
                ", ".join(get_tool_parts(tool_num)),
            ))

    def _selected_tool(self):
        sel = self.tool_tree.selection()
        if not sel:
            return ""
        return self.tool_tree.item(sel[0], "values")[0]

    def _open_tool_editor(self, tool_num: str = ""):
        if self.readonly:
            return
        top = tk.Toplevel(self)
        top.title("Tool Editor")
        top.geometry("740x640")

        is_new = not tool_num
        tool_data = {}
        if tool_num:
            for t in list_tools_simple():
                if t.get("tool_num") == tool_num:
                    tool_data = t
                    break

        form = tk.Frame(top, padx=12, pady=12)
        form.pack(fill="both", expand=True)

        tk.Label(form, text="Tool #").grid(row=0, column=0, sticky="w")
        tool_num_var = tk.StringVar(value=tool_num)
        tool_num_entry = tk.Entry(form, textvariable=tool_num_var, width=18)
        tool_num_entry.grid(row=0, column=1, sticky="w")
        if not is_new:
            tool_num_entry.configure(state="readonly")

        tk.Label(form, text="Name").grid(row=0, column=2, sticky="w", padx=(12, 0))
        tool_name_var = tk.StringVar(value=tool_data.get("name", ""))
        tk.Entry(form, textvariable=tool_name_var, width=30).grid(row=0, column=3, sticky="w")

        tk.Label(form, text="Unit Cost ($)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        tool_cost_var = tk.StringVar(value=str(tool_data.get("unit_cost", 0.0)))
        tk.Entry(form, textvariable=tool_cost_var, width=12).grid(row=1, column=1, sticky="w", pady=(8, 0))

        tk.Label(form, text="Stock Qty").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(8, 0))
        tool_stock_var = tk.StringVar(value=str(tool_data.get("stock_qty", 0)))
        tk.Entry(form, textvariable=tool_stock_var, width=12).grid(row=1, column=3, sticky="w", pady=(8, 0))

        line_frame = tk.LabelFrame(form, text="Lines", padx=8, pady=8)
        line_frame.grid(row=2, column=0, columnspan=4, sticky="we", pady=10)
        line_opts = list_lines() or ["U725", "JL"]
        selected_lines = set(get_tool_lines(tool_num)) if tool_num else set()
        line_vars = {}
        for idx, line in enumerate(line_opts):
            var = tk.BooleanVar(value=line in selected_lines)
            line_vars[line] = var
            tk.Checkbutton(line_frame, text=line, variable=var).grid(row=0, column=idx, sticky="w", padx=6)

        parts_frame = tk.LabelFrame(form, text="Parts", padx=8, pady=8)
        parts_frame.grid(row=3, column=0, columnspan=4, sticky="we", pady=10)
        part_options = [p.get("part_number", "") for p in list_parts_with_lines()]
        selected_parts = set(get_tool_parts(tool_num)) if tool_num else set()
        part_vars = {}
        for idx, pn in enumerate(part_options):
            var = tk.BooleanVar(value=pn in selected_parts)
            part_vars[pn] = var
            tk.Checkbutton(parts_frame, text=pn, variable=var).grid(row=idx // 4, column=idx % 4, sticky="w", padx=6)

        inserts_frame = tk.LabelFrame(form, text="Insert Types", padx=8, pady=8)
        inserts_frame.grid(row=4, column=0, columnspan=4, sticky="we", pady=10)

        inserts_nb = ttk.Notebook(inserts_frame)
        inserts_nb.pack(fill="both", expand=True)

        insert_tabs = []
        for ins in list_tool_inserts(tool_num):
            insert_tabs.append(self._populate_insert_tab(inserts_nb, ins))
        if not insert_tabs:
            insert_tabs.append(self._populate_insert_tab(inserts_nb, {}))

        def add_insert_tab():
            insert_tabs.append(self._populate_insert_tab(inserts_nb, {}))

        tk.Button(inserts_frame, text="Add Insert Type", command=add_insert_tab).pack(pady=6)

        calc_lbl = tk.Label(form, text="Calculated change cost: $0.00")
        calc_lbl.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))

        def recalc_cost():
            cost = self._calculate_insert_cost(self._collect_insert_data(insert_tabs))
            calc_lbl.config(text=f"Calculated change cost: ${cost:,.4f}")

        tk.Button(form, text="Recalculate Cost", command=recalc_cost).grid(row=6, column=0, pady=8, sticky="w")

        def save():
            tnum = tool_num_var.get().strip()
            if not tnum:
                messagebox.showerror("Error", "Tool # is required.")
                return
            upsert_tool_inventory(
                tool_num=tnum,
                name=tool_name_var.get().strip(),
                unit_cost=safe_float(tool_cost_var.get(), 0.0),
                stock_qty=safe_int(tool_stock_var.get(), 0),
                inserts_per_tool=1,
            )
            set_tool_lines(tnum, [ln for ln, var in line_vars.items() if var.get()])
            set_tool_parts(tnum, [pn for pn, var in part_vars.items() if var.get()])
            replace_tool_inserts(tnum, self._collect_insert_data(insert_tabs))
            log_audit(self.controller.user, f"Updated tool {tnum} configuration")
            self.refresh_tools()
            top.destroy()

        tk.Button(form, text="Save Tool", command=save, bg="#28a745", fg="white").grid(row=6, column=3, pady=8, sticky="e")
        recalc_cost()

    def delete_selected_tool(self):
        sel = self.tool_tree.selection()
        if not sel:
            return
        tool = self.tool_tree.item(sel[0], "values")[0]
        if not tool:
            return
        if not messagebox.askyesno("Confirm", f"Delete tool '{tool}'?"):
            return
        deactivate_tool(tool)
        log_audit(self.controller.user, f"Deactivated tool {tool}")
        self.refresh_tools()

    def save_tools(self):
        messagebox.showinfo("Saved", "Tool pricing saved.")

    def _populate_insert_tab(self, notebook: ttk.Notebook, data: dict):
        frame = tk.Frame(notebook)
        notebook.add(frame, text=data.get("insert_name") or "Insert")

        fields = {}
        labels = [
            ("Insert Name", "insert_name"),
            ("# Inserts", "insert_count"),
            ("Price/Insert", "price_per_insert"),
            ("Sides/Insert", "sides_per_insert"),
            ("Tool Life", "tool_life"),
        ]
        for row, (label, key) in enumerate(labels):
            tk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=6)
            var = tk.StringVar(value=str(data.get(key, "")))
            entry = tk.Entry(frame, textvariable=var, width=18)
            entry.grid(row=row, column=1, sticky="w", pady=4)
            fields[key] = var
        return {"frame": frame, "fields": fields, "notebook": notebook}

    def _collect_insert_data(self, insert_tabs):
        data = []
        for tab in insert_tabs:
            fields = tab["fields"]
            name = fields["insert_name"].get().strip()
            data.append({
                "insert_name": name,
                "insert_count": safe_int(fields["insert_count"].get(), 0),
                "price_per_insert": safe_float(fields["price_per_insert"].get(), 0.0),
                "sides_per_insert": safe_int(fields["sides_per_insert"].get(), 1),
                "tool_life": safe_float(fields["tool_life"].get(), 0.0),
            })
            if name:
                tab["notebook"].tab(tab["frame"], text=name)
        return data

    def _calculate_insert_cost(self, inserts):
        total = 0.0
        for ins in inserts:
            count = safe_float(ins.get("insert_count", 0), 0.0)
            price = safe_float(ins.get("price_per_insert", 0), 0.0)
            life = safe_float(ins.get("tool_life", 0), 0.0)
            sides = safe_float(ins.get("sides_per_insert", 1), 1.0)
            if life <= 0 or sides <= 0:
                continue
            total += ((count * price) / life) / sides
        return total

    # -------------------- PARTS & LINES --------------------
    def _build_parts(self, parent):
        top = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(
            top,
            text="Parts & Line Assignment",
            bg=self.controller.colors["bg"],
            fg=self.controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        tk.Button(top, text="Refresh", command=self.refresh_parts).pack(side="right")
        self.part_add_btn = tk.Button(top, text="Add Part", command=lambda: self._open_part_editor())
        self.part_add_btn.pack(side="right", padx=8)

        cols = ("part_number", "name", "lines")
        self.part_tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for c in cols:
            self.part_tree.heading(c, text=c.upper())
            self.part_tree.column(c, width=260 if c != "lines" else 420)
        self.part_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.part_tree.bind("<Double-1>", lambda e: self._open_part_editor(self._selected_part()))

        self.part_del_btn = tk.Button(parent, text="Delete Selected", command=self.delete_selected_part)
        self.part_del_btn.pack(anchor="e", padx=10, pady=(0, 10))

        self.refresh_parts()
        self._apply_readonly_parts()

    def _apply_readonly_parts(self):
        if not self.readonly:
            return
        self.part_add_btn.configure(state="disabled")
        self.part_del_btn.configure(state="disabled")

    def refresh_parts(self):
        for i in self.part_tree.get_children():
            self.part_tree.delete(i)

        for p in list_parts_with_lines():
            self.part_tree.insert("", "end", values=(
                p.get("part_number", ""),
                p.get("name", ""),
                ", ".join(p.get("lines", []) or []),
            ))

    def _selected_part(self):
        sel = self.part_tree.selection()
        if not sel:
            return ""
        return self.part_tree.item(sel[0], "values")[0]

    def _open_part_editor(self, part_number: str = ""):
        if self.readonly:
            return
        top = tk.Toplevel(self)
        top.title("Part Editor")
        top.geometry("520x360")

        existing = {}
        for p in list_parts_with_lines():
            if p.get("part_number") == part_number:
                existing = p
                break

        form = tk.Frame(top, padx=12, pady=12)
        form.pack(fill="both", expand=True)

        tk.Label(form, text="Part #").grid(row=0, column=0, sticky="w")
        part_var = tk.StringVar(value=part_number)
        part_entry = tk.Entry(form, textvariable=part_var, width=24)
        part_entry.grid(row=0, column=1, sticky="w")
        if part_number:
            part_entry.configure(state="readonly")

        tk.Label(form, text="Name").grid(row=1, column=0, sticky="w", pady=(8, 0))
        name_var = tk.StringVar(value=existing.get("name", ""))
        tk.Entry(form, textvariable=name_var, width=30).grid(row=1, column=1, sticky="w", pady=(8, 0))

        line_frame = tk.LabelFrame(form, text="Lines", padx=8, pady=8)
        line_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=10)
        line_opts = list_lines() or ["U725", "JL"]
        selected = set(existing.get("lines", []) or [])
        line_vars = {}
        for idx, line in enumerate(line_opts):
            var = tk.BooleanVar(value=line in selected)
            line_vars[line] = var
            tk.Checkbutton(line_frame, text=line, variable=var).grid(row=0, column=idx, sticky="w", padx=6)

        def save():
            pn = part_var.get().strip()
            if not pn:
                messagebox.showerror("Error", "Part # is required.")
                return
            name = name_var.get().strip()
            lines = [ln for ln, var in line_vars.items() if var.get()]
            upsert_part(pn, name=name, lines=lines)
            log_audit(self.controller.user, f"Updated part {pn} lines/pricing")
            self.refresh_parts()
            top.destroy()

        tk.Button(form, text="Save Part", command=save, bg="#28a745", fg="white").grid(row=3, column=1, sticky="e", pady=10)

    def delete_selected_part(self):
        sel = self.part_tree.selection()
        if not sel:
            return
        pn = self.part_tree.item(sel[0], "values")[0]
        if not pn:
            return
        if not messagebox.askyesno("Confirm", f"Delete part '{pn}'?"):
            return

        deactivate_part(pn)
        log_audit(self.controller.user, f"Deactivated part {pn}")
        self.refresh_parts()

    # -------------------- SCRAP PRICING --------------------
    def _build_scrap(self, parent):
        top = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(
            top,
            text="Scrap Pricing (by Part)",
            bg=self.controller.colors["bg"],
            fg=self.controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        tk.Button(top, text="Refresh", command=self.refresh_scrap).pack(side="right")
        self.scrap_add_btn = tk.Button(top, text="Add Scrap Cost", command=lambda: self._open_scrap_editor())
        self.scrap_add_btn.pack(side="right", padx=8)

        cols = ("part_number", "scrap_cost")
        self.scrap_tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for c in cols:
            self.scrap_tree.heading(c, text=c.upper())
            self.scrap_tree.column(c, width=260)
        self.scrap_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.scrap_tree.bind("<Double-1>", lambda e: self._open_scrap_editor(self._selected_scrap_part()))

        self.scrap_del_btn = tk.Button(parent, text="Delete Selected", command=self.delete_selected_scrap)
        self.scrap_del_btn.pack(anchor="e", padx=10, pady=(0, 10))

        self.refresh_scrap()
        self._apply_readonly_scrap()

    def _apply_readonly_scrap(self):
        if not self.readonly:
            return
        self.scrap_add_btn.configure(state="disabled")
        self.scrap_del_btn.configure(state="disabled")

    def refresh_scrap(self):
        for i in self.scrap_tree.get_children():
            self.scrap_tree.delete(i)

        m = get_scrap_costs_simple()
        for pn in sorted(m.keys()):
            self.scrap_tree.insert("", "end", values=(pn, m[pn]))
    def _selected_scrap_part(self):
        sel = self.scrap_tree.selection()
        if not sel:
            return ""
        return self.scrap_tree.item(sel[0], "values")[0]

    def _open_scrap_editor(self, part_number: str = ""):
        if self.readonly:
            return
        top = tk.Toplevel(self)
        top.title("Scrap Cost Editor")
        top.geometry("420x220")

        existing_costs = get_scrap_costs_simple()
        cost_val = existing_costs.get(part_number, "")

        form = tk.Frame(top, padx=12, pady=12)
        form.pack(fill="both", expand=True)

        tk.Label(form, text="Part #").grid(row=0, column=0, sticky="w")
        pn_var = tk.StringVar(value=part_number)
        pn_entry = tk.Entry(form, textvariable=pn_var, width=18)
        pn_entry.grid(row=0, column=1, sticky="w")
        if part_number:
            pn_entry.configure(state="readonly")

        tk.Label(form, text="Scrap Cost ($)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        cost_var = tk.StringVar(value=str(cost_val))
        tk.Entry(form, textvariable=cost_var, width=12).grid(row=1, column=1, sticky="w", pady=(8, 0))

        def save():
            pn = pn_var.get().strip()
            if not pn:
                messagebox.showerror("Error", "Part # is required.")
                return
            cost = safe_float(cost_var.get(), 0.0)
            set_scrap_cost(pn, cost)
            log_audit(self.controller.user, f"Set scrap cost for {pn} to {cost}")
            self.refresh_scrap()
            top.destroy()

        tk.Button(form, text="Save Scrap Cost", command=save, bg="#28a745", fg="white").grid(row=2, column=1, sticky="e", pady=12)

    def delete_selected_scrap(self):
        sel = self.scrap_tree.selection()
        if not sel:
            return
        pn = self.scrap_tree.item(sel[0], "values")[0]
        if not pn:
            return
        if not messagebox.askyesno("Confirm", f"Delete scrap price for '{pn}'?"):
            return
        set_scrap_cost(pn, 0.0)
        log_audit(self.controller.user, f"Cleared scrap cost for {pn}")
        self.refresh_scrap()

    # -------------------- DOWNTIME CODES --------------------
    def _build_downtime(self, parent):
        top = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(
            top,
            text="Downtime Codes",
            bg=self.controller.colors["bg"],
            fg=self.controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        tk.Button(top, text="Refresh", command=self.refresh_downtime).pack(side="right")
        self.downtime_add_btn = tk.Button(top, text="Add Code", command=lambda: self._open_downtime_editor())
        self.downtime_add_btn.pack(side="right", padx=8)

        cols = ("code", "description", "active")
        self.downtime_tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for c in cols:
            self.downtime_tree.heading(c, text=c.upper())
            self.downtime_tree.column(c, width=220)
        self.downtime_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.downtime_tree.bind("<Double-1>", lambda e: self._open_downtime_editor(self._selected_downtime()))

        self.downtime_del_btn = tk.Button(parent, text="Deactivate Selected", command=self.delete_selected_downtime)
        self.downtime_del_btn.pack(anchor="e", padx=10, pady=(0, 10))

        self.refresh_downtime()
        if self.readonly:
            self.downtime_add_btn.configure(state="disabled")
            self.downtime_del_btn.configure(state="disabled")

    def refresh_downtime(self):
        for i in self.downtime_tree.get_children():
            self.downtime_tree.delete(i)

        for row in list_downtime_codes(active_only=False):
            self.downtime_tree.insert("", "end", values=(
                row.get("code", ""),
                row.get("description", ""),
                "Yes" if row.get("is_active", 1) else "No",
            ))

    def _selected_downtime(self):
        sel = self.downtime_tree.selection()
        if not sel:
            return ""
        return self.downtime_tree.item(sel[0], "values")[0]

    def _open_downtime_editor(self, code: str = ""):
        if self.readonly:
            return
        top = tk.Toplevel(self)
        top.title("Downtime Code Editor")
        top.geometry("420x220")

        existing = {row["code"]: row for row in list_downtime_codes(active_only=False)}
        info = existing.get(code, {})

        form = tk.Frame(top, padx=12, pady=12)
        form.pack(fill="both", expand=True)

        tk.Label(form, text="Code").grid(row=0, column=0, sticky="w")
        code_var = tk.StringVar(value=code)
        code_entry = tk.Entry(form, textvariable=code_var, width=18)
        code_entry.grid(row=0, column=1, sticky="w")
        if code:
            code_entry.configure(state="readonly")

        tk.Label(form, text="Description").grid(row=1, column=0, sticky="w", pady=(8, 0))
        desc_var = tk.StringVar(value=info.get("description", ""))
        tk.Entry(form, textvariable=desc_var, width=30).grid(row=1, column=1, sticky="w", pady=(8, 0))

        def save():
            code_val = code_var.get().strip()
            if not code_val:
                messagebox.showerror("Error", "Code is required.")
                return
            upsert_downtime_code(code_val, desc_var.get().strip())
            log_audit(self.controller.user, f"Updated downtime code {code_val}")
            self.refresh_downtime()
            top.destroy()

        tk.Button(form, text="Save Code", command=save, bg="#28a745", fg="white").grid(row=2, column=1, sticky="e", pady=12)

    def delete_selected_downtime(self):
        code = self._selected_downtime()
        if not code:
            return
        if not messagebox.askyesno("Confirm", f"Deactivate downtime code '{code}'?"):
            return
        deactivate_downtime_code(code)
        log_audit(self.controller.user, f"Deactivated downtime code {code}")
        self.refresh_downtime()

    # -------------------- CELLS & MACHINES --------------------
    def _build_cells(self, parent):
        top = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(
            top,
            text="Cells & Machines",
            bg=self.controller.colors["bg"],
            fg=self.controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        tk.Button(top, text="Refresh", command=self.refresh_cells).pack(side="right")

        filter_frame = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=6)
        filter_frame.pack(fill="x")

        tk.Label(filter_frame, text="Line:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).pack(side="left")
        self.cell_line_var = tk.StringVar(value="")
        self.cell_line_combo = ttk.Combobox(
            filter_frame,
            values=list_lines(),
            textvariable=self.cell_line_var,
            state="readonly",
            width=18,
        )
        self.cell_line_combo.pack(side="left", padx=6)
        self.cell_line_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_cells())

        self.cell_del_btn = tk.Button(filter_frame, text="Delete Selected", command=self.delete_selected_cell_machine)
        self.cell_del_btn.pack(side="right")

        form = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=6)
        form.pack(fill="x")

        tk.Label(form, text="New Cell:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).grid(row=0, column=0, sticky="w")
        self.new_cell_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=self.new_cell_var, width=20).grid(row=0, column=1, sticky="w", padx=6)
        self.add_cell_btn = tk.Button(form, text="Add Cell", command=self.add_cell, bg="#28a745", fg="white")
        self.add_cell_btn.grid(row=0, column=2, sticky="w", padx=6)

        tk.Label(form, text="Cell:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.machine_cell_var = tk.StringVar(value="")
        self.machine_cell_combo = ttk.Combobox(
            form,
            values=[],
            textvariable=self.machine_cell_var,
            state="readonly",
            width=18,
        )
        self.machine_cell_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))

        tk.Label(form, text="Machine:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).grid(
            row=1, column=2, sticky="w", padx=(12, 0), pady=(8, 0)
        )
        self.new_machine_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=self.new_machine_var, width=20).grid(row=1, column=3, sticky="w", padx=6, pady=(8, 0))
        self.add_machine_btn = tk.Button(form, text="Add Machine", command=self.add_machine, bg="#28a745", fg="white")
        self.add_machine_btn.grid(row=1, column=4, sticky="w", padx=6, pady=(8, 0))

        cols = ("cell", "machine")
        self.cell_tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        for c in cols:
            self.cell_tree.heading(c, text=c.upper())
            self.cell_tree.column(c, width=220)
        self.cell_tree.pack(fill="both", expand=True, padx=10, pady=10)

        if self.readonly:
            self.add_cell_btn.configure(state="disabled")
            self.add_machine_btn.configure(state="disabled")
            self.cell_del_btn.configure(state="disabled")

        self.refresh_cells()

    def refresh_cells(self):
        if hasattr(self, "cell_tree"):
            for i in self.cell_tree.get_children():
                self.cell_tree.delete(i)
            line = self.cell_line_combo.get().strip() if hasattr(self, "cell_line_combo") else ""
            if not line:
                line_opts = list_lines()
                if line_opts:
                    line = line_opts[0]
                    self.cell_line_combo.set(line)
            rows = list_cells_with_machines(line) if line else []
            if rows:
                for row in rows:
                    self.cell_tree.insert("", "end", values=(row.get("cell", ""), row.get("machine", "")))
            else:
                for cell in list_cells_for_line(line):
                    self.cell_tree.insert("", "end", values=(cell, ""))

            cells = list_cells_for_line(line)
            self.machine_cell_combo.configure(values=cells)
            if cells:
                self.machine_cell_combo.set(cells[0])
            else:
                self.machine_cell_combo.set("")

            self.cell_line_combo.configure(values=list_lines())

    def add_cell(self):
        if self.readonly:
            return
        line = self.cell_line_combo.get().strip()
        cell = self.new_cell_var.get().strip()
        if not line:
            messagebox.showerror("Missing Info", "Select a line.")
            return
        if not cell:
            messagebox.showerror("Missing Info", "Enter a cell name.")
            return
        upsert_cell(line, cell)
        log_audit(self.controller.user, f"Added cell {cell} to {line}")
        self.new_cell_var.set("")
        self.refresh_cells()

    def add_machine(self):
        if self.readonly:
            return
        line = self.cell_line_combo.get().strip()
        cell = self.machine_cell_combo.get().strip()
        machine = self.new_machine_var.get().strip()
        if not line:
            messagebox.showerror("Missing Info", "Select a line.")
            return
        if not cell:
            messagebox.showerror("Missing Info", "Select a cell.")
            return
        if not machine:
            messagebox.showerror("Missing Info", "Enter a machine name.")
            return
        upsert_machine(line, cell, machine)
        log_audit(self.controller.user, f"Added machine {machine} to {cell} ({line})")
        self.new_machine_var.set("")
        self.refresh_cells()

    def delete_selected_cell_machine(self):
        if self.readonly:
            return
        sel = self.cell_tree.selection()
        if not sel:
            return
        line = self.cell_line_combo.get().strip()
        cell, machine = self.cell_tree.item(sel[0], "values")
        if machine:
            if not messagebox.askyesno("Confirm", f"Delete machine '{machine}' from cell '{cell}'?"):
                return
            delete_machine(line, cell, machine)
            log_audit(self.controller.user, f"Deleted machine {machine} from {cell} ({line})")
        else:
            if not messagebox.askyesno("Confirm", f"Delete cell '{cell}' and all machines?"):
                return
            delete_cell(line, cell)
            log_audit(self.controller.user, f"Deleted cell {cell} from {line}")
        self.refresh_cells()

    # -------------------- DATABASE IMPORT/EXPORT --------------------
    def _export_database(self):
        if self.readonly:
            return
        path = filedialog.asksaveasfilename(
            title="Export Database",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            shutil.copyfile(DB_PATH, path)
            log_audit(self.controller.user, f"Exported database to {path}")
            messagebox.showinfo("Exported", f"Database exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Unable to export database.\n{exc}")

    def _import_database(self):
        if self.readonly:
            return
        path = filedialog.askopenfilename(
            title="Import Database",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Confirm Import",
            "Importing a database will overwrite current data. Continue?",
        ):
            return
        try:
            shutil.copyfile(path, DB_PATH)
            log_audit(self.controller.user, f"Imported database from {path}")
            messagebox.showinfo("Imported", "Database imported. Please restart the app.")
        except Exception as exc:
            messagebox.showerror("Import Failed", f"Unable to import database.\n{exc}")

    # -------------------- MASTER DATA IMPORT/EXPORT --------------------
    def _collect_master_data(self):
        lines = list_lines()
        parts = list_parts_with_lines()
        tools = list_tools_simple()
        downtime = list_downtime_codes(active_only=False)
        goals = list_production_goals()

        df_lines = pd.DataFrame([{"line": ln} for ln in lines], columns=["line"])
        df_parts = pd.DataFrame(
            [
                {
                    "part_number": p.get("part_number", ""),
                    "name": p.get("name", ""),
                    "lines": ", ".join(p.get("lines", []) or []),
                    "is_active": 1,
                }
                for p in parts
            ],
            columns=["part_number", "name", "lines", "is_active"],
        )
        df_tools = pd.DataFrame(
            [
                {
                    "tool_num": t.get("tool_num", ""),
                    "name": t.get("name", ""),
                    "unit_cost": t.get("unit_cost", 0.0),
                    "stock_qty": t.get("stock_qty", 0),
                    "inserts_per_tool": t.get("inserts_per_tool", 1),
                    "lines": ", ".join(get_tool_lines(t.get("tool_num", ""))),
                    "parts": ", ".join(get_tool_parts(t.get("tool_num", ""))),
                    "is_active": 1,
                }
                for t in tools
            ],
            columns=[
                "tool_num",
                "name",
                "unit_cost",
                "stock_qty",
                "inserts_per_tool",
                "lines",
                "parts",
                "is_active",
            ],
        )
        df_downtime = pd.DataFrame(
            [
                {
                    "code": d.get("code", ""),
                    "description": d.get("description", ""),
                    "is_active": int(d.get("is_active", 1) or 0),
                }
                for d in downtime
            ],
            columns=["code", "description", "is_active"],
        )
        df_goals = pd.DataFrame(
            [
                {
                    "line": g.get("line", ""),
                    "cell": g.get("cell", ""),
                    "part_number": g.get("part_number", ""),
                    "target": g.get("target", 0.0),
                }
                for g in goals
            ],
            columns=["line", "cell", "part_number", "target"],
        )

        cells_rows = []
        machines_rows = []
        for line in lines:
            for cell in list_cells_for_line(line):
                cells_rows.append({"line": line, "cell": cell})
                for machine in list_machines_for_cell(line, cell):
                    machines_rows.append({"line": line, "cell": cell, "machine": machine})

        df_cells = pd.DataFrame(cells_rows, columns=["line", "cell"])
        df_machines = pd.DataFrame(machines_rows, columns=["line", "cell", "machine"])
        return {
            "lines": df_lines,
            "parts": df_parts,
            "tools": df_tools,
            "downtime_codes": df_downtime,
            "production_goals": df_goals,
            "cells": df_cells,
            "machines": df_machines,
        }

    def _export_master_data(self):
        if self.readonly:
            return
        path = filedialog.asksaveasfilename(
            title="Export Master Data",
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx"), ("CSV (combined)", "*.csv")],
        )
        if not path:
            return
        data = self._collect_master_data()
        try:
            if path.lower().endswith(".csv"):
                frames = []
                columns = ["table"]
                for name, df in data.items():
                    df = df.copy()
                    df.insert(0, "table", name)
                    for col in df.columns:
                        if col not in columns:
                            columns.append(col)
                    frames.append(df)
                out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
                out = out.reindex(columns=columns)
                out.to_csv(path, index=False)
            else:
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    for name, df in data.items():
                        df.to_excel(writer, sheet_name=name, index=False)
            log_audit(self.controller.user, f"Exported master data to {path}")
            messagebox.showinfo("Exported", f"Master data exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Unable to export master data.\n{exc}")

    def _import_master_data(self):
        if self.readonly:
            return
        path = filedialog.askopenfilename(
            title="Import Master Data",
            filetypes=[("Excel Workbook", "*.xlsx"), ("CSV (combined)", "*.csv")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Confirm Import",
            "Importing master data will overwrite or add data. Continue?",
        ):
            return

        try:
            if path.lower().endswith(".csv"):
                df_all = pd.read_csv(path)
                if "table" not in df_all.columns:
                    raise ValueError("CSV must include a 'table' column.")
                sheets = {name: sub.drop(columns=["table"]) for name, sub in df_all.groupby("table")}
            else:
                sheets = pd.read_excel(path, sheet_name=None)

            self._apply_master_data_import(sheets)
            log_audit(self.controller.user, f"Imported master data from {path}")
            messagebox.showinfo("Imported", "Master data imported.")
            self.refresh_tools()
            self.refresh_parts()
            self.refresh_scrap()
            self.refresh_downtime()
            self.refresh_goals()
            self.refresh_cells()
        except Exception as exc:
            messagebox.showerror("Import Failed", f"Unable to import master data.\n{exc}")

    def _apply_master_data_import(self, sheets):
        def _sheet(name: str) -> pd.DataFrame:
            for key, df in sheets.items():
                if key.lower() == name:
                    return df
            return pd.DataFrame()

        def _clean(df: pd.DataFrame) -> pd.DataFrame:
            return df.fillna("")

        lines_df = _clean(_sheet("lines"))
        if not lines_df.empty and "line" in lines_df.columns:
            ensure_lines(lines_df["line"].astype(str).tolist())

        parts_df = _clean(_sheet("parts"))
        if not parts_df.empty and "part_number" in parts_df.columns:
            for _, row in parts_df.iterrows():
                part_number = str(row.get("part_number", "")).strip()
                if not part_number:
                    continue
                is_active = safe_int(row.get("is_active", 1), 1)
                if is_active:
                    lines = [ln.strip() for ln in str(row.get("lines", "")).split(",") if ln.strip()]
                    upsert_part(part_number, str(row.get("name", "")).strip(), lines)
                else:
                    deactivate_part(part_number)

        tools_df = _clean(_sheet("tools"))
        if not tools_df.empty and "tool_num" in tools_df.columns:
            tool_lines = {}
            tool_parts = {}
            for _, row in tools_df.iterrows():
                tool_num = str(row.get("tool_num", "")).strip()
                if not tool_num:
                    continue
                is_active = safe_int(row.get("is_active", 1), 1)
                if is_active:
                    upsert_tool_inventory(
                        tool_num,
                        name=str(row.get("name", "")).strip(),
                        unit_cost=safe_float(row.get("unit_cost", 0.0), 0.0),
                        stock_qty=safe_int(row.get("stock_qty", 0), 0),
                        inserts_per_tool=safe_int(row.get("inserts_per_tool", 1), 1),
                    )
                    tool_lines[tool_num] = [ln.strip() for ln in str(row.get("lines", "")).split(",") if ln.strip()]
                    tool_parts[tool_num] = [pn.strip() for pn in str(row.get("parts", "")).split(",") if pn.strip()]
                else:
                    deactivate_tool(tool_num)
            for tool_num, lines in tool_lines.items():
                set_tool_lines(tool_num, lines)
            for tool_num, parts in tool_parts.items():
                set_tool_parts(tool_num, parts)

        downtime_df = _clean(_sheet("downtime_codes"))
        if not downtime_df.empty and "code" in downtime_df.columns:
            for _, row in downtime_df.iterrows():
                code = str(row.get("code", "")).strip()
                if not code:
                    continue
                is_active = safe_int(row.get("is_active", 1), 1)
                if is_active:
                    upsert_downtime_code(code, str(row.get("description", "")).strip())
                else:
                    deactivate_downtime_code(code)

        goals_df = _clean(_sheet("production_goals"))
        if not goals_df.empty and "line" in goals_df.columns:
            for _, row in goals_df.iterrows():
                line = str(row.get("line", "")).strip()
                cell = str(row.get("cell", "")).strip()
                part_number = str(row.get("part_number", "")).strip()
                if not line or not cell or not part_number:
                    continue
                target = safe_float(row.get("target", 0.0), 0.0)
                upsert_production_goal(line, cell, part_number, target)

        cells_df = _clean(_sheet("cells"))
        if not cells_df.empty and "line" in cells_df.columns:
            for _, row in cells_df.iterrows():
                line = str(row.get("line", "")).strip()
                cell = str(row.get("cell", "")).strip()
                if line and cell:
                    upsert_cell(line, cell)

        machines_df = _clean(_sheet("machines"))
        if not machines_df.empty and "line" in machines_df.columns:
            for _, row in machines_df.iterrows():
                line = str(row.get("line", "")).strip()
                cell = str(row.get("cell", "")).strip()
                machine = str(row.get("machine", "")).strip()
                if line and cell and machine:
                    upsert_machine(line, cell, machine)

    # -------------------- PRODUCTION GOALS --------------------
    def _build_production_goals(self, parent):
        top = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(
            top,
            text="Production Goals (Target per Line)",
            bg=self.controller.colors["bg"],
            fg=self.controller.colors["fg"],
            font=("Arial", 14, "bold"),
        ).pack(side="left")

        tk.Button(top, text="Refresh", command=self.refresh_goals).pack(side="right")

        form = tk.Frame(parent, bg=self.controller.colors["bg"], padx=10, pady=6)
        form.pack(fill="x")

        tk.Label(form, text="Line:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).pack(side="left")
        self.goal_line_var = tk.StringVar(value="")
        self.goal_line_combo = ttk.Combobox(
            form,
            values=list_lines(),
            textvariable=self.goal_line_var,
            state="readonly",
            width=12,
        )
        self.goal_line_combo.pack(side="left", padx=6)
        self.goal_line_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_goal_cells())

        tk.Label(form, text="Cell:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).pack(side="left")
        self.goal_cell_var = tk.StringVar(value="")
        self.goal_cell_combo = ttk.Combobox(
            form,
            values=[],
            textvariable=self.goal_cell_var,
            state="readonly",
            width=12,
        )
        self.goal_cell_combo.pack(side="left", padx=6)
        self.goal_cell_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_goal_parts())

        tk.Label(form, text="Part:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).pack(side="left")
        self.goal_part_var = tk.StringVar(value="")
        self.goal_part_combo = ttk.Combobox(
            form,
            values=[],
            textvariable=self.goal_part_var,
            state="readonly",
            width=16,
        )
        self.goal_part_combo.pack(side="left", padx=6)

        tk.Label(form, text="Target:", bg=self.controller.colors["bg"], fg=self.controller.colors["fg"]).pack(side="left")
        self.goal_target_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=self.goal_target_var, width=10).pack(side="left", padx=6)

        self.goal_save_btn = tk.Button(form, text="Save Goal", command=self.save_goal, bg="#28a745", fg="white")
        self.goal_save_btn.pack(side="left", padx=8)

        cols = ("line", "cell", "part_number", "target")
        self.goal_tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        for c in cols:
            self.goal_tree.heading(c, text=c.upper())
            if c in {"line", "cell"}:
                self.goal_tree.column(c, width=140)
            elif c == "part_number":
                self.goal_tree.column(c, width=180)
            else:
                self.goal_tree.column(c, width=120)
        self.goal_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.goal_tree.bind("<<TreeviewSelect>>", self._load_selected_goal)

        self.refresh_goals()
        if self.readonly:
            self.goal_save_btn.configure(state="disabled")

    def refresh_goals(self):
        if hasattr(self, "goal_tree"):
            for i in self.goal_tree.get_children():
                self.goal_tree.delete(i)
            for goal in list_production_goals():
                self.goal_tree.insert("", "end", values=(
                    goal.get("line", ""),
                    goal.get("cell", ""),
                    goal.get("part_number", ""),
                    goal.get("target", 0.0),
                ))
        if hasattr(self, "goal_line_combo"):
            self.goal_line_combo.configure(values=list_lines())
        self._refresh_goal_cells()

    def _refresh_goal_cells(self):
        if not hasattr(self, "goal_cell_combo") or not hasattr(self, "goal_line_combo"):
            return
        line = self.goal_line_combo.get().strip()
        cells = list_cells_for_line(line)
        self.goal_cell_combo.configure(values=cells)
        if cells and self.goal_cell_var.get() not in cells:
            self.goal_cell_var.set(cells[0])
        elif not cells:
            self.goal_cell_var.set("")
        self._refresh_goal_parts()

    def _refresh_goal_parts(self):
        if not hasattr(self, "goal_part_combo") or not hasattr(self, "goal_line_combo"):
            return
        line = self.goal_line_combo.get().strip()
        parts = list_parts_for_line(line)
        self.goal_part_combo.configure(values=parts)
        if parts and self.goal_part_var.get() not in parts:
            self.goal_part_var.set(parts[0])
        elif not parts:
            self.goal_part_var.set("")

    def _load_selected_goal(self, event=None):
        sel = self.goal_tree.selection()
        if not sel:
            return
        line, cell, part_number, target = self.goal_tree.item(sel[0], "values")
        self.goal_line_var.set(line)
        self._refresh_goal_cells()
        self.goal_cell_var.set(cell)
        self._refresh_goal_parts()
        self.goal_part_var.set(part_number)
        self.goal_target_var.set(str(target))

    def save_goal(self):
        if self.readonly:
            return
        line = self.goal_line_var.get().strip()
        cell = self.goal_cell_var.get().strip()
        part_number = self.goal_part_var.get().strip()
        if not line:
            messagebox.showerror("Error", "Select a line.")
            return
        if not cell:
            messagebox.showerror("Error", "Select a cell.")
            return
        if not part_number:
            messagebox.showerror("Error", "Select a part number.")
            return
        target = safe_float(self.goal_target_var.get(), 0.0)
        upsert_production_goal(line, cell, part_number, target)
        log_audit(self.controller.user, f"Updated production goal for {line}/{cell}/{part_number}: {target}")
        self.refresh_goals()
