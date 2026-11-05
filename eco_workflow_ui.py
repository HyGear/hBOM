"""
Graphical ECO Workflow & Approval Center + Tab 5 Layout Restructurer (`eco_workflow_ui.py`)
"""

import tkinter as tk
from tkinter import ttk, messagebox
from database import session_scope
from models import (
    EngineeringChange, Part, PartPendingUpdate, BOMItem,
    ECODrawingRegistrationItem, ECOAttachment
)


STATUS_COLORS = {
    "REQUESTED": ("#A855F7", "#F3E8FF"),        # Purple
    "OPEN": ("#38BDF8", "#E0F2FE"),             # Cyan / Blue
    "PENDING_APPROVAL": ("#F59E0B", "#FEF3C7"), # Amber / Gold
    "APPROVED": ("#10B981", "#D1FAE5"),         # Emerald
    "RELEASED": ("#22C55E", "#DCFCE7"),         # Bright Green
}


def _walk_widgets(root_widget):
    """Yields root_widget and all of its descendants recursively."""
    yield root_widget
    for child in root_widget.winfo_children():
        yield from _walk_widgets(child)


def _fmt_dt(dt_val) -> str:
    if not dt_val:
        return ""
    try:
        return dt_val.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt_val)[:16]


class ECOWorkflowDialog(tk.Toplevel):
    """
    Graphical Flowchart & Role-Based Approval Center for Engineering Change Orders.
    Displays current workflow state, pre-flight gate checks, and role-filtered action buttons.
    """

    def __init__(self, app, refs: dict):
        super().__init__(app)
        self.app = app
        self.refs = refs
        self.title("hBOM — ECO Graphical Workflow & Approval Center")
        self.geometry("1040x690")
        self.minsize(960, 640)

        self.colors = getattr(app, "colors", None) or {
            "bg_primary": "#0F172A",
            "bg_surface": "#1E293B",
            "fg_primary": "#F8FAFC",
            "fg_secondary": "#94A3B8",
            "accent_primary": "#38BDF8",
            "accent_success": "#22C55E",
            "accent_warning": "#F59E0B",
        }
        self.configure(bg=self.colors["bg_primary"])
        self.transient(app)
        self.grab_set()

        self.active_eco_num = self._detect_initial_eco()
        self._build_ui()
        self._refresh_eco_list()
        self._load_and_render_eco(self.active_eco_num)

        self.lift()
        self.focus_force()

    def _get_user_role(self) -> str:
        role = getattr(self.app, "user_role", None)
        if not role and hasattr(self.app, "user_settings"):
            role = self.app.user_settings.get("user_role", "VIEWER")
        return str(role or "VIEWER").strip().upper()

    def _get_user_display(self) -> str:
        uid = getattr(self.app, "active_userid", None) or "user"
        role = self._get_user_role()
        return f"{uid} [{role}]"

    def _detect_initial_eco(self) -> str:
        # 1. Check Active ECO combobox in Panel 1
        cmb = self.refs.get("cmb_active_eco")
        if cmb is not None:
            val = cmb.get().strip()
            if val:
                return val.split()[0].strip()

        # 2. Check selected row in Master Log treeview
        tree = self.refs.get("tree_master_log")
        if tree is not None:
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if vals:
                    return str(vals[0]).strip()

        # 3. Fallback to most recent ECO in database
        with session_scope() as s:
            first_eco = s.query(EngineeringChange).order_by(EngineeringChange.created_at.desc()).first()
            return first_eco.eco_number if first_eco else ""

    def _build_ui(self):
        bg_pri = self.colors["bg_primary"]
        bg_sur = self.colors["bg_surface"]
        fg_pri = self.colors["fg_primary"]
        fg_sec = self.colors["fg_secondary"]
        acc_pri = self.colors["accent_primary"]
        acc_suc = self.colors["accent_success"]

        outer = tk.Frame(self, bg=bg_pri, padx=14, pady=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # ------------------------------------------------------------------
        # 1. TOP BAR: ECO SELECTOR & USER ROLE BADGE
        # ------------------------------------------------------------------
        top_bar = tk.Frame(outer, bg=bg_sur, padx=12, pady=10, highlightthickness=1, highlightbackground="#334155")
        top_bar.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            top_bar,
            text="Target ECO / ECR:",
            bg=bg_sur,
            fg=acc_pri,
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.cmb_eco_selector = ttk.Combobox(top_bar, width=22, state="readonly", font=("Segoe UI", 10, "bold"))
        self.cmb_eco_selector.pack(side=tk.LEFT, padx=(0, 12))
        self.cmb_eco_selector.bind("<<ComboboxSelected>>", self._on_popup_eco_selected)

        self.lbl_eco_headline = tk.Label(
            top_bar,
            text="",
            bg=bg_sur,
            fg=fg_pri,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.lbl_eco_headline.pack(side=tk.LEFT, fill=tk.X, expand=True)

        role_str = self._get_user_display()
        tk.Label(
            top_bar,
            text=f"Signed In: {role_str}",
            bg="#1E3A8A",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT)

        # ------------------------------------------------------------------
        # 2. GRAPHICAL FLOWCHART CANVAS
        # ------------------------------------------------------------------
        flow_frame = tk.LabelFrame(
            outer,
            text=" Graphical ECO Lifecycle Flowchart (Current Step Highlighted) ",
            bg=bg_pri,
            fg=acc_suc,
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=6,
        )
        flow_frame.pack(fill=tk.X, pady=(0, 10))

        self.canvas = tk.Canvas(
            flow_frame,
            height=235,
            bg="#0B1120",
            bd=0,
            highlightthickness=1,
            highlightbackground="#1E293B",
        )
        self.canvas.pack(fill=tk.X, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw_flowchart(self._current_eco_data))

        # ------------------------------------------------------------------
        # 3. MIDDLE SPLIT: PRE-FLIGHT GATE CHECKLIST & CHANGE SUMMARY
        # ------------------------------------------------------------------
        mid_frame = tk.Frame(outer, bg=bg_pri)
        mid_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        mid_frame.columnconfigure(0, weight=1)
        mid_frame.columnconfigure(1, weight=1)
        mid_frame.rowconfigure(0, weight=1)

        gate_lf = tk.LabelFrame(
            mid_frame,
            text=" Pre-Flight Gate & Readiness Audit ",
            bg=bg_pri,
            fg=acc_pri,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        gate_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.txt_gates = tk.Text(
            gate_lf,
            height=8,
            wrap=tk.WORD,
            bg=bg_sur,
            fg=fg_pri,
            font=("Consolas", 10),
            padx=10,
            pady=8,
            bd=0,
            highlightthickness=0,
        )
        self.txt_gates.pack(fill=tk.BOTH, expand=True)
        self.txt_gates.tag_configure("ok", foreground="#22C55E", font=("Consolas", 10, "bold"))
        self.txt_gates.tag_configure("warn", foreground="#F59E0B", font=("Consolas", 10, "bold"))
        self.txt_gates.tag_configure("info", foreground="#38BDF8", font=("Consolas", 10, "bold"))
        self.txt_gates.tag_configure("muted", foreground="#94A3B8", font=("Consolas", 9))

        reason_lf = tk.LabelFrame(
            mid_frame,
            text=" Engineering Change Reason & Audit Trail ",
            bg=bg_pri,
            fg=acc_pri,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=8,
        )
        reason_lf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.txt_reason_audit = tk.Text(
            reason_lf,
            height=8,
            wrap=tk.WORD,
            bg=bg_sur,
            fg=fg_pri,
            font=("Consolas", 10),
            padx=10,
            pady=8,
            bd=0,
            highlightthickness=0,
        )
        self.txt_reason_audit.pack(fill=tk.BOTH, expand=True)
        self.txt_reason_audit.tag_configure("head", foreground="#38BDF8", font=("Consolas", 10, "bold"))

        # ------------------------------------------------------------------
        # 4. BOTTOM BAR: ROLE-FILTERED WORKFLOW ACTION BUTTONS
        # ------------------------------------------------------------------
        self.action_lf = tk.LabelFrame(
            outer,
            text=" Available Workflow Actions for Your Role ",
            bg=bg_pri,
            fg=acc_suc,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=10,
        )
        self.action_lf.pack(fill=tk.X)

        self.lbl_role_guidance = tk.Label(
            self.action_lf,
            text="",
            bg=bg_pri,
            fg=fg_sec,
            font=("Segoe UI", 9, "italic"),
            anchor="w",
        )
        self.lbl_role_guidance.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_container = tk.Frame(self.action_lf, bg=bg_pri)
        self.btn_container.pack(side=tk.RIGHT)

        self._current_eco_data = None

    def _refresh_eco_list(self):
        with session_scope() as s:
            ecos = s.query(EngineeringChange).order_by(EngineeringChange.created_at.desc()).all()
            items = [f"{e.eco_number}  [{e.status}]" for e in ecos]
            self._eco_map = {f"{e.eco_number}  [{e.status}]": e.eco_number for e in ecos}
            self.cmb_eco_selector["values"] = items

            if self.active_eco_num:
                for label, num in self._eco_map.items():
                    if num == self.active_eco_num:
                        self.cmb_eco_selector.set(label)
                        break
            elif items:
                self.cmb_eco_selector.set(items[0])
                self.active_eco_num = self._eco_map[items[0]]

    def _on_popup_eco_selected(self, event=None):
        sel = self.cmb_eco_selector.get()
        eco_num = self._eco_map.get(sel, sel.split()[0].strip() if sel else "")
        if eco_num:
            self._sync_main_window_to_eco(eco_num)
            self._load_and_render_eco(eco_num)

    def _sync_main_window_to_eco(self, eco_num: str):
        """Synchronizes Tab 5's Active ECO combobox and Master Log selection with the popup's target ECO."""
        cmb = self.refs.get("cmb_active_eco")
        if cmb is not None:
            vals = list(cmb["values"]) if cmb["values"] else []
            matched = None
            for v in vals:
                if str(v).split()[0].strip().upper() == eco_num.upper():
                    matched = v
                    break
            if matched is not None:
                cmb.set(matched)
            else:
                cmb.set(eco_num)
            try:
                cmb.event_generate("<<ComboboxSelected>>")
            except Exception:
                pass

        tree = self.refs.get("tree_master_log")
        if tree is not None:
            for iid in tree.get_children():
                row_vals = tree.item(iid, "values")
                if row_vals and str(row_vals[0]).strip().upper() == eco_num.upper():
                    tree.selection_set(iid)
                    tree.see(iid)
                    try:
                        tree.event_generate("<<TreeviewSelect>>")
                    except Exception:
                        pass
                    break

    def _load_and_render_eco(self, eco_num: str):
        self.active_eco_num = eco_num
        if not eco_num:
            self._current_eco_data = None
            self.lbl_eco_headline.configure(text="No ECO Selected — Pull or Request an ECO first.")
            self._draw_flowchart(None)
            return

        with session_scope() as s:
            eco = s.get(EngineeringChange, eco_num)
            if not eco:
                eco = s.query(EngineeringChange).filter(EngineeringChange.eco_number.ilike(eco_num)).first()
            if not eco:
                self._current_eco_data = None
                self.lbl_eco_headline.configure(text=f"ECO '{eco_num}' not found.")
                self._draw_flowchart(None)
                return

            new_pts = s.query(Part).filter_by(eco_number=eco.eco_number).count()
            mod_pts = s.query(PartPendingUpdate).filter_by(eco_number=eco.eco_number).count()
            bom_rows = s.query(BOMItem).filter_by(eco_number=eco.eco_number).count()
            dwg_items = s.query(ECODrawingRegistrationItem).filter_by(eco_number=eco.eco_number).all()
            dwg_total = len(dwg_items)
            dwg_reg = sum(1 for d in dwg_items if d.is_registered)
            att_count = s.query(ECOAttachment).filter_by(eco_number=eco.eco_number).count()

            data = {
                "eco_number": eco.eco_number,
                "eco_type": eco.eco_type or "PRODUCTION",
                "status": (eco.status or "OPEN").upper(),
                "title": eco.title or "(Untitled ECO)",
                "reason": eco.reason or "",
                "created_by": eco.created_by or "engineer",
                "created_at": _fmt_dt(getattr(eco, "created_at", None)),
                "submitted_at": _fmt_dt(getattr(eco, "submitted_at", None)),
                "approved_by": getattr(eco, "approved_by", None) or "",
                "approved_at": _fmt_dt(getattr(eco, "approved_at", None)),
                "released_by": getattr(eco, "released_by", None) or "",
                "released_at": _fmt_dt(getattr(eco, "released_at", None)),
                "new_pts": new_pts,
                "mod_pts": mod_pts,
                "bom_rows": bom_rows,
                "dwg_total": dwg_total,
                "dwg_reg": dwg_reg,
                "att_count": att_count,
            }

        self._current_eco_data = data
        self.lbl_eco_headline.configure(
            text=f"{data['eco_number']} ({data['eco_type']}) — {data['title']}"
        )
        self._draw_flowchart(data)
        self._populate_gates_and_audit(data)
        self._build_role_action_buttons(data)

        if "update_badge_fn" in self.refs:
            self.refs["update_badge_fn"](data["eco_number"], data["status"])

    def _draw_flowchart(self, data):
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 960)
        h = max(c.winfo_height(), 235)

        if not data:
            c.create_text(
                w // 2, h // 2,
                text="Select or Pull an ECO to view its graphical lifecycle flowchart.",
                fill="#94A3B8",
                font=("Segoe UI", 11, "italic"),
            )
            return

        status = data["status"]
        stages = [
            ("REQUESTED", "1. REQUESTED", "ECR / PECO Request", data["created_by"], data["created_at"]),
            ("OPEN", "2. OPEN", "Active Engineering", data["created_by"], data["created_at"]),
            ("PENDING_APPROVAL", "3. PEND APPROVAL", "Submitted for Review", data["created_by"], data["submitted_at"]),
            ("APPROVED", "4. APPROVED", "Approver Sign-Off", data["approved_by"], data["approved_at"]),
            ("RELEASED", "5. RELEASED", "Production Baseline", data["released_by"], data["released_at"]),
        ]
        order_idx = {s[0]: i for i, s in enumerate(stages)}
        curr_idx = order_idx.get(status, 1)

        margin_x = 28
        avail_w = w - 2 * margin_x
        box_w = min(158, int(avail_w / 5.9))
        gap = int((avail_w - 5 * box_w) / 4)
        top_y = 32
        box_h = 112
        mid_y = top_y + box_h // 2

        box_centers = []

        for idx, (st_key, title, subtitle, actor, dt_str) in enumerate(stages):
            x1 = margin_x + idx * (box_w + gap)
            x2 = x1 + box_w
            cx = (x1 + x2) // 2
            box_centers.append((x1, x2, cx))

            if idx < curr_idx or status == "RELEASED":
                fill_col = "#064E3B"
                border_col = "#22C55E"
                border_w = 2
                badge_txt = "✓ COMPLETED"
                badge_col = "#4ADE80"
            elif idx == curr_idx:
                fill_col = "#1E3A8A"
                border_col = "#38BDF8"
                border_w = 3
                badge_txt = "★ CURRENT STEP ★"
                badge_col = "#FACC15"
                c.create_rectangle(
                    x1 - 4, top_y - 4, x2 + 4, top_y + box_h + 4,
                    outline="#38BDF8", width=1, dash=(4, 2)
                )
            else:
                fill_col = "#1E293B"
                border_col = "#475569"
                border_w = 1
                badge_txt = "○ UPCOMING"
                badge_col = "#94A3B8"

            c.create_rectangle(x1, top_y, x2, top_y + box_h, fill=fill_col, outline=border_col, width=border_w)
            c.create_rectangle(x1, top_y, x2, top_y + 26, fill=border_col if idx == curr_idx else "#0F172A", outline="")

            c.create_text(
                cx, top_y + 13,
                text=title,
                fill="#0F172A" if idx == curr_idx else "#F8FAFC",
                font=("Segoe UI", 9, "bold"),
            )
            c.create_text(
                cx, top_y + 42,
                text=subtitle,
                fill="#E2E8F0",
                font=("Segoe UI", 8),
            )
            c.create_text(
                cx, top_y + 64,
                text=badge_txt,
                fill=badge_col,
                font=("Segoe UI", 8, "bold"),
            )

            meta_line = ""
            if idx <= curr_idx:
                if actor and dt_str:
                    meta_line = f"{actor} • {dt_str[:10]}"
                elif actor:
                    meta_line = f"By: {actor}"
                elif dt_str:
                    meta_line = dt_str[:10]
            c.create_text(
                cx, top_y + 90,
                text=meta_line,
                fill="#CBD5E1",
                font=("Consolas", 8),
            )

            if idx < len(stages) - 1:
                ax1 = x2 + 3
                ax2 = x1 + box_w + gap - 3
                arrow_col = "#22C55E" if idx < curr_idx else "#475569"
                c.create_line(ax1, mid_y, ax2, mid_y, fill=arrow_col, width=3, arrow=tk.LAST, arrowshape=(10, 12, 5))

        # Return / Rejection Feedback Loop underneath from Stage 3 & Stage 4 back to Stage 2 (OPEN)
        _, _, cx_open = box_centers[1]
        _, _, cx_pend = box_centers[2]
        _, _, cx_appr = box_centers[3]
        loop_y = top_y + box_h + 44

        loop_active = status in ("PENDING_APPROVAL", "APPROVED")
        loop_col = "#F59E0B" if loop_active else "#475569"
        dash_pat = () if loop_active else (4, 3)

        c.create_line(cx_pend, top_y + box_h + 2, cx_pend, loop_y, fill=loop_col, width=2, dash=dash_pat)
        c.create_line(cx_appr, top_y + box_h + 2, cx_appr, loop_y, fill=loop_col, width=2, dash=dash_pat)
        c.create_line(cx_appr, loop_y, cx_open, loop_y, fill=loop_col, width=2, dash=dash_pat)
        c.create_line(
            cx_open, loop_y, cx_open, top_y + box_h + 3,
            fill=loop_col, width=2, arrow=tk.LAST, arrowshape=(9, 11, 4)
        )
        c.create_text(
            (cx_open + cx_appr) // 2,
            loop_y + 14,
            text="↩ Reject / Return to OPEN (Re-opens ECO for additional engineering edits)",
            fill=loop_col,
            font=("Segoe UI", 8, "bold" if loop_active else "normal"),
        )

    def _populate_gates_and_audit(self, d: dict):
        self.txt_gates.configure(state=tk.NORMAL)
        self.txt_gates.delete("1.0", tk.END)

        has_title = bool(d["title"] and d["title"] != "(Untitled ECO)")
        has_reason = bool(d["reason"].strip())
        if has_title and has_reason:
            self.txt_gates.insert(tk.END, "[✓] Gate 1 — Title & Engineering Reason: Populated\n", "ok")
        else:
            self.txt_gates.insert(tk.END, "[!] Gate 1 — Title & Engineering Reason: Incomplete\n", "warn")

        total_changes = d["new_pts"] + d["mod_pts"] + d["bom_rows"]
        if total_changes > 0:
            self.txt_gates.insert(
                tk.END,
                f"[✓] Gate 2 — Staged Engineering Changes: {total_changes} total item(s)\n",
                "ok",
            )
        else:
            self.txt_gates.insert(
                tk.END,
                "[i] Gate 2 — Staged Engineering Changes: 0 items attached so far\n",
                "info",
            )
        self.txt_gates.insert(
            tk.END,
            f"      • New Parts Created      : {d['new_pts']}\n"
            f"      • Modified Parts Staged  : {d['mod_pts']}\n"
            f"      • BOM Markup Rows Staged : {d['bom_rows']}\n"
            f"      • Attached Reference Docs: {d['att_count']}\n",
            "muted",
        )

        if d["dwg_total"] == 0:
            self.txt_gates.insert(
                tk.END,
                "[✓] Gate 3 — Drawing Checklist: 0 Required Drawings (Ready)\n",
                "ok",
            )
        elif d["dwg_reg"] >= d["dwg_total"]:
            self.txt_gates.insert(
                tk.END,
                f"[✓] Gate 3 — Drawing Checklist: {d['dwg_reg']}/{d['dwg_total']} Registered (Complete)\n",
                "ok",
            )
        else:
            self.txt_gates.insert(
                tk.END,
                f"[!] Gate 3 — Drawing Checklist: {d['dwg_reg']}/{d['dwg_total']} Registered\n"
                f"      (All required drawings must be registered in Tab 6 before Release)\n",
                "warn",
            )

        self.txt_gates.configure(state=tk.DISABLED)

        self.txt_reason_audit.configure(state=tk.NORMAL)
        self.txt_reason_audit.delete("1.0", tk.END)
        self.txt_reason_audit.insert(tk.END, "ENGINEERING REASON / DESCRIPTION:\n", "head")
        self.txt_reason_audit.insert(tk.END, f"{d['reason'] or '(No reason entered)'}\n\n")
        self.txt_reason_audit.insert(tk.END, "SIGN-OFF & TIMESTAMP AUDIT:\n", "head")
        self.txt_reason_audit.insert(
            tk.END,
            f"• Created By   : {d['created_by']} ({d['created_at'] or 'N/A'})\n"
            f"• Submitted At : {d['submitted_at'] or 'Pending'}\n"
            f"• Approved By  : {d['approved_by'] or 'Pending'} ({d['approved_at'] or 'N/A'})\n"
            f"• Released By  : {d['released_by'] or 'Pending'} ({d['released_at'] or 'N/A'})\n",
        )
        self.txt_reason_audit.configure(state=tk.DISABLED)

    def _build_role_action_buttons(self, d: dict):
        for child in self.btn_container.winfo_children():
            child.destroy()

        status = d["status"]
        role = self._get_user_role()
        can_design = role in ("DESIGNER", "ENGINEER", "APPROVER", "ADMIN")
        can_approve = role in ("APPROVER", "ADMIN")

        def _make_btn(text, bg_col, cmd, state=tk.NORMAL):
            btn = tk.Button(
                self.btn_container,
                text=text,
                bg=bg_col if state == tk.NORMAL else "#334155",
                fg="#FFFFFF" if state == tk.NORMAL else "#94A3B8",
                activebackground=bg_col,
                activeforeground="#FFFFFF",
                font=("Segoe UI", 9, "bold"),
                relief=tk.FLAT,
                padx=14,
                pady=6,
                state=state,
                command=cmd,
            )
            btn.pack(side=tk.LEFT, padx=5)
            return btn

        _make_btn("📄 Summary PDF...", "#475569", lambda: self._trigger_original_button("btn_pdf_report"))

        if status == "REQUESTED":
            if can_approve:
                self.lbl_role_guidance.configure(
                    text="This request is awaiting Approver sign-off to issue an editable OPEN ECO number."
                )
                _make_btn(
                    "✓ Approve Request (Issue Open ECO #)",
                    "#16A34A",
                    lambda: self._execute_transition("btn_approve_req"),
                )
            else:
                self.lbl_role_guidance.configure(
                    text=f"Your role ({role}) cannot approve ECR requests. An APPROVER or ADMIN must issue the ECO."
                )
                _make_btn("✓ Approve Request (Requires Approver)", "#334155", lambda: None, state=tk.DISABLED)

        elif status == "OPEN":
            if can_design:
                self.lbl_role_guidance.configure(
                    text="ECO is OPEN for authoring. When parts, BOM markups, and drawings are ready, submit for approval."
                )
                _make_btn(
                    "➜ Submit ECO for Approval",
                    "#2563EB",
                    lambda: self._execute_transition("btn_submit"),
                )
            else:
                self.lbl_role_guidance.configure(
                    text="Read-Only Viewer mode: A Designer, Approver, or Admin must submit this ECO."
                )
                _make_btn("➜ Submit ECO for Approval (Requires Designer)", "#334155", lambda: None, state=tk.DISABLED)

        elif status == "PENDING_APPROVAL":
            if can_approve:
                self.lbl_role_guidance.configure(
                    text="ECO is Pending Approval. Review the summary & gates above, then Approve or Reject/Return to Open."
                )
                _make_btn(
                    "↩ Reject / Return to Open",
                    "#D97706",
                    lambda: self._execute_transition("btn_reject"),
                )
                _make_btn(
                    "✓ Approve ECO",
                    "#16A34A",
                    lambda: self._execute_transition("btn_approve"),
                )
            else:
                self.lbl_role_guidance.configure(
                    text="ECO is frozen in PENDING_APPROVAL. Waiting on an APPROVER or ADMIN to review."
                )
                _make_btn("✓ Approve ECO (Requires Approver)", "#334155", lambda: None, state=tk.DISABLED)

        elif status == "APPROVED":
            if can_approve:
                self.lbl_role_guidance.configure(
                    text="ECO is APPROVED! Click 'Release Approved ECO' to promote all changes to production."
                )
                _make_btn(
                    "↩ Reject / Return to Open",
                    "#D97706",
                    lambda: self._execute_transition("btn_reject"),
                )
                _make_btn(
                    "🚀 Release Approved ECO to Production",
                    "#059669",
                    lambda: self._execute_transition("btn_release"),
                )
            else:
                self.lbl_role_guidance.configure(
                    text="ECO is APPROVED and awaiting final production release by an APPROVER or ADMIN."
                )
                _make_btn("🚀 Release Approved ECO (Requires Approver)", "#334155", lambda: None, state=tk.DISABLED)

        elif status == "RELEASED":
            self.lbl_role_guidance.configure(
                text="✓ This ECO is officially RELEASED to production and permanently locked."
            )

        _make_btn("Close Window", "#334155", self.destroy)

    def _trigger_original_button(self, ref_key: str):
        self._sync_main_window_to_eco(self.active_eco_num)
        btn = self.refs.get(ref_key)
        if btn is None:
            messagebox.showwarning("Action Unavailable", f"Control '{ref_key}' not found.", parent=self)
            return
        cmd = btn["command"]
        if cmd:
            self.app.tk.call(cmd)

    def _execute_transition(self, ref_key: str):
        prev_eco = self.active_eco_num
        with session_scope() as s:
            before_nums = {e.eco_number for e in s.query(EngineeringChange).all()}

        self._sync_main_window_to_eco(prev_eco)

        btn = self.refs.get(ref_key)
        if btn is None:
            messagebox.showwarning("Action Unavailable", f"Workflow button '{ref_key}' not found.", parent=self)
            return

        orig_state = str(btn.cget("state"))
        try:
            btn.configure(state=tk.NORMAL)
            btn.invoke()
        finally:
            try:
                btn.configure(state=orig_state)
            except Exception:
                pass

        target_eco = prev_eco
        with session_scope() as s:
            after_nums = {e.eco_number for e in s.query(EngineeringChange).all()}
            added = after_nums - before_nums
            if added:
                target_eco = sorted(added)[-1]
            elif prev_eco not in after_nums:
                cmb = self.refs.get("cmb_active_eco")
                if cmb and cmb.get().strip():
                    target_eco = cmb.get().strip().split()[0]

        self._refresh_eco_list()
        self._load_and_render_eco(target_eco)


def install_eco_manager_enhancements(app):
    """
    Locates Tab 5 ('5. ECO Manager'), reorganizes it into the clean top-down layout,
    replaces the 5 separate approval buttons with the unified 'Workflow & Approvals...'
    button + live status badge, and auto-loads the Master Log on startup.
    """

    # Hide redundant top-right 'Pull / Request ECO #...' button in global header bar
    for w in _walk_widgets(app):
        if isinstance(w, (ttk.Button, tk.Button)):
            b_txt = str(w.cget("text")).strip()
            if "pull / request eco #" in b_txt.lower():
                try:
                    if w.winfo_manager() == "pack":
                        w.pack_forget()
                    elif w.winfo_manager() == "grid":
                        w.grid_remove()
                except Exception:
                    pass

    nb = getattr(app, "notebook", None) or getattr(app, "nb", None)
    if nb is None:
        for w in _walk_widgets(app):
            if isinstance(w, ttk.Notebook):
                nb = w
                break
    if nb is None:
        return

    tab_eco = None
    for tab_id in nb.tabs():
        if "eco manager" in nb.tab(tab_id, "text").lower():
            tab_eco = nb.nametowidget(tab_id)
            break
    if tab_eco is None:
        return

    lf_pull_edit = None
    lf_smart_dwg = None
    lf_master_log = None
    lf_live_preview = None
    lf_reg_attach = None

    for w in _walk_widgets(tab_eco):
        if isinstance(w, (ttk.LabelFrame, tk.LabelFrame)):
            txt = str(w.cget("text")).strip().lower()
            if "pull eco number" in txt or "edit change info" in txt:
                lf_pull_edit = w
            elif "smart drawing update checklist" in txt:
                lf_smart_dwg = w
            elif "engineering change orders master log" in txt:
                lf_master_log = w
            elif "live eco summary report preview" in txt:
                lf_live_preview = w
            elif "official drawing registration" in txt or "attachments" in txt:
                lf_reg_attach = w

    if not all([lf_pull_edit, lf_smart_dwg, lf_master_log, lf_live_preview, lf_reg_attach]):
        return

    refs = {}
    for w in _walk_widgets(lf_pull_edit):
        if isinstance(w, (ttk.Button, tk.Button)):
            btxt = str(w.cget("text")).strip()
            low = btxt.lower()
            if "approve request" in low:
                refs["btn_approve_req"] = w
            elif "submit approval" in low:
                refs["btn_submit"] = w
            elif low == "approve eco":
                refs["btn_approve"] = w
            elif "reject" in low or "return" in low:
                refs["btn_reject"] = w
            elif "release approved" in low:
                refs["btn_release"] = w
            elif "save info" in low:
                refs["btn_save_info"] = w
            elif "summary report" in low:
                refs["btn_pdf_report"] = w
        elif isinstance(w, ttk.Combobox):
            vals = [str(v).upper() for v in (w["values"] or ())]
            if "PRODUCTION" not in vals and "PROTOTYPE" not in vals:
                refs["cmb_active_eco"] = w

    for w in _walk_widgets(lf_master_log):
        if isinstance(w, ttk.Treeview):
            refs["tree_master_log"] = w
        elif isinstance(w, (ttk.Button, tk.Button)):
            if str(w.cget("text")).strip().lower() == "show all":
                refs["btn_show_all"] = w

    for key in ("btn_approve_req", "btn_submit", "btn_approve", "btn_reject", "btn_release"):
        btn = refs.get(key)
        if btn is not None:
            try:
                if btn.winfo_manager() == "grid":
                    btn.grid_remove()
                elif btn.winfo_manager() == "pack":
                    btn.pack_forget()
            except Exception:
                pass

    btn_save = refs.get("btn_save_info")
    btn_bar = btn_save.master if btn_save is not None else lf_pull_edit

    def _open_workflow_dialog():
        ECOWorkflowDialog(app, refs)

    btn_workflow = tk.Button(
        btn_bar,
        text="❖ Manage Workflow / Approvals...",
        bg="#0284C7",
        fg="#FFFFFF",
        activebackground="#0369A1",
        activeforeground="#FFFFFF",
        font=("Segoe UI", 9, "bold"),
        relief=tk.FLAT,
        padx=14,
        pady=4,
        cursor="hand2",
        command=_open_workflow_dialog,
    )

    lbl_status_badge = tk.Label(
        btn_bar,
        text=" ● STATUS: --- ",
        bg="#1E293B",
        fg="#38BDF8",
        font=("Segoe UI", 9, "bold"),
        padx=8,
        pady=4,
    )

    if btn_save is not None and btn_save.winfo_manager() == "grid":
        btn_workflow.grid(row=0, column=8, padx=6, pady=2)
        lbl_status_badge.grid(row=0, column=9, padx=4, pady=2)
    else:
        btn_workflow.pack(side=tk.LEFT, padx=8)
        lbl_status_badge.pack(side=tk.LEFT, padx=4)

    def _update_status_badge(eco_num: str = "", status_str: str = ""):
        if not eco_num:
            cmb = refs.get("cmb_active_eco")
            if cmb and cmb.get().strip():
                eco_num = cmb.get().strip().split()[0]
        if eco_num and not status_str:
            try:
                with session_scope() as s:
                    e = s.get(EngineeringChange, eco_num)
                    if e:
                        status_str = (e.status or "OPEN").upper()
            except Exception:
                pass
        if not status_str:
            lbl_status_badge.configure(text=" ● NO ECO SELECTED ", bg="#1E293B", fg="#94A3B8")
            return
        fg_col, _ = STATUS_COLORS.get(status_str, ("#38BDF8", "#E0F2FE"))
        lbl_status_badge.configure(text=f" ● {eco_num}: {status_str} ", bg="#0F172A", fg=fg_col)

    refs["update_badge_fn"] = _update_status_badge

    cmb_active = refs.get("cmb_active_eco")
    if cmb_active is not None:
        cmb_active.bind("<<ComboboxSelected>>", lambda e: app.after(50, _update_status_badge), add="+")

    tree_log = refs.get("tree_master_log")
    if tree_log is not None:
        def _on_tree_click(event=None):
            sel = tree_log.selection()
            if sel:
                vals = tree_log.item(sel[0], "values")
                if vals:
                    _update_status_badge(str(vals[0]), str(vals[2]) if len(vals) > 2 else "")
        tree_log.bind("<<TreeviewSelect>>", _on_tree_click, add="+")
        tree_log.bind("<Double-1>", lambda e: _open_workflow_dialog(), add="+")

    parent_container = lf_master_log.master
    if (
        lf_pull_edit.master == parent_container
        and lf_smart_dwg.master == parent_container
        and lf_live_preview.master == parent_container
        and lf_reg_attach.master == parent_container
    ):
        lf_master_log.configure(
            text=" 1. Engineering Change Orders Master Log (Click Any Row to Load ECO — Double-Click for Workflow Flowchart) "
        )
        lf_pull_edit.configure(
            text=" 2. Active ECO Details, New ECO Pull & Workflow Control "
        )
        lf_live_preview.configure(
            text=" 3. Live ECO Summary Report Preview "
        )
        lf_smart_dwg.configure(
            text=" Smart Drawing Update Checklist (Click Row to Toggle [✓] / [ ] Checkmark) "
        )
        lf_reg_attach.configure(
            text=" Official Drawing Registration List & File Attachments "
        )

        lf_master_log.grid_configure(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=(4, 6))
        lf_pull_edit.grid_configure(row=2, column=0, columnspan=1, sticky="nsew", padx=(6, 4), pady=4)
        lf_live_preview.grid_configure(row=3, column=0, columnspan=1, sticky="nsew", padx=(6, 4), pady=(4, 6))

        bg_pri = getattr(app, "colors", {}).get("bg_primary", "#0F172A")
        right_host = tk.Frame(parent_container, bg=bg_pri)
        right_host.grid(row=2, column=1, rowspan=2, sticky="nsew", padx=(4, 6), pady=(4, 6))
        right_host.columnconfigure(0, weight=1)
        right_host.rowconfigure(1, weight=1)
        right_host.rowconfigure(2, weight=1)

        sw_bar = tk.Frame(right_host, bg=bg_pri)
        sw_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        tk.Label(
            sw_bar,
            text="Deliverables View:",
            bg=bg_pri,
            fg="#38BDF8",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(2, 8))

        btn_tab_a = tk.Button(
            sw_bar,
            text="📋 1. Smart Drawing Checklist",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
        )
        btn_tab_a.pack(side=tk.LEFT, padx=2)

        btn_tab_b = tk.Button(
            sw_bar,
            text="📎 2. Registered Drawings & Attachments",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
        )
        btn_tab_b.pack(side=tk.LEFT, padx=2)

        btn_split = tk.Button(
            sw_bar,
            text="⊞ Split View",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=8,
            pady=3,
            cursor="hand2",
        )
        btn_split.pack(side=tk.LEFT, padx=2)

        def _switch_deliverables_view(mode: str):
            lf_smart_dwg.grid_forget()
            lf_reg_attach.grid_forget()

            if mode == "smart":
                btn_tab_a.configure(bg="#2563EB", fg="#FFFFFF")
                btn_tab_b.configure(bg="#1E293B", fg="#94A3B8")
                btn_split.configure(bg="#1E293B", fg="#94A3B8")
                lf_smart_dwg.lift(right_host)
                lf_smart_dwg.grid(in_=right_host, row=1, column=0, rowspan=2, sticky="nsew")
            elif mode == "attach":
                btn_tab_a.configure(bg="#1E293B", fg="#94A3B8")
                btn_tab_b.configure(bg="#2563EB", fg="#FFFFFF")
                btn_split.configure(bg="#1E293B", fg="#94A3B8")
                lf_reg_attach.lift(right_host)
                lf_reg_attach.grid(in_=right_host, row=1, column=0, rowspan=2, sticky="nsew")
            else:
                btn_tab_a.configure(bg="#1E293B", fg="#94A3B8")
                btn_tab_b.configure(bg="#1E293B", fg="#94A3B8")
                btn_split.configure(bg="#2563EB", fg="#FFFFFF")
                lf_smart_dwg.lift(right_host)
                lf_reg_attach.lift(right_host)
                lf_smart_dwg.grid(in_=right_host, row=1, column=0, sticky="nsew", pady=(0, 4))
                lf_reg_attach.grid(in_=right_host, row=2, column=0, sticky="nsew", pady=(4, 0))

        btn_tab_a.configure(command=lambda: _switch_deliverables_view("smart"))
        btn_tab_b.configure(command=lambda: _switch_deliverables_view("attach"))
        btn_split.configure(command=lambda: _switch_deliverables_view("split"))

        parent_container.rowconfigure(1, weight=3)
        parent_container.rowconfigure(2, weight=1)
        parent_container.rowconfigure(3, weight=3)

        _switch_deliverables_view("attach")

    btn_show_all = refs.get("btn_show_all")
    if btn_show_all is not None:
        app.after(150, lambda: (btn_show_all.invoke(), _update_status_badge()))



# ==============================================================================
# ADMIN TAB VISIBILITY & USER/PASSWORD MANAGEMENT RESTORER
# ==============================================================================
def _detect_effective_user_role(app) -> str:
    """Reliably determines the active user's role across all app attributes, UI badges, and DB."""
    # 1. Direct dictionary on app (e.g. current_user / auth_user)
    for attr in ("current_user", "auth_user", "logged_in_user", "active_user"):
        val = getattr(app, attr, None)
        if isinstance(val, dict) and val.get("role"):
            return str(val["role"]).strip().upper()
        elif hasattr(val, "role") and getattr(val, "role"):
            return str(val.role).strip().upper()

    # 2. Direct string attribute on app
    for attr in ("user_role", "role", "active_role"):
        val = getattr(app, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip().upper()

    # 3. Inspect the top-right 'Active User: ... [ROLE]' badge text in the live UI
    for w in _walk_widgets(app):
        if isinstance(w, (tk.Label, ttk.Label, tk.Button, ttk.Button)):
            try:
                txt = str(w.cget("text")).strip()
                if "active user:" in txt.lower() and "[" in txt and "]" in txt:
                    role_in_brackets = txt.split("[")[-1].split("]")[0].strip().upper()
                    if role_in_brackets:
                        return role_in_brackets
            except Exception:
                pass

    # 4. Query the database using active_userid
    uid = getattr(app, "active_userid", None)
    if not uid and hasattr(app, "user_settings") and isinstance(app.user_settings, dict):
        uid = app.user_settings.get("active_userid")
    if uid:
        try:
            from models import User
            with session_scope() as s:
                u = s.query(User).filter(User.userid.ilike(str(uid).strip())).first()
                if u and u.role:
                    return str(u.role).strip().upper()
        except Exception:
            pass
        if str(uid).strip().lower() == "admin":
            return "ADMIN"

    # 5. Fallback to user_settings dict
    if hasattr(app, "user_settings") and isinstance(app.user_settings, dict):
        r = app.user_settings.get("user_role") or app.user_settings.get("role")
        if r:
            return str(r).strip().upper()

    return "VIEWER"


def _build_fallback_admin_tab(app, nb) -> ttk.Frame:
    """
    Builds the complete '12. Administration' User & Password Management tab
    if it was not already instantiated in nb.winfo_children().
    """
    from models import User
    from services import BOMService

    colors = getattr(app, "colors", None) or {
        "bg_primary": "#0F172A",
        "bg_surface": "#1E293B",
        "fg_primary": "#F8FAFC",
        "fg_secondary": "#94A3B8",
        "accent_primary": "#38BDF8",
        "accent_success": "#22C55E",
    }

    tab = ttk.Frame(nb, padding=12)
    tab._is_hbom_admin_tab = True

    hdr = ttk.Label(
        tab,
        text="STEP 12: SYSTEM ADMINISTRATION — USER ACCOUNTS, ROLES & PASSWORD SECURITY",
        font=("Segoe UI", 11, "bold"),
        foreground=colors.get("accent_success", "#22C55E"),
    )
    hdr.pack(anchor="w", pady=(0, 10))

    split = ttk.Frame(tab)
    split.pack(fill=tk.BOTH, expand=True)
    split.columnconfigure(0, weight=3)
    split.columnconfigure(1, weight=2)
    split.rowconfigure(0, weight=1)

    # Left: User Directory Table
    lf_dir = ttk.LabelFrame(split, text=" 1. Registered System Users (Select Row to Edit or Reset Password) ", padding=10)
    lf_dir.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

    cols = ("userid", "full_name", "role", "status", "email")
    tree = ttk.Treeview(lf_dir, columns=cols, show="headings", height=16)
    tree.heading("userid", text="User ID")
    tree.heading("full_name", text="Full Name")
    tree.heading("role", text="Security Role")
    tree.heading("status", text="Status")
    tree.heading("email", text="Email Address")

    tree.column("userid", width=110, anchor="w")
    tree.column("full_name", width=170, anchor="w")
    tree.column("role", width=110, anchor="center")
    tree.column("status", width=95, anchor="center")
    tree.column("email", width=210, anchor="w")
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    sb = ttk.Scrollbar(lf_dir, orient=tk.VERTICAL, command=tree.yview)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=sb.set)

    # Right: User Account & Password Editor
    lf_edit = ttk.LabelFrame(split, text=" 2. Create User, Assign Role & Reset Password ", padding=14)
    lf_edit.grid(row=0, column=1, sticky="nsew")
    lf_edit.columnconfigure(1, weight=1)

    ttk.Label(lf_edit, text="User ID (Login Handle):").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
    ent_uid = ttk.Entry(lf_edit)
    ent_uid.grid(row=0, column=1, sticky="ew", pady=6)

    ttk.Label(lf_edit, text="Full Name:").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
    ent_name = ttk.Entry(lf_edit)
    ent_name.grid(row=1, column=1, sticky="ew", pady=6)

    ttk.Label(lf_edit, text="Email Address:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
    ent_email = ttk.Entry(lf_edit)
    ent_email.grid(row=2, column=1, sticky="ew", pady=6)

    ttk.Label(lf_edit, text="Security Role:").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
    cmb_role = ttk.Combobox(lf_edit, values=["VIEWER", "DESIGNER", "APPROVER", "ADMIN"], state="readonly")
    cmb_role.grid(row=3, column=1, sticky="ew", pady=6)
    cmb_role.set("DESIGNER")

    ttk.Label(lf_edit, text="Account Status:").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 8))
    cmb_status = ttk.Combobox(lf_edit, values=["ACTIVE", "DISABLED"], state="readonly")
    cmb_status.grid(row=4, column=1, sticky="ew", pady=6)
    cmb_status.set("ACTIVE")

    ttk.Separator(lf_edit, orient=tk.HORIZONTAL).grid(row=5, column=0, columnspan=2, sticky="ew", pady=12)

    ttk.Label(lf_edit, text="New / Reset Password:").grid(row=6, column=0, sticky="w", pady=6, padx=(0, 8))
    ent_pwd = ttk.Entry(lf_edit, show="*")
    ent_pwd.grid(row=6, column=1, sticky="ew", pady=6)

    ttk.Label(
        lf_edit,
        text="(Leave password blank when updating an existing user's Name/Role/Status\n"
             "to keep their current password, or enter a new password to reset it.)",
        foreground=colors.get("fg_secondary", "#94A3B8"),
        font=("Segoe UI", 8),
    ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def _load_users():
        for iid in tree.get_children():
            tree.delete(iid)
        with session_scope() as s:
            users = s.query(User).order_by(User.userid).all()
            for u in users:
                tree.insert(
                    "",
                    tk.END,
                    values=(
                        u.userid,
                        u.full_name or "",
                        u.role or "VIEWER",
                        u.status or "ACTIVE",
                        u.email or "",
                    ),
                )

    def _on_select(event=None):
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals:
            return
        ent_uid.delete(0, tk.END)
        ent_uid.insert(0, vals[0])
        ent_name.delete(0, tk.END)
        ent_name.insert(0, vals[1])
        cmb_role.set(vals[2])
        cmb_status.set(vals[3])
        ent_email.delete(0, tk.END)
        ent_email.insert(0, vals[4])
        ent_pwd.delete(0, tk.END)

    tree.bind("<<TreeviewSelect>>", _on_select)

    def _clear_form():
        tree.selection_remove(tree.selection())
        ent_uid.delete(0, tk.END)
        ent_name.delete(0, tk.END)
        ent_email.delete(0, tk.END)
        cmb_role.set("DESIGNER")
        cmb_status.set("ACTIVE")
        ent_pwd.delete(0, tk.END)

    def _save_user():
        uid = ent_uid.get().strip().lower()
        name = ent_name.get().strip()
        email = ent_email.get().strip()
        role = cmb_role.get().strip().upper()
        status = cmb_status.get().strip().upper()
        pwd = ent_pwd.get()

        if not uid:
            messagebox.showwarning("Validation", "User ID is required.", parent=app)
            return

        try:
            with session_scope() as s:
                svc = BOMService(s)
                existing = s.query(User).filter(User.userid.ilike(uid)).first()
                if existing:
                    existing.full_name = name or existing.full_name
                    existing.email = email
                    existing.role = role
                    existing.status = status
                    if pwd:
                        if hasattr(svc, "_hash_password"):
                            existing.password_hash = svc._hash_password(pwd)
                        else:
                            import hashlib
                            existing.password_hash = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
                    msg = f"Updated user '{uid}' ({role}, {status})" + (" and reset password." if pwd else ".")
                else:
                    if not pwd:
                        pwd = "demo"
                    if hasattr(svc, "create_user"):
                        svc.create_user(uid, pwd, role=role, full_name=name or uid, email=email, status=status)
                    else:
                        import hashlib
                        new_u = User(
                            userid=uid,
                            password_hash=hashlib.sha256(pwd.encode("utf-8")).hexdigest(),
                            role=role,
                            full_name=name or uid,
                            email=email,
                            status=status,
                        )
                        s.add(new_u)
                    msg = f"Created new user '{uid}' with role '{role}'."
            _load_users()
            ent_pwd.delete(0, tk.END)
            messagebox.showinfo("Administration", msg, parent=app)
        except Exception as e:
            messagebox.showerror("Administration Error", str(e), parent=app)

    def _reset_password_only():
        uid = ent_uid.get().strip().lower()
        pwd = ent_pwd.get()
        if not uid or not pwd:
            messagebox.showwarning("Reset Password", "Select a User ID and enter a New Password first.", parent=app)
            return
        try:
            with session_scope() as s:
                u = s.query(User).filter(User.userid.ilike(uid)).first()
                if not u:
                    raise ValueError(f"User '{uid}' not found.")
                import hashlib
                u.password_hash = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
            ent_pwd.delete(0, tk.END)
            messagebox.showinfo("Password Reset", f"Password for '{uid}' has been updated.", parent=app)
        except Exception as e:
            messagebox.showerror("Password Reset Error", str(e), parent=app)

    btn_row = ttk.Frame(lf_edit)
    btn_row.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    tk.Button(
        btn_row, text="Save / Update User", bg="#2563EB", fg="#FFFFFF",
        font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=5, command=_save_user
    ).pack(side=tk.LEFT, padx=(0, 6))

    tk.Button(
        btn_row, text="Reset Password Only", bg="#059669", fg="#FFFFFF",
        font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=5, command=_reset_password_only
    ).pack(side=tk.LEFT, padx=6)

    tk.Button(
        btn_row, text="Clear / New", bg="#334155", fg="#F8FAFC",
        font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=5, command=_clear_form
    ).pack(side=tk.LEFT, padx=6)

    tk.Button(
        btn_row, text="Refresh List", bg="#334155", fg="#F8FAFC",
        font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=5, command=_load_users
    ).pack(side=tk.RIGHT)

    _load_users()
    return tab


def sync_admin_tab_visibility(app):
    """
    Ensures '12. Administration' is visible when signed in as ADMIN
    and strictly hidden for VIEWER, DESIGNER, and APPROVER.
    """
    nb = getattr(app, "notebook", None) or getattr(app, "nb", None)
    if nb is None:
        for w in _walk_widgets(app):
            if isinstance(w, ttk.Notebook):
                nb = w
                break
    if nb is None:
        return

    role = _detect_effective_user_role(app)
    is_admin = (role == "ADMIN")

    # 1. Locate the Administration tab widget even if it was previously hidden via nb.hide()
    admin_widget = getattr(app, "_admin_tab_widget", None) or getattr(app, "tab_admin", None)
    admin_text = getattr(app, "_admin_tab_text", "12. Administration")

    # Search visible tabs first
    if admin_widget is None:
        for tab_id in nb.tabs():
            try:
                lbl = nb.tab(tab_id, "text")
                if "admin" in lbl.lower() or "12." in lbl.lower():
                    admin_widget = nb.nametowidget(tab_id)
                    admin_text = lbl
                    break
            except Exception:
                pass

    # Search ALL child frames of the Notebook (includes hidden tabs!)
    if admin_widget is None:
        for child in nb.winfo_children():
            if getattr(child, "_is_hbom_admin_tab", False):
                admin_widget = child
                break
            # Inspect labels inside child frame to see if it's the existing Admin tab
            for sub in _walk_widgets(child):
                if isinstance(sub, (tk.Label, ttk.Label, tk.LabelFrame, ttk.LabelFrame)):
                    try:
                        t = str(sub.cget("text")).lower()
                        if "user directory" in t or "system administration" in t or "reset password" in t or "12. administration" in t:
                            if str(child) not in nb.tabs():
                                admin_widget = child
                                break
                    except Exception:
                        pass
            if admin_widget is not None:
                break

    # If still None and user is ADMIN, build the fallback Administration tab
    if admin_widget is None and is_admin:
        admin_widget = _build_fallback_admin_tab(app, nb)
        admin_text = "12. Administration"

    if admin_widget is not None:
        app._admin_tab_widget = admin_widget
        app._admin_tab_text = admin_text
        try:
            if is_admin:
                if str(admin_widget) not in nb.tabs():
                    nb.add(admin_widget, text=admin_text)
                nb.tab(admin_widget, state="normal")
            else:
                if str(admin_widget) in nb.tabs():
                    if str(nb.select()) == str(admin_widget) and len(nb.tabs()) > 1:
                        nb.select(0)
                    nb.hide(admin_widget)
        except Exception as e:
            print(f"Admin tab sync note: {e}")
