"""
Polished Enterprise PyQt6 Desktop GUI for Engineering BOM Management (v1.0).
Includes:
- Interactive QSplitter dividers across Tabs 4, 5, 12, and Help Manual
- Elevated Card QGroupBox styling, rounded controls, and cyan focus rings
- Modern bottom-accent indicator on the 12-tab navigation bar
- Subtle zebra striping, row hover illumination, monospace code columns,
  automatic numeric/center alignment, and true numeric sorting on all QTreeWidgets
- Built-in Clear (×) buttons on all search inputs
- Branded 28x28 header logo (hbom-icon.jpeg) and live bottom QStatusBar
"""

import os
import sys
import csv
import datetime
import hashlib
import subprocess
from typing import Optional, List
from sqlalchemy import select

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QPixmap, QPainter, QPen, QBrush, QPolygonF,
    QTextCharFormat, QTextCursor
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QPushButton, QLineEdit, QTextEdit,
    QComboBox, QRadioButton, QCheckBox, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QFileDialog, QMessageBox, QColorDialog,
    QListWidget, QSplitter, QFrame, QButtonGroup, QAbstractItemView,
    QTextBrowser, QMenu, QStatusBar
)

from settings_manager import (
    load_user_settings, save_user_settings, get_active_drawing_sizes,
    get_active_bulk_uoms, get_envelope_unit_hint, THEME_PRESETS, DEFAULT_SETTINGS, USER_ROLES
)
from help_data import (
    HELP_TOPICS, HELP_TEXT, HELP_FLOWCHARTS, MASTER_PROCESS_STAGES,
    render_topic_html, render_combined_html
)
from database import session_scope
from services import BOMService, detect_pdf_page_count
from pdf_generator import generate_eco_pdf_file
from pn_generator import (
    preview_next_part_number, get_default_seed_for_type,
    preview_next_eco_number, get_default_seed_for_eco,
    parse_starting_code, sync_sequence_with_seed
)
from models import (
    ECO_TYPES, EngineeringChange, Part, PartPendingUpdate, BOMItem,
    ECODrawingRegistrationItem, ECOAttachment, DrawingRevisionHistory,
    DrawingSupportingDoc, UserAccount
)
from config import (
    BULK_UOM_OPTIONS, DRAWING_SHEET_SIZES, DRAWING_TYPES,
    FINISH_OPTIONS, SUPPLY_CLASS_OPTIONS, STARTING_CODES
)

STATUS_COLORS = {
    "REQUESTED": ("#A855F7", "#F3E8FF"),
    "OPEN": ("#38BDF8", "#E0F2FE"),
    "PENDING_APPROVAL": ("#F59E0B", "#FEF3C7"),
    "APPROVED": ("#10B981", "#D1FAE5"),
    "RELEASED": ("#22C55E", "#DCFCE7"),
}

# Column key classifications for automatic alignment & monospace typography
RIGHT_ALIGN_KEYS = {"find", "qty", "ext_qty", "unit_weight", "ext_weight", "qty_per", "new_cnt", "mod_cnt", "bom_cnt", "sheets", "q1", "q2", "q3", "q4", "id"}
CENTER_ALIGN_KEYS = {"cond", "uom", "rev", "size", "dwg_size", "chk", "status", "reg_status", "dtype", "source_type", "type"}
MONO_FONT_KEYS = {"pn", "tree_pn", "eco", "dwg_no", "rev", "cond", "find", "qty", "ext_qty", "unit_weight", "ext_weight", "qty_per", "q1", "q2", "q3", "q4", "created", "released", "created_at", "released_at", "date"}


class FormattedTreeItem(QTreeWidgetItem):
    """
    Custom QTreeWidgetItem that provides:
    1. True numeric sorting when clicking column headers (e.g. Find #, Qty, Weight, ID).
    2. Automatic monospace font for Part Numbers, ECOs, Revisions, and numeric columns.
    3. Automatic Right-Alignment for quantities/weights and Center-Alignment for codes/revisions.
    """
    def __init__(self, values: List[str]):
        super().__init__(values)
        self._styled = False

    def apply_column_formatting(self, tree: QTreeWidget):
        if self._styled or tree is None:
            return
        self._styled = True
        col_keys = getattr(tree, "_col_keys", [])
        mono_font = QFont("Consolas", 9)
        for c, key in enumerate(col_keys):
            if c >= self.columnCount():
                break
            if key in MONO_FONT_KEYS:
                self.setFont(c, mono_font)
            if key in RIGHT_ALIGN_KEYS:
                self.setTextAlignment(c, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            elif key in CENTER_ALIGN_KEYS:
                self.setTextAlignment(c, int(Qt.AlignmentFlag.AlignCenter))

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        tree = self.treeWidget()
        if tree is None:
            return super().__lt__(other)
        self.apply_column_formatting(tree)
        if isinstance(other, FormattedTreeItem):
            other.apply_column_formatting(tree)
        col = tree.sortColumn()
        t1 = self.text(col).strip()
        t2 = other.text(col).strip()
        try:
            v1 = float(t1.split()[0].replace(",", ""))
            v2 = float(t2.split()[0].replace(",", ""))
            return v1 < v2
        except Exception:
            return t1.lower() < t2.lower()


# Use FormattedTreeItem everywhere QTreeWidgetItem is instantiated
QTreeWidgetItem = FormattedTreeItem


def _fmt_dt(dt_val) -> str:
    if not dt_val:
        return "-"
    try:
        return dt_val.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt_val)[:16]


def _find_logo_path() -> Optional[str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "hbom-icon.jpeg"),
        os.path.join(base_dir, "hbom-icon.jpg"),
        os.path.join(base_dir, "hbom_logo.jpg"),
        os.path.join(base_dir, "hbom_logo.jpeg"),
        os.path.join(base_dir, "hbom-icon.png"),
        "hbom-icon.jpeg",
        "hbom_logo.jpg",
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def build_app_stylesheet(colors: dict) -> str:
    bg_pri = colors.get("bg_primary", "#0F172A")
    bg_sec = colors.get("bg_secondary", "#1E293B")
    bg_sur = colors.get("bg_surface", "#1E293B")
    fg_pri = colors.get("fg_primary", "#F8FAFC")
    fg_sec = colors.get("fg_secondary", "#94A3B8")
    acc_pri = colors.get("accent_primary", "#38BDF8")
    acc_suc = colors.get("accent_success", "#22C55E")

    return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {bg_pri};
            color: {fg_pri};
            font-family: "Segoe UI", "Ubuntu", sans-serif;
            font-size: 9pt;
        }}
        QGroupBox {{
            background-color: {bg_pri};
            border: 1px solid #334155;
            border-radius: 6px;
            margin-top: 14px;
            padding: 10px 8px 8px 8px;
            font-weight: bold;
            color: {acc_suc};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 1px 6px;
            color: {acc_suc};
            background-color: {bg_pri};
            border-radius: 3px;
        }}
        QTabWidget::pane {{
            border: 1px solid #334155;
            border-radius: 4px;
            background-color: {bg_pri};
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: #152033;
            color: {fg_sec};
            padding: 7px 13px;
            font-weight: bold;
            border: 1px solid #26354D;
            border-bottom: 2px solid transparent;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 3px;
        }}
        QTabBar::tab:hover {{
            background-color: #1E2D45;
            color: #E2E8F0;
        }}
        QTabBar::tab:selected {{
            background-color: {bg_sur};
            color: #FFFFFF;
            border: 1px solid #38BDF8;
            border-bottom: 3px solid #38BDF8;
        }}
        QLineEdit, QComboBox, QTextEdit {{
            background-color: {bg_sur};
            color: {fg_pri};
            border: 1px solid #475569;
            border-radius: 4px;
            padding: 4px 7px;
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
            border: 1px solid #38BDF8;
            background-color: #162235;
        }}
        QLineEdit:disabled, QComboBox:disabled {{
            background-color: #0B1120;
            color: #64748B;
            border: 1px solid #1E293B;
        }}
        QComboBox::drop-down {{
            border-left: 1px solid #475569;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {bg_sur};
            color: {fg_pri};
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
            border: 1px solid #38BDF8;
        }}
        QTreeWidget {{
            background-color: {bg_sec};
            alternate-background-color: #162032;
            color: {fg_pri};
            border: 1px solid #334155;
            border-radius: 5px;
            gridline-color: #26354D;
            outline: none;
        }}
        QTreeWidget::item {{
            padding: 4px 5px;
            border-bottom: 1px solid #1A2639;
        }}
        QTreeWidget::item:hover {{
            background-color: #24344D;
        }}
        QTreeWidget::item:selected {{
            background-color: #2563EB;
            color: #FFFFFF;
        }}
        QHeaderView::section {{
            background-color: #0F172A;
            color: #38BDF8;
            font-weight: bold;
            padding: 6px 7px;
            border: none;
            border-right: 1px solid #26354D;
            border-bottom: 2px solid #334155;
        }}
        QHeaderView::section:hover {{
            background-color: #1E293B;
            color: #FFFFFF;
        }}
        QSplitter::handle {{
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 2px;
        }}
        QSplitter::handle:horizontal {{
            width: 5px;
            margin: 2px 3px;
        }}
        QSplitter::handle:vertical {{
            height: 5px;
            margin: 3px 2px;
        }}
        QSplitter::handle:hover {{
            background-color: #38BDF8;
            border-color: #38BDF8;
        }}
        QPushButton {{
            background-color: #334155;
            color: {fg_pri};
            border: 1px solid #475569;
            border-radius: 4px;
            padding: 5px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: #475569;
            border-color: #64748B;
            color: #FFFFFF;
        }}
        QPushButton:disabled {{
            background-color: #1E293B;
            color: #64748B;
            border: 1px solid #334155;
        }}
        QPushButton[role="designer"] {{
            background-color: #2563EB;
            color: #FFFFFF;
            font-weight: bold;
            border: 1px solid #3B82F6;
        }}
        QPushButton[role="designer"]:hover {{
            background-color: #1D4ED8;
            border-color: #60A5FA;
        }}
        QPushButton[role="designer"]:disabled {{
            background-color: #1E293B;
            color: #64748B;
            border: 1px solid #334155;
        }}
        QPushButton[role="approver"] {{
            background-color: #059669;
            color: #FFFFFF;
            font-weight: bold;
            border: 1px solid #10B981;
        }}
        QPushButton[role="approver"]:hover {{
            background-color: #047857;
            border-color: #34D399;
        }}
        QPushButton[role="admin"] {{
            background-color: #7C3AED;
            color: #FFFFFF;
            font-weight: bold;
            border: 1px solid #8B5CF6;
        }}
        QPushButton[role="admin"]:hover {{
            background-color: #6D28D9;
            border-color: #A78BFA;
        }}
        QMenu {{
            background-color: {bg_sur};
            color: {fg_pri};
            border: 1px solid #38BDF8;
            border-radius: 4px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 20px;
            border-radius: 3px;
        }}
        QMenu::item:selected {{
            background-color: #2563EB;
            color: #FFFFFF;
        }}
        QStatusBar {{
            background-color: #0B1120;
            color: {fg_sec};
            border-top: 1px solid #26354D;
            font-size: 8.5pt;
        }}
        QRadioButton, QCheckBox {{
            color: {fg_pri};
            spacing: 7px;
            font-weight: bold;
        }}
        QRadioButton::indicator {{
            width: 15px;
            height: 15px;
            border-radius: 8px;
            border: 2px solid #94A3B8;
            background-color: #1E293B;
        }}
        QRadioButton::indicator:hover {{
            border: 2px solid #38BDF8;
            background-color: #334155;
        }}
        QRadioButton::indicator:checked {{
            width: 11px;
            height: 11px;
            border-radius: 8px;
            border: 4px solid #38BDF8;
            background-color: #F8FAFC;
        }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border-radius: 3px;
            border: 2px solid #94A3B8;
            background-color: #1E293B;
        }}
        QCheckBox::indicator:hover {{
            border: 2px solid #38BDF8;
            background-color: #334155;
        }}
        QCheckBox::indicator:checked {{
            border: 2px solid #38BDF8;
            background-color: #2563EB;
        }}
    """


def make_btn(text: str, role: str = "viewer", cmd=None) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("role", role)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if cmd is not None:
        b.clicked.connect(cmd)
    return b


def make_search_entry(width: int = 200, placeholder: str = "Wildcard search (* or ?)...") -> QLineEdit:
    ent = QLineEdit()
    if width:
        ent.setFixedWidth(width)
    ent.setPlaceholderText(placeholder)
    ent.setClearButtonEnabled(True)
    return ent


def insert_colored_eco_report_qt(txt_widget: QTextEdit, report_text: str):
    txt_widget.setReadOnly(False)
    txt_widget.clear()
    cursor = txt_widget.textCursor()

    styles = {
        "TAG_ADDED": ("#4ADE80", "#0D2818", True, 8),
        "TAG_REMOVED": ("#F87171", "#2D1215", True, 8),
        "TAG_CHANGED": ("#60A5FA", "#0F243C", True, 8),
        "TAG_TBL_HDR": ("#F8FAFC", "#263349", True, 8),
        "TAG_SECTION": ("#FBBF24", None, True, 9),
        "TAG_HEADER": ("#38BDF8", None, True, 9),
        "TAG_NORMAL": ("#CBD5E1", None, False, 8),
    }

    for line in report_text.splitlines():
        s = line.strip()
        tag = "TAG_NORMAL"
        if s.startswith("| Act |") or s.startswith("| St  |"):
            tag = "TAG_TBL_HDR"
        elif s.startswith("| +"):
            tag = "TAG_ADDED"
        elif s.startswith("| -"):
            tag = "TAG_REMOVED"
        elif s.startswith("| ~") or s.startswith("^--"):
            tag = "TAG_CHANGED"
        elif s[:2] in ("1.", "2.", "3.", "4.", "5.") or s.startswith("PARENT ASSEMBLY:"):
            tag = "TAG_SECTION"
        elif s.startswith("===") or s.startswith("hBOM"):
            tag = "TAG_HEADER"

        fg_hex, bg_hex, is_bold, pt = styles[tag]
        fmt = QTextCharFormat()
        font = QFont("Consolas", pt)
        font.setBold(is_bold)
        fmt.setFont(font)
        fmt.setForeground(QColor(fg_hex))
        if bg_hex:
            fmt.setBackground(QColor(bg_hex))
        cursor.insertText(line + "\n", fmt)

    txt_widget.setReadOnly(True)
    txt_widget.moveCursor(QTextCursor.MoveOperation.Start)


def open_file_externally(filepath: str, parent_win=None):
    if not filepath or not os.path.exists(filepath):
        QMessageBox.warning(
            parent_win,
            "File Path Info",
            f"Recorded Vault Path:\n{filepath}\n\n(Local file not found on disk.)"
        )
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(filepath)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", filepath])
        else:
            subprocess.Popen(["xdg-open", filepath])
    except Exception as e:
        QMessageBox.critical(parent_win, "Open Error", str(e))


def make_tab_header(parent_layout: QVBoxLayout, app, title_text: str, help_key: str):
    bar = QFrame()
    bar.setStyleSheet(
        f"background-color: {app.colors['bg_secondary']}; "
        f"border: 1px solid #26354D; border-left: 4px solid {app.colors['accent_success']}; border-radius: 4px;"
    )
    bar.setFixedHeight(36)
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(10, 2, 8, 2)

    lbl = QLabel(f"{title_text}")
    lbl.setStyleSheet(
        f"color: {app.colors['accent_success']}; font-weight: bold; font-size: 9.5pt; border: none;"
    )
    lay.addWidget(lbl)
    lay.addStretch(1)

    btn_help = make_btn("? Help & Process Flowchart", "viewer", lambda: HelpDialogQt(app, help_key).exec())
    lay.addWidget(btn_help)

    parent_layout.addWidget(bar)
    return bar


def export_tree_to_csv_qt(tree: QTreeWidget, default_filename: str = "export.csv", parent_win=None):
    if tree is None:
        QMessageBox.warning(parent_win, "No Data", "No table data to export.")
        return
    path, _ = QFileDialog.getSaveFileName(
        parent_win, "Export Table to CSV", default_filename, "CSV Files (*.csv);;All Files (*.*)"
    )
    if not path:
        return

    col_cnt = tree.columnCount()
    headers = [tree.headerItem().text(c) for c in range(col_cnt)]
    rows_out: List[List[str]] = []

    def _collect(parent_item: Optional[QTreeWidgetItem]):
        cnt = tree.topLevelItemCount() if parent_item is None else parent_item.childCount()
        for i in range(cnt):
            item = tree.topLevelItem(i) if parent_item is None else parent_item.child(i)
            rows_out.append([item.text(c) for c in range(col_cnt)])
            _collect(item)

    _collect(None)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows_out)
    QMessageBox.information(parent_win, "CSV Exported", f"Exported {len(rows_out)} rows to:\n{path}")


def setup_tree_columns(tree: QTreeWidget, col_defs: List[tuple]):
    tree._col_keys = [c[0] for c in col_defs]
    tree.setColumnCount(len(col_defs))
    tree.setHeaderLabels([c[1] for c in col_defs])
    tree.setRootIsDecorated(False)
    tree.setAlternatingRowColors(True)
    tree.setUniformRowHeights(True)
    tree.setSortingEnabled(True)
    tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    hdr = tree.header()
    hdr.setStretchLastSection(True)
    for idx, c in enumerate(col_defs):
        key, _label, w = c[0], c[1], c[2]
        hdr.setSectionResizeMode(idx, QHeaderView.ResizeMode.Interactive)
        tree.setColumnWidth(idx, w)
        if key in RIGHT_ALIGN_KEYS:
            tree.headerItem().setTextAlignment(idx, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        elif key in CENTER_ALIGN_KEYS:
            tree.headerItem().setTextAlignment(idx, int(Qt.AlignmentFlag.AlignCenter))

    orig_add = tree.addTopLevelItem

    def _formatted_add(item: QTreeWidgetItem):
        if isinstance(item, FormattedTreeItem):
            item.apply_column_formatting(tree)
        orig_add(item)

    tree.addTopLevelItem = _formatted_add


# ==============================================================================
# POPUP DIALOGS (HELP, SEARCH, ECO REQUEST, SUMMARY REPORT, NOUN/MAT DB)
# ==============================================================================
class MasterProcessFlowCanvasQt(QWidget):
    """
    Renders the 6-stage Overall hBOM Engineering Process Flowchart and
    highlights the exact stage(s) where the current Help topic / Tab fits in.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(152)
        self.active_indices: List[int] = [0]
        self.focus_note: str = ""

    def set_highlight(self, active_indices: List[int], focus_note: str = ""):
        self.active_indices = list(active_indices or [0])
        self.focus_note = focus_note
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = max(self.width(), 780)

        p.fillRect(0, 0, self.width(), self.height(), QColor("#0B1120"))
        p.setPen(QPen(QColor("#1E293B"), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

        stages = MASTER_PROCESS_STAGES
        n = len(stages)
        margin_x = 18
        avail_w = self.width() - 2 * margin_x
        box_w = min(145, int(avail_w / (n + 0.65)))
        gap = int((avail_w - n * box_w) / max(1, n - 1))
        top_y = 14
        box_h = 96
        mid_y = top_y + box_h // 2

        min_active = min(self.active_indices) if self.active_indices else 0
        all_selected = (len(self.active_indices) == n)

        for idx, (title, subtitle, tabs_label) in enumerate(stages):
            x1 = margin_x + idx * (box_w + gap)
            x2 = x1 + box_w

            is_here = (idx in self.active_indices)
            is_prior = (idx < min_active) and not is_here

            if all_selected:
                fill_col = "#1E3A8A"
                border_col = "#38BDF8"
                hdr_bg = "#0F172A"
                hdr_fg = "#38BDF8"
                badge_txt = "★ OVERVIEW ★"
                badge_col = "#FACC15"
                border_w = 2
            elif is_here:
                fill_col = "#1E3A8A"
                border_col = "#38BDF8"
                hdr_bg = "#38BDF8"
                hdr_fg = "#0F172A"
                badge_txt = "★ YOU ARE HERE ★"
                badge_col = "#FACC15"
                border_w = 3
                dash_pen = QPen(QColor("#38BDF8"), 1, Qt.PenStyle.DashLine)
                p.setPen(dash_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(x1 - 4, top_y - 4, box_w + 8, box_h + 8)
            elif is_prior:
                fill_col = "#064E3B"
                border_col = "#22C55E"
                hdr_bg = "#0F172A"
                hdr_fg = "#F8FAFC"
                badge_txt = "✓ PRIOR STAGE"
                badge_col = "#4ADE80"
                border_w = 2
            else:
                fill_col = "#1E293B"
                border_col = "#475569"
                hdr_bg = "#0F172A"
                hdr_fg = "#94A3B8"
                badge_txt = "○ NEXT STAGE"
                badge_col = "#64748B"
                border_w = 1

            p.setPen(QPen(QColor(border_col), border_w))
            p.setBrush(QBrush(QColor(fill_col)))
            p.drawRect(x1, top_y, box_w, box_h)

            p.fillRect(x1 + 1, top_y + 1, box_w - 2, 22, QColor(hdr_bg))

            p.setPen(QColor(hdr_fg))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(QRectF(x1 + 2, top_y, box_w - 4, 22), Qt.AlignmentFlag.AlignCenter, title)

            p.setPen(QColor("#E2E8F0" if (is_here or is_prior or all_selected) else "#94A3B8"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRectF(x1 + 2, top_y + 25, box_w - 4, 20), Qt.AlignmentFlag.AlignCenter, subtitle)

            p.setPen(QColor(badge_col))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(QRectF(x1 + 2, top_y + 46, box_w - 4, 20), Qt.AlignmentFlag.AlignCenter, badge_txt)

            p.setPen(QColor("#F8FAFC" if is_here else "#CBD5E1"))
            p.setFont(QFont("Consolas", 8, QFont.Weight.Bold if is_here else QFont.Weight.Normal))
            p.drawText(QRectF(x1 + 2, top_y + 68, box_w - 4, 20), Qt.AlignmentFlag.AlignCenter, tabs_label)

            if idx < n - 1:
                ax1 = x2 + 3
                ax2 = x1 + box_w + gap - 3
                arrow_col = QColor("#22C55E" if idx < min_active else ("#38BDF8" if is_here else "#475569"))
                p.setPen(QPen(arrow_col, 2))
                p.drawLine(ax1, mid_y, ax2, mid_y)
                poly = QPolygonF([QPointF(ax2, mid_y), QPointF(ax2 - 8, mid_y - 4), QPointF(ax2 - 8, mid_y + 4)])
                p.setBrush(QBrush(arrow_col))
                p.drawPolygon(poly)

        if self.focus_note:
            p.setPen(QColor("#38BDF8"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(QRectF(margin_x, top_y + box_h + 12, w - 2 * margin_x, 20), Qt.AlignmentFlag.AlignCenter, self.focus_note)


class HelpDialogQt(QDialog):
    def __init__(self, parent, initial_topic: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("hBOM — Interactive Engineering Operations Manual & Process Flowchart")
        self.resize(1260, 840)
        self.setMinimumSize(980, 640)
        self.colors = getattr(parent, "colors", DEFAULT_SETTINGS["colors"])
        self._all_topics = list(HELP_TOPICS.keys())
        self._build_ui()
        selected = self._match_initial_topic(initial_topic)
        self._select_topic(selected)

    def _match_initial_topic(self, hint: Optional[str]) -> str:
        if not hint:
            return self._all_topics[0]
        mapping = {
            "TAB_1_NOUN": "01. Tab 1: Product Setup",
            "TAB_2_MAT": "03. Tab 3: Part Setup",
            "TAB_6_PROD": "01. Tab 1: Product Setup",
            "TAB_5_SUB": "02. Tab 2: Prod Subassembly",
            "TAB_4_PART": "03. Tab 3: Part Setup",
            "TAB_7_BOM": "04. Tab 4: BOM Builder",
            "TAB_3_ECO": "05. Tab 5: ECO Manager",
            "TAB_8_DWG_REG": "06. Tab 6: Drawing Registration",
            "TAB_9_LOOKUP": "07. Tab 7: BOM Lookup",
            "TAB_10_WU": "08. Tab 8: Where-Used",
            "TAB_11_COMPARE": "09. Tab 9: Compare BOMs",
            "TAB_12_DWG_VIEW": "10. Tab 10: Drawing Viewer",
            "TAB_13_SETTINGS": "11. Tab 11: Settings",
        }
        mapped = mapping.get(hint, hint).lower()
        for t in self._all_topics:
            if mapped in t.lower():
                return t
        return self._all_topics[0]

    def _build_ui(self):
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        lbl = QLabel("hBOM Interactive Engineering Guide — Overall Process Tie-In & Illustrated Reference")
        lbl.setStyleSheet(f"color: {self.colors['accent_primary']}; font-size: 11pt; font-weight: bold;")
        top.addWidget(lbl)
        top.addStretch(1)

        top.addWidget(QLabel("Search Keyword:"))
        self.ent_search = make_search_entry(220, "Filter chapters & highlight...")
        self.ent_search.textChanged.connect(self._on_search_change)
        top.addWidget(self.ent_search)

        top.addWidget(make_btn("View Complete Manual (All Tabs)", "designer", self._show_combined_manual))
        top.addWidget(make_btn("Close Manual", "viewer", self.accept))
        v.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_gb = QGroupBox(" Manual Chapters && Application Tabs ")
        left_gb.setMinimumWidth(260)
        ll = QVBoxLayout(left_gb)
        self.lst_topics = QListWidget()
        for t in self._all_topics:
            self.lst_topics.addItem(t)
        self.lst_topics.currentTextChanged.connect(self._on_topic_selected)
        ll.addWidget(self.lst_topics)
        splitter.addWidget(left_gb)

        right_widget = QWidget()
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(0, 0, 0, 0)

        self.master_flow_gb = QGroupBox(" Overall hBOM Engineering Process (Current Tab Highlighted: ★ YOU ARE HERE ★) ")
        mflay = QVBoxLayout(self.master_flow_gb)
        mflay.setContentsMargins(6, 6, 6, 6)
        self.master_canvas = MasterProcessFlowCanvasQt(self)
        mflay.addWidget(self.master_canvas)
        right_col.addWidget(self.master_flow_gb)

        right_gb = QGroupBox(" Step-by-Step Directions, Field && Button Reference && Engineering Concept Links ")
        rl = QVBoxLayout(right_gb)
        self.txt_content = QTextBrowser()
        self.txt_content.setOpenExternalLinks(True)
        self.txt_content.setStyleSheet("background-color: #1E293B; border: 1px solid #334155; border-radius: 4px; padding: 6px;")
        rl.addWidget(self.txt_content)
        right_col.addWidget(right_gb, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        v.addWidget(splitter, 1)

    def _select_topic(self, topic_name: str):
        items = self.lst_topics.findItems(topic_name, Qt.MatchFlag.MatchExactly)
        if items:
            self.lst_topics.setCurrentItem(items[0])
        self._render_topic(topic_name)

    def _on_topic_selected(self, text: str):
        if text:
            self._render_topic(text)

    def _render_topic(self, topic_name: str, highlight_term: str = ""):
        spec = HELP_FLOWCHARTS.get(topic_name)
        if spec:
            self.master_canvas.set_highlight(
                spec.get("master_active_indices", [0]),
                spec.get("master_focus_note", "")
            )
        q = highlight_term or self.ent_search.text().strip()
        self.txt_content.setHtml(render_topic_html(topic_name, highlight_term=q))

    def _show_combined_manual(self):
        self.lst_topics.clearSelection()
        spec = HELP_FLOWCHARTS.get("00. System Overview & Login Security")
        if spec:
            self.master_canvas.set_highlight(spec["master_active_indices"], spec["master_focus_note"])
        self.txt_content.setHtml(render_combined_html(highlight_term=self.ent_search.text().strip()))

    def _on_search_change(self, q: str):
        q = q.strip().lower()
        self.lst_topics.clear()
        matched = []
        for t, body in HELP_TOPICS.items():
            if not q or q in t.lower() or q in body.lower():
                self.lst_topics.addItem(t)
                matched.append(t)
        if matched:
            self.lst_topics.setCurrentRow(0)
            self._render_topic(matched[0], highlight_term=q)
        else:
            self.master_canvas.set_highlight([], "No matching topic")
            self.txt_content.setHtml(f"<h3 style='color:#F59E0B;'>No manual topics matched '{q}'.</h3>")


class PartSearchDialogQt(QDialog):
    def __init__(self, parent, target_entry: Optional[QLineEdit] = None, part_types=None, on_select_callback=None, title_override=None, initial_query: str = ""):
        super().__init__(parent)
        self.target_entry = target_entry
        self.part_types = part_types
        self.on_select_callback = on_select_callback
        self.colors = parent.colors

        self.setWindowTitle(title_override or "Wildcard Part Search (Use '*' or '?', e.g. 1AF*5)")
        self.resize(980, 480)

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Wildcard Search (PN / Noun / Desc, e.g. 1AF*5):"))
        self.ent_query = make_search_entry(260, "e.g. 1AF*5 or *BOLT*")
        top.addWidget(self.ent_query)

        seed_q = initial_query.strip()
        if not seed_q and target_entry is not None:
            seed_q = target_entry.text().strip()
        if seed_q:
            self.ent_query.setText(seed_q)
        self.ent_query.returnPressed.connect(lambda: self._populate(force_all=False))

        top.addWidget(make_btn("Search", "viewer", lambda: self._populate(force_all=False)))
        top.addWidget(make_btn("Show All", "viewer", lambda: self._populate(force_all=True)))
        top.addStretch(1)
        top.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree, "part_search_results.csv", self)))
        lay.addLayout(top)

        self.lbl_status = QLabel("Type a search pattern above (supports '*' wildcard, e.g. '1AF*5') or click 'Show All'.")
        self.lbl_status.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        lay.addWidget(self.lbl_status)

        self.tree = QTreeWidget()
        setup_tree_columns(self.tree, [
            ("pn", "Part Number", 110), ("name", "Noun, Description", 220),
            ("type", "Category", 130), ("cond", "Cond", 50),
            ("finish", "Finish", 65), ("envelope", "Envelope (LXWXH)", 105),
            ("uom", "UOM", 45), ("status", "Status", 85), ("rev", "Rev", 45),
            ("created", "Created Date", 115)
        ])
        self.tree.itemDoubleClicked.connect(lambda _item, _col: self._confirm())
        lay.addWidget(self.tree, 1)

        btm = QHBoxLayout()
        btm.addStretch(1)
        btm.addWidget(make_btn("Cancel", "viewer", self.reject))
        btm.addWidget(make_btn("Select Highlighted Number", "viewer", self._confirm))
        lay.addLayout(btm)

        if seed_q:
            self._populate(force_all=False)
        self.ent_query.setFocus()
        self.ent_query.selectAll()

    def _populate(self, force_all: bool = False):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        q = "*" if force_all else self.ent_query.text().strip()
        if not q:
            self.lbl_status.setText("Table cleared. Type a search pattern or click 'Show All'.")
            self.tree.setSortingEnabled(True)
            return
        with session_scope() as s:
            results = BOMService(s).search_parts(q, part_types=self.part_types)
            for p in results:
                self.tree.addTopLevelItem(QTreeWidgetItem([
                    p.part_number, p.standard_name, p.part_type,
                    p.condition_code or "-", p.finish, p.envelope or "-",
                    p.uom, p.release_status, p.revision, _fmt_dt(getattr(p, "created_at", None))
                ]))
        self.tree.setSortingEnabled(True)
        self.lbl_status.setText(f"Found {len(results)} matching record(s) for '{q}'.")

    def _confirm(self):
        items = self.tree.selectedItems()
        if not items:
            return
        pn = items[0].text(0)
        if self.target_entry is not None:
            self.target_entry.setText(pn)
        if self.on_select_callback:
            try:
                self.on_select_callback(pn)
            except TypeError:
                self.on_select_callback()
        self.accept()


class ECORequestDialogQt(QDialog):
    def __init__(self, parent, is_designer: bool):
        super().__init__(parent)
        self.parent_app = parent
        self.is_designer = is_designer
        self.colors = parent.colors
        self.created_eco_no: Optional[str] = None

        self.setWindowTitle("Submit New ECO Request (ECR)" if is_designer else "Pull New Official ECO Number")
        self.resize(540, 320)

        lay = QVBoxLayout(self)
        gb_title = " Request ECO Number (Requires Approver/Admin to Issue) " if is_designer else " Pull Official Open ECO Number "
        frm = QGroupBox(gb_title)
        grid = QGridLayout(frm)

        grid.addWidget(QLabel("ECO Category:"), 0, 0)
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(list(ECO_TYPES))
        self.cmb_type.setCurrentText("PRODUCTION")
        self.cmb_type.setFixedWidth(160)
        grid.addWidget(self.cmb_type, 0, 1, Qt.AlignmentFlag.AlignLeft)

        grid.addWidget(QLabel("Proposed ECO Title:"), 1, 0)
        self.ent_title = QLineEdit()
        grid.addWidget(self.ent_title, 1, 1)

        grid.addWidget(QLabel("Engineering Reason\n/ Justification:"), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.txt_reason = QTextEdit()
        grid.addWidget(self.txt_reason, 2, 1)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch(1)
        btn_bar.addWidget(make_btn("Cancel", "viewer", self.reject))
        btn_label = "Submit ECO Request (ECR)" if is_designer else "Pull Official ECO #"
        btn_bar.addWidget(make_btn(btn_label, "designer", self._submit))
        grid.addLayout(btn_bar, 3, 0, 1, 2)

        lay.addWidget(frm)
        self.ent_title.setFocus()

    def _submit(self):
        title = self.ent_title.text().strip()
        reason = self.txt_reason.toPlainText().strip()
        if not title or not reason:
            QMessageBox.warning(self, "Required Fields", "Please enter both a Proposed Title and an Engineering Reason.")
            return
        try:
            with session_scope() as s:
                eco = BOMService(s).pull_eco_number(self.cmb_type.currentText(), title=title, reason=reason)
                self.created_eco_no = eco.eco_number
                st = eco.status
            self.parent_app.refresh_all_data()
            self.parent_app.cmb_active_eco.setCurrentText(self.created_eco_no)
            self.parent_app._load_selected_eco_into_editor()
            self.parent_app.notebook.setCurrentWidget(self.parent_app.tab_ecos)
            self.accept()
            if st == "REQUESTED":
                QMessageBox.information(self.parent_app, "ECO Request Submitted", f"Submitted Request: {self.created_eco_no} (Status: REQUESTED).")
            else:
                QMessageBox.information(self.parent_app, "Pulled ECO Number", f"Pulled Official ECO Number: {self.created_eco_no} (Status: OPEN).")
        except Exception as e:
            QMessageBox.critical(self, "Permission / ECO Error", str(e))


class ECOSummaryReportModalQt(QDialog):
    def __init__(self, parent, eco_number: str, report_text: str):
        super().__init__(parent)
        self.colors = parent.colors
        self.eco_number = eco_number
        self.report_text = report_text
        self.setWindowTitle(f"ECO Summary Report — {eco_number}")
        self.resize(1180, 660)

        lay = QVBoxLayout(self)
        self.txt = QTextEdit()
        self.txt.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        insert_colored_eco_report_qt(self.txt, report_text)
        lay.addWidget(self.txt, 1)

        btm = QHBoxLayout()
        btm.addWidget(make_btn("Export Formatted PDF Report...", "viewer", self._export_pdf))
        btm.addWidget(make_btn("Export Plain .TXT...", "viewer", self._export_txt))
        btm.addStretch(1)
        btm.addWidget(make_btn("Close", "viewer", self.accept))
        lay.addLayout(btm)

    def _export_pdf(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{self.eco_number}_Summary_Report.pdf", "PDF Document (*.pdf)")
        if p:
            generate_eco_pdf_file(p, self.eco_number, self.report_text)
            QMessageBox.information(self, "PDF Generated", f"Saved formatted PDF report to:\n{p}")
            open_file_externally(p, self)

    def _export_txt(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export TXT", f"{self.eco_number}_Summary_Report.txt", "Text Files (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.report_text)
            QMessageBox.information(self, "Exported", f"Saved plain text report to:\n{p}")


class NounDatabaseDialogQt(QDialog):
    def __init__(self, app, target_combobox: Optional[QComboBox] = None):
        super().__init__(app)
        self.app = app
        self.target_combobox = target_combobox
        self.colors = app.colors
        self.setWindowTitle("Master Noun Dictionary Database")
        self.resize(920, 540)

        lay = QVBoxLayout(self)
        make_tab_header(lay, self.app, "MASTER NOUN DICTIONARY DATABASE", "TAB_1_NOUN")

        frm = QGroupBox(" Add Approved Noun && Short Definition ")
        grid = QGridLayout(frm)
        grid.addWidget(QLabel("Approved Noun (e.g., BRACKET):"), 0, 0)
        self.ent_noun_name = QLineEdit()
        self.ent_noun_name.setFixedWidth(240)
        grid.addWidget(self.ent_noun_name, 0, 1, Qt.AlignmentFlag.AlignLeft)

        grid.addWidget(QLabel("Short Definition (Required):"), 1, 0)
        self.ent_noun_def = QLineEdit()
        self.ent_noun_def.setFixedWidth(460)
        grid.addWidget(self.ent_noun_def, 1, 1, Qt.AlignmentFlag.AlignLeft)

        grid.addWidget(make_btn("Register Noun", "designer", self._save_noun), 2, 1, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(2, 1)
        lay.addWidget(frm)

        btm = QGroupBox(" Master Noun Dictionary (Double-Click Row to Select into Form) ")
        blay = QVBoxLayout(btm)

        tbar = QHBoxLayout()
        tbar.addWidget(QLabel("Wildcard Search (e.g. BRACKET*):"))
        self.ent_noun_search = make_search_entry(200, "e.g. BRACKET*")
        self.ent_noun_search.returnPressed.connect(lambda: self._populate_nouns(force_all=False))
        tbar.addWidget(self.ent_noun_search)
        tbar.addWidget(make_btn("Search", "viewer", lambda: self._populate_nouns(force_all=False)))
        tbar.addWidget(make_btn("Show All", "viewer", lambda: self._populate_nouns(force_all=True)))
        tbar.addWidget(make_btn("Clear", "viewer", self._clear_noun_search))
        self.lbl_noun_count = QLabel("(Enter a search above to display records)")
        self.lbl_noun_count.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        tbar.addWidget(self.lbl_noun_count)
        tbar.addStretch(1)
        tbar.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_nouns, "noun_dictionary.csv", self)))
        blay.addLayout(tbar)

        self.tree_nouns = QTreeWidget()
        setup_tree_columns(self.tree_nouns, [("id", "ID", 65), ("name", "Approved Noun", 220), ("definition", "Short Definition", 540)])
        self.tree_nouns.itemDoubleClicked.connect(self._on_row_double_click)
        blay.addWidget(self.tree_nouns, 1)
        lay.addWidget(btm, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(make_btn("Close Window", "viewer", self.accept))
        lay.addLayout(footer)
        self.ent_noun_search.setFocus()

    def _clear_noun_search(self):
        self.ent_noun_search.clear()
        self.tree_nouns.clear()
        self.lbl_noun_count.setText("(Enter a search above to display records)")

    def _populate_nouns(self, force_all: bool = False):
        self.tree_nouns.setSortingEnabled(False)
        self.tree_nouns.clear()
        q = "*" if force_all else self.ent_noun_search.text().strip()
        if not q:
            self.lbl_noun_count.setText("(Enter a search above to display records)")
            self.tree_nouns.setSortingEnabled(True)
            return
        with session_scope() as s:
            rows = BOMService(s).search_nouns(q)
            for n in rows:
                self.tree_nouns.addTopLevelItem(QTreeWidgetItem([str(n.id), n.name, n.short_definition]))
            self.lbl_noun_count.setText(f"Showing {len(rows)} record(s)")
        self.tree_nouns.setSortingEnabled(True)

    def _save_noun(self):
        try:
            with session_scope() as s:
                noun = BOMService(s).register_noun(self.ent_noun_name.text(), self.ent_noun_def.text())
                saved_name = noun.name
            self.ent_noun_name.clear()
            self.ent_noun_def.clear()
            self.app.refresh_all_data()
            self._populate_nouns(force_all=True)
            if self.target_combobox is not None:
                self.target_combobox.setEditText(f"{saved_name}, ")
            QMessageBox.information(self, "Noun Registered", f"Noun '{saved_name}' registered successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Noun Error", str(e))

    def _on_row_double_click(self, item: QTreeWidgetItem, _col: int):
        if self.target_combobox is None:
            return
        noun_name = item.text(1)
        current_val = self.target_combobox.currentText()
        if "," in current_val:
            _, desc_part = current_val.split(",", 1)
            self.target_combobox.setEditText(f"{noun_name}, {desc_part.strip()}")
        else:
            self.target_combobox.setEditText(f"{noun_name}, ")
        self.target_combobox.setFocus()
        self.accept()


class MaterialDatabaseDialogQt(QDialog):
    def __init__(self, app, target_combobox: Optional[QComboBox] = None):
        super().__init__(app)
        self.app = app
        self.target_combobox = target_combobox
        self.colors = app.colors
        self.setWindowTitle("Master Materials Database")
        self.resize(920, 540)

        lay = QVBoxLayout(self)
        make_tab_header(lay, self.app, "MASTER MATERIALS DATABASE", "TAB_2_MAT")

        frm = QGroupBox(" Add Approved Material && Specification ")
        grid = QGridLayout(frm)
        grid.addWidget(QLabel("Material Name:"), 0, 0)
        self.ent_mat_name = QLineEdit()
        self.ent_mat_name.setFixedWidth(280)
        grid.addWidget(self.ent_mat_name, 0, 1, Qt.AlignmentFlag.AlignLeft)

        grid.addWidget(QLabel("Standard / Specification:"), 1, 0)
        self.ent_mat_spec = QLineEdit()
        self.ent_mat_spec.setFixedWidth(280)
        grid.addWidget(self.ent_mat_spec, 1, 1, Qt.AlignmentFlag.AlignLeft)

        grid.addWidget(make_btn("Register Material", "designer", self._save_material), 2, 1, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(2, 1)
        lay.addWidget(frm)

        btm = QGroupBox(" Master Materials List (Double-Click Row to Select into Form) ")
        blay = QVBoxLayout(btm)

        tbar = QHBoxLayout()
        tbar.addWidget(QLabel("Wildcard Search (e.g. *STEEL*):"))
        self.ent_mat_search = make_search_entry(200, "e.g. *STEEL* or *4140*")
        self.ent_mat_search.returnPressed.connect(lambda: self._populate_mats(force_all=False))
        tbar.addWidget(self.ent_mat_search)
        tbar.addWidget(make_btn("Search", "viewer", lambda: self._populate_mats(force_all=False)))
        tbar.addWidget(make_btn("Show All", "viewer", lambda: self._populate_mats(force_all=True)))
        tbar.addWidget(make_btn("Clear", "viewer", self._clear_mat_search))
        self.lbl_mat_count = QLabel("(Enter a search above to display records)")
        self.lbl_mat_count.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        tbar.addWidget(self.lbl_mat_count)
        tbar.addStretch(1)
        tbar.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_mats, "materials_database.csv", self)))
        blay.addLayout(tbar)

        self.tree_mats = QTreeWidget()
        setup_tree_columns(self.tree_mats, [("id", "ID", 65), ("name", "Material Name", 320), ("spec", "Specification", 380)])
        self.tree_mats.itemDoubleClicked.connect(self._on_row_double_click)
        blay.addWidget(self.tree_mats, 1)
        lay.addWidget(btm, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(make_btn("Close Window", "viewer", self.accept))
        lay.addLayout(footer)
        self.ent_mat_search.setFocus()

    def _clear_mat_search(self):
        self.ent_mat_search.clear()
        self.tree_mats.clear()
        self.lbl_mat_count.setText("(Enter a search above to display records)")

    def _populate_mats(self, force_all: bool = False):
        self.tree_mats.setSortingEnabled(False)
        self.tree_mats.clear()
        q = "*" if force_all else self.ent_mat_search.text().strip()
        if not q:
            self.lbl_mat_count.setText("(Enter a search above to display records)")
            self.tree_mats.setSortingEnabled(True)
            return
        with session_scope() as s:
            rows = BOMService(s).search_materials(q)
            for m in rows:
                self.tree_mats.addTopLevelItem(QTreeWidgetItem([str(m.id), m.name, m.specification or "-"]))
            self.lbl_mat_count.setText(f"Showing {len(rows)} record(s)")
        self.tree_mats.setSortingEnabled(True)

    def _save_material(self):
        try:
            with session_scope() as s:
                mat = BOMService(s).register_material(self.ent_mat_name.text(), self.ent_mat_spec.text() or None)
                saved_name = mat.name
            self.ent_mat_name.clear()
            self.ent_mat_spec.clear()
            self.app.refresh_all_data()
            self._populate_mats(force_all=True)
            if self.target_combobox is not None:
                self.target_combobox.setCurrentText(saved_name)
            QMessageBox.information(self, "Material Registered", f"Material '{saved_name}' registered successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Material Error", str(e))

    def _on_row_double_click(self, item: QTreeWidgetItem, _col: int):
        if self.target_combobox is None:
            return
        mat_name = item.text(1)
        idx = self.target_combobox.findText(mat_name)
        if idx >= 0:
            self.target_combobox.setCurrentIndex(idx)
        else:
            self.target_combobox.setCurrentText(mat_name)
        self.accept()


# ==============================================================================
# GRAPHICAL ECO WORKFLOW & APPROVAL CENTER DIALOG
# ==============================================================================
class FlowchartCanvasQt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(235)
        self.eco_data: Optional[dict] = None

    def set_data(self, data: Optional[dict]):
        self.eco_data = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = max(self.width(), 900)
        h = max(self.height(), 235)

        p.fillRect(0, 0, self.width(), self.height(), QColor("#0B1120"))
        p.setPen(QPen(QColor("#1E293B"), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

        if not self.eco_data:
            p.setPen(QColor("#94A3B8"))
            f = QFont("Segoe UI", 11)
            f.setItalic(True)
            p.setFont(f)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Select or Pull an ECO to view its graphical lifecycle flowchart.")
            return

        data = self.eco_data
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
        avail_w = self.width() - 2 * margin_x
        box_w = min(158, int(avail_w / 5.9))
        gap = int((avail_w - 5 * box_w) / 4)
        top_y = 32
        box_h = 112
        mid_y = top_y + box_h // 2

        box_centers = []
        for idx, (_st_key, title, subtitle, actor, dt_str) in enumerate(stages):
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
                dash_pen = QPen(QColor("#38BDF8"), 1, Qt.PenStyle.DashLine)
                p.setPen(dash_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(x1 - 4, top_y - 4, box_w + 8, box_h + 8)
            else:
                fill_col = "#1E293B"
                border_col = "#475569"
                border_w = 1
                badge_txt = "○ UPCOMING"
                badge_col = "#94A3B8"

            p.setPen(QPen(QColor(border_col), border_w))
            p.setBrush(QBrush(QColor(fill_col)))
            p.drawRect(x1, top_y, box_w, box_h)

            hdr_col = border_col if idx == curr_idx else "#0F172A"
            p.fillRect(x1 + 1, top_y + 1, box_w - 2, 25, QColor(hdr_col))

            p.setPen(QColor("#0F172A" if idx == curr_idx else "#F8FAFC"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.drawText(QRectF(x1, top_y, box_w, 26), Qt.AlignmentFlag.AlignCenter, title)

            p.setPen(QColor("#E2E8F0"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRectF(x1, top_y + 30, box_w, 22), Qt.AlignmentFlag.AlignCenter, subtitle)

            p.setPen(QColor(badge_col))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(QRectF(x1, top_y + 52, box_w, 22), Qt.AlignmentFlag.AlignCenter, badge_txt)

            meta_line = ""
            if idx <= curr_idx:
                if actor and dt_str and dt_str != "-":
                    meta_line = f"{actor} • {dt_str[:10]}"
                elif actor:
                    meta_line = f"By: {actor}"
                elif dt_str and dt_str != "-":
                    meta_line = dt_str[:10]
            p.setPen(QColor("#CBD5E1"))
            p.setFont(QFont("Consolas", 8))
            p.drawText(QRectF(x1, top_y + 78, box_w, 22), Qt.AlignmentFlag.AlignCenter, meta_line)

            if idx < len(stages) - 1:
                ax1 = x2 + 3
                ax2 = x1 + box_w + gap - 3
                arrow_col = QColor("#22C55E" if idx < curr_idx else "#475569")
                p.setPen(QPen(arrow_col, 3))
                p.drawLine(ax1, mid_y, ax2, mid_y)
                poly = QPolygonF([QPointF(ax2, mid_y), QPointF(ax2 - 9, mid_y - 5), QPointF(ax2 - 9, mid_y + 5)])
                p.setBrush(QBrush(arrow_col))
                p.drawPolygon(poly)

        _, _, cx_open = box_centers[1]
        _, _, cx_pend = box_centers[2]
        _, _, cx_appr = box_centers[3]
        loop_y = top_y + box_h + 44
        loop_active = status in ("PENDING_APPROVAL", "APPROVED")
        loop_col = QColor("#F59E0B" if loop_active else "#475569")
        pen_style = Qt.PenStyle.SolidLine if loop_active else Qt.PenStyle.DashLine
        p.setPen(QPen(loop_col, 2, pen_style))
        p.drawLine(cx_pend, top_y + box_h + 2, cx_pend, loop_y)
        p.drawLine(cx_appr, top_y + box_h + 2, cx_appr, loop_y)
        p.drawLine(cx_appr, loop_y, cx_open, loop_y)
        p.drawLine(cx_open, loop_y, cx_open, top_y + box_h + 3)

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold if loop_active else QFont.Weight.Normal))
        p.drawText(
            QRectF(cx_open, loop_y + 2, cx_appr - cx_open, 22),
            Qt.AlignmentFlag.AlignCenter,
            "↩ Reject / Return to OPEN (Re-opens ECO for additional engineering edits)"
        )


class ECOWorkflowDialogQt(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.colors = app.colors
        self.setWindowTitle("hBOM — ECO Graphical Workflow & Approval Center")
        self.resize(1040, 690)
        self.setMinimumSize(960, 640)

        self.active_eco_num = self._detect_initial_eco()
        self._eco_map = {}
        self._current_eco_data = None
        self._build_ui()
        self._refresh_eco_list()
        self._load_and_render_eco(self.active_eco_num)

    def _get_user_role(self) -> str:
        raw = self.app.user_settings.get("user_role", "VIEWER")
        return str(raw).split()[0].strip().upper()

    def _get_user_display(self) -> str:
        uid = self.app.user_settings.get("active_userid", "user")
        return f"{uid} [{self._get_user_role()}]"

    def _detect_initial_eco(self) -> str:
        val = self.app.cmb_active_eco.currentText().strip()
        if val:
            return val.split()[0].strip()
        sel = self.app.tree_ecos.selectedItems()
        if sel:
            return sel[0].text(0).strip()
        with session_scope() as s:
            first_eco = s.query(EngineeringChange).order_by(EngineeringChange.created_at.desc()).first()
            return first_eco.eco_number if first_eco else ""

    def _build_ui(self):
        outer = QVBoxLayout(self)

        top_bar = QFrame()
        top_bar.setStyleSheet(f"background-color: {self.colors['bg_surface']}; border: 1px solid #334155; border-radius: 5px;")
        tlay = QHBoxLayout(top_bar)
        lbl_t = QLabel("Target ECO / ECR:")
        lbl_t.setStyleSheet(f"color: {self.colors['accent_primary']}; font-weight: bold;")
        tlay.addWidget(lbl_t)

        self.cmb_eco_selector = QComboBox()
        self.cmb_eco_selector.setFixedWidth(210)
        self.cmb_eco_selector.currentTextChanged.connect(self._on_popup_eco_selected)
        tlay.addWidget(self.cmb_eco_selector)

        self.lbl_eco_headline = QLabel("")
        self.lbl_eco_headline.setStyleSheet("font-weight: bold; font-size: 10pt;")
        tlay.addWidget(self.lbl_eco_headline, 1)

        lbl_role = QLabel(f"Signed In: {self._get_user_display()}")
        lbl_role.setStyleSheet("background-color: #1E3A8A; color: #FFFFFF; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        tlay.addWidget(lbl_role)
        outer.addWidget(top_bar)

        flow_gb = QGroupBox(" Graphical ECO Lifecycle Flowchart (Current Step Highlighted) ")
        flay = QVBoxLayout(flow_gb)
        self.canvas = FlowchartCanvasQt(self)
        flay.addWidget(self.canvas)
        outer.addWidget(flow_gb)

        mid_split = QSplitter(Qt.Orientation.Horizontal)
        gate_gb = QGroupBox(" Pre-Flight Gate && Readiness Audit ")
        glay = QVBoxLayout(gate_gb)
        self.txt_gates = QTextEdit()
        self.txt_gates.setReadOnly(True)
        self.txt_gates.setFont(QFont("Consolas", 10))
        glay.addWidget(self.txt_gates)
        mid_split.addWidget(gate_gb)

        reason_gb = QGroupBox(" Engineering Change Reason && Audit Trail ")
        rlay = QVBoxLayout(reason_gb)
        self.txt_reason_audit = QTextEdit()
        self.txt_reason_audit.setReadOnly(True)
        self.txt_reason_audit.setFont(QFont("Consolas", 10))
        rlay.addWidget(self.txt_reason_audit)
        mid_split.addWidget(reason_gb)
        outer.addWidget(mid_split, 1)

        action_gb = QGroupBox(" Available Workflow Actions for Your Role ")
        alay = QHBoxLayout(action_gb)
        self.lbl_role_guidance = QLabel("")
        self.lbl_role_guidance.setStyleSheet(f"color: {self.colors['fg_secondary']}; font-style: italic;")
        alay.addWidget(self.lbl_role_guidance, 1)

        self.btn_container = QWidget()
        self.btn_lay = QHBoxLayout(self.btn_container)
        self.btn_lay.setContentsMargins(0, 0, 0, 0)
        alay.addWidget(self.btn_container)
        outer.addWidget(action_gb)

    def _refresh_eco_list(self):
        self.cmb_eco_selector.blockSignals(True)
        self.cmb_eco_selector.clear()
        with session_scope() as s:
            ecos = s.query(EngineeringChange).order_by(EngineeringChange.created_at.desc()).all()
            items = [f"{e.eco_number}  [{e.status}]" for e in ecos]
            self._eco_map = {f"{e.eco_number}  [{e.status}]": e.eco_number for e in ecos}
            self.cmb_eco_selector.addItems(items)
            if self.active_eco_num:
                for label, num in self._eco_map.items():
                    if num == self.active_eco_num:
                        self.cmb_eco_selector.setCurrentText(label)
                        break
            elif items:
                self.cmb_eco_selector.setCurrentIndex(0)
                self.active_eco_num = self._eco_map[items[0]]
        self.cmb_eco_selector.blockSignals(False)

    def _on_popup_eco_selected(self, sel: str):
        if not sel:
            return
        eco_num = self._eco_map.get(sel, sel.split()[0].strip())
        if eco_num:
            self.app.cmb_active_eco.setCurrentText(eco_num)
            self.app._load_selected_eco_into_editor()
            self._load_and_render_eco(eco_num)

    def _load_and_render_eco(self, eco_num: str):
        self.active_eco_num = eco_num
        if not eco_num:
            self.lbl_eco_headline.setText("No ECO Selected — Pull or Request an ECO first.")
            self.canvas.set_data(None)
            return

        with session_scope() as s:
            eco = s.get(EngineeringChange, eco_num)
            if not eco:
                self.lbl_eco_headline.setText(f"ECO '{eco_num}' not found.")
                self.canvas.set_data(None)
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
        self.lbl_eco_headline.setText(f"{data['eco_number']} ({data['eco_type']}) — {data['title']}")
        self.canvas.set_data(data)
        self._populate_gates_and_audit(data)
        self._build_role_action_buttons(data)
        self.app._update_eco_status_badge(data["eco_number"], data["status"])

    def _populate_gates_and_audit(self, d: dict):
        has_title = bool(d["title"] and d["title"] != "(Untitled ECO)")
        has_reason = bool(d["reason"].strip())
        g1 = "[✓] Gate 1 — Title & Engineering Reason: Populated" if (has_title and has_reason) else "[!] Gate 1 — Title & Engineering Reason: Incomplete"

        total_changes = d["new_pts"] + d["mod_pts"] + d["bom_rows"]
        g2 = f"[✓] Gate 2 — Staged Engineering Changes: {total_changes} total item(s)" if total_changes > 0 else "[i] Gate 2 — Staged Engineering Changes: 0 items attached so far"

        if d["dwg_total"] == 0:
            g3 = "[✓] Gate 3 — Drawing Checklist: 0 Required Drawings (Ready)"
        elif d["dwg_reg"] >= d["dwg_total"]:
            g3 = f"[✓] Gate 3 — Drawing Checklist: {d['dwg_reg']}/{d['dwg_total']} Registered (Complete)"
        else:
            g3 = f"[!] Gate 3 — Drawing Checklist: {d['dwg_reg']}/{d['dwg_total']} Registered\n      (All required drawings must be registered in Tab 6 before Release)"

        gate_txt = (
            f"{g1}\n{g2}\n"
            f"      • New Parts Created      : {d['new_pts']}\n"
            f"      • Modified Parts Staged  : {d['mod_pts']}\n"
            f"      • BOM Markup Rows Staged : {d['bom_rows']}\n"
            f"      • Attached Reference Docs: {d['att_count']}\n"
            f"{g3}"
        )
        self.txt_gates.setPlainText(gate_txt)

        audit_txt = (
            f"ENGINEERING REASON / DESCRIPTION:\n{d['reason'] or '(No reason entered)'}\n\n"
            f"SIGN-OFF & TIMESTAMP AUDIT:\n"
            f"• Created By   : {d['created_by']} ({d['created_at']})\n"
            f"• Submitted At : {d['submitted_at']}\n"
            f"• Approved By  : {d['approved_by'] or 'Pending'} ({d['approved_at']})\n"
            f"• Released By  : {d['released_by'] or 'Pending'} ({d['released_at']})"
        )
        self.txt_reason_audit.setPlainText(audit_txt)

    def _build_role_action_buttons(self, d: dict):
        while self.btn_lay.count():
            item = self.btn_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        status = d["status"]
        role = self._get_user_role()
        can_design = role in ("DESIGNER", "ENGINEER", "APPROVER", "ADMIN")
        can_approve = role in ("APPROVER", "ADMIN")

        self.btn_lay.addWidget(make_btn("📄 Summary PDF...", "viewer", self.app._show_eco_summary_report))

        if status == "REQUESTED":
            if can_approve:
                self.lbl_role_guidance.setText("This request is awaiting Approver sign-off to issue an editable OPEN ECO number.")
                self.btn_lay.addWidget(make_btn("✓ Approve Request (Issue Open ECO #)", "approver", lambda: self._run_transition(self.app._approve_ecr_action)))
            else:
                self.lbl_role_guidance.setText(f"Your role ({role}) cannot approve ECR requests. An APPROVER or ADMIN must issue the ECO.")
                b = make_btn("✓ Approve Request (Requires Approver)", "viewer")
                b.setEnabled(False)
                self.btn_lay.addWidget(b)

        elif status == "OPEN":
            if can_design:
                self.lbl_role_guidance.setText("ECO is OPEN for authoring. When parts, BOM markups, and drawings are ready, submit for approval.")
                self.btn_lay.addWidget(make_btn("➜ Submit ECO for Approval", "designer", lambda: self._run_transition(self.app._submit_eco_action)))
            else:
                self.lbl_role_guidance.setText("Read-Only Viewer mode: A Designer, Approver, or Admin must submit this ECO.")
                b = make_btn("➜ Submit ECO for Approval (Requires Designer)", "viewer")
                b.setEnabled(False)
                self.btn_lay.addWidget(b)

        elif status == "PENDING_APPROVAL":
            if can_approve:
                self.lbl_role_guidance.setText("ECO is Pending Approval. Review the summary & gates above, then Approve or Reject/Return to Open.")
                self.btn_lay.addWidget(make_btn("↩ Reject / Return to Open", "designer", lambda: self._run_transition(self.app._reject_eco_action)))
                self.btn_lay.addWidget(make_btn("✓ Approve ECO", "approver", lambda: self._run_transition(self.app._approve_eco_action)))
            else:
                self.lbl_role_guidance.setText("ECO is frozen in PENDING_APPROVAL. Waiting on an APPROVER or ADMIN to review.")
                b = make_btn("✓ Approve ECO (Requires Approver)", "viewer")
                b.setEnabled(False)
                self.btn_lay.addWidget(b)

        elif status == "APPROVED":
            if can_approve:
                self.lbl_role_guidance.setText("ECO is APPROVED! Click 'Release Approved ECO' to promote all changes to production.")
                self.btn_lay.addWidget(make_btn("↩ Reject / Return to Open", "designer", lambda: self._run_transition(self.app._reject_eco_action)))
                self.btn_lay.addWidget(make_btn("🚀 Release Approved ECO to Production", "approver", lambda: self._run_transition(self.app._release_eco)))
            else:
                self.lbl_role_guidance.setText("ECO is APPROVED and awaiting final production release by an APPROVER or ADMIN.")
                b = make_btn("🚀 Release Approved ECO (Requires Approver)", "viewer")
                b.setEnabled(False)
                self.btn_lay.addWidget(b)

        elif status == "RELEASED":
            self.lbl_role_guidance.setText("✓ This ECO is officially RELEASED to production and permanently locked.")

        self.btn_lay.addWidget(make_btn("Close Window", "viewer", self.accept))

    def _run_transition(self, fn):
        self.app.cmb_active_eco.setCurrentText(self.active_eco_num)
        fn()
        new_active = self.app.cmb_active_eco.currentText().split(" | ")[0].strip()
        self.active_eco_num = new_active or self.active_eco_num
        self._refresh_eco_list()
        self._load_and_render_eco(self.active_eco_num)


# ==============================================================================
# TABS 1, 2, 3: CATEGORY SETUP PANEL
# ==============================================================================
class CategorySetupPanelQt(QWidget):
    def __init__(self, app, part_type: str, help_key: str):
        super().__init__(app)
        self.app = app
        self.part_type = part_type
        self.help_key = help_key
        self.colors = app.colors
        self.is_regular_part = (part_type == "PART")
        self.is_prod_sub = (part_type == "PRODUCTION SUBASSEMBLY")
        self.default_seed = get_default_seed_for_type(part_type)
        self._build_ui()

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(6, 6, 6, 6)
        make_tab_header(
            main_lay, self.app,
            f"{self.part_type} SETUP — ADD NEW, CLONE, OR MODIFY EXISTING (TIED TO OPEN ECO)",
            self.help_key
        )

        v_split = QSplitter(Qt.Orientation.Vertical)

        top_widget = QWidget()
        form_wrap = QHBoxLayout(top_widget)
        form_wrap.setContentsMargins(0, 0, 0, 0)
        form_wrap.setSpacing(10)

        col1 = QGroupBox(" 1. Identification, Nomenclature && Material ")
        g1 = QGridLayout(col1)
        g1.setVerticalSpacing(8)
        g1.setHorizontalSpacing(10)

        g1.addWidget(QLabel("Workflow Mode:"), 0, 0)
        act_f = QHBoxLayout()
        self.rb_add = QRadioButton("Add New")
        self.rb_mod = QRadioButton("Modify Existing")
        self.rb_add.setChecked(True)
        self.mode_grp = QButtonGroup(self)
        self.mode_grp.addButton(self.rb_add)
        self.mode_grp.addButton(self.rb_mod)
        self.rb_add.toggled.connect(self._on_mode_change)
        act_f.addWidget(self.rb_add)
        act_f.addWidget(self.rb_mod)
        act_f.addWidget(make_btn("Clone Existing...", "designer", self._open_clone_dialog))
        act_f.addStretch(1)
        g1.addLayout(act_f, 0, 1)

        g1.addWidget(QLabel("Starting Code Seed:"), 1, 0)
        sf = QHBoxLayout()
        self.ent_seed = QLineEdit(self.default_seed)
        self.ent_seed.setFixedWidth(150)
        self.ent_seed.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_seed.textChanged.connect(self.update_seed_preview)
        sf.addWidget(self.ent_seed)
        self.lbl_next_pn = QLabel("Next PN: ...")
        self.lbl_next_pn.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        sf.addWidget(self.lbl_next_pn)
        sf.addStretch(1)
        g1.addLayout(sf, 1, 1)

        g1.addWidget(QLabel("Target Number (Modify):"), 2, 0)
        mf = QHBoxLayout()
        self.ent_existing_pn = QLineEdit()
        self.ent_existing_pn.setFixedWidth(150)
        self.ent_existing_pn.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_existing_pn.setEnabled(False)
        self.ent_existing_pn.returnPressed.connect(self._load_existing_record)
        mf.addWidget(self.ent_existing_pn)
        self.btn_find_existing = make_btn(
            "Find...", "viewer",
            lambda: PartSearchDialogQt(
                self.app, self.ent_existing_pn, part_types=[self.part_type],
                on_select_callback=lambda _pn=None: self._load_existing_record()
            ).exec()
        )
        self.btn_find_existing.setEnabled(False)
        mf.addWidget(self.btn_find_existing)
        mf.addStretch(1)
        g1.addLayout(mf, 2, 1)

        g1.addWidget(QLabel("Noun, Description:"), 3, 0)
        nd_f = QHBoxLayout()
        self.cmb_noun_desc = QComboBox()
        self.cmb_noun_desc.setEditable(True)
        self.cmb_noun_desc.setFixedWidth(300)
        self.cmb_noun_desc.activated.connect(self._on_noun_picked)
        nd_f.addWidget(self.cmb_noun_desc)
        nd_f.addWidget(make_btn("Noun DB...", "designer", lambda: NounDatabaseDialogQt(self.app, self.cmb_noun_desc).exec()))
        nd_f.addStretch(1)
        g1.addLayout(nd_f, 3, 1)

        mat_lbl = "Material (Required):" if self.is_regular_part else "Material [Optional]:"
        g1.addWidget(QLabel(mat_lbl), 4, 0)
        mtf = QHBoxLayout()
        self.cmb_mat = QComboBox()
        self.cmb_mat.setFixedWidth(240)
        mtf.addWidget(self.cmb_mat)
        mtf.addWidget(make_btn("Mat DB...", "designer", lambda: MaterialDatabaseDialogQt(self.app, self.cmb_mat).exec()))
        mtf.addStretch(1)
        g1.addLayout(mtf, 4, 1)

        g1.addWidget(QLabel("Material Size (Stock):"), 5, 0)
        self.ent_mat_size = QLineEdit()
        self.ent_mat_size.setFixedWidth(310)
        g1.addWidget(self.ent_mat_size, 5, 1, Qt.AlignmentFlag.AlignLeft)

        form_wrap.addWidget(col1, 1)

        col2 = QGroupBox(" 2. Physical Specs, Lifecycle && ECO Governance ")
        g2 = QGridLayout(col2)
        g2.setVerticalSpacing(8)
        g2.setHorizontalSpacing(10)

        g2.addWidget(QLabel("Finish & Dwg Size:"), 0, 0)
        ff = QHBoxLayout()
        self.cmb_finish = QComboBox()
        self.cmb_finish.addItems(FINISH_OPTIONS)
        self.cmb_finish.setCurrentText("RAW" if self.is_regular_part else "PAINTED")
        self.cmb_finish.setFixedWidth(105)
        ff.addWidget(self.cmb_finish)

        ff.addWidget(QLabel("Dwg Size:"))
        self.cmb_dwg_size = QComboBox()
        self.cmb_dwg_size.addItems(DRAWING_SHEET_SIZES)
        self.cmb_dwg_size.setCurrentText("D")
        self.cmb_dwg_size.setFixedWidth(75)
        ff.addWidget(self.cmb_dwg_size)

        self.ent_cond_code = QLineEdit()
        self.ent_cond_code.setFixedWidth(55)
        self.ent_cond_code.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        if self.is_prod_sub:
            lbl_c = QLabel("3-Digit Cond:")
            lbl_c.setStyleSheet(f"color: {self.colors['accent_success']};")
            ff.addWidget(lbl_c)
            ff.addWidget(self.ent_cond_code)
        else:
            self.ent_cond_code.setVisible(False)
        ff.addStretch(1)
        g2.addLayout(ff, 0, 1)

        g2.addWidget(QLabel("Envelope (LXWXH):"), 1, 0)
        env_f = QHBoxLayout()
        self.ent_envelope = QLineEdit()
        self.ent_envelope.setFixedWidth(125)
        env_f.addWidget(self.ent_envelope)
        env_f.addWidget(QLabel("Wt:"))
        self.ent_unit_weight = QLineEdit("0.0")
        self.ent_unit_weight.setFixedWidth(60)
        env_f.addWidget(self.ent_unit_weight)
        env_f.addWidget(QLabel("Src:"))
        self.cmb_source_type = QComboBox()
        self.cmb_source_type.addItems(["MAKE", "BUY", "PHANTOM"])
        self.cmb_source_type.setCurrentText("PHANTOM" if self.is_prod_sub else "MAKE")
        self.cmb_source_type.setFixedWidth(95)
        env_f.addWidget(self.cmb_source_type)
        env_f.addStretch(1)
        g2.addLayout(env_f, 1, 1)

        g2.addWidget(QLabel("Unit of Measure:"), 2, 0)
        uf = QHBoxLayout()
        self.chk_is_bulk = QCheckBox("Bulk item (Oil, Loctite, Tape)")
        self.cmb_uom = QComboBox()
        self.cmb_uom.addItems(["EA"])
        self.cmb_uom.setCurrentText("EA")
        self.cmb_uom.setEnabled(False)
        self.cmb_uom.setFixedWidth(75)
        if self.is_regular_part:
            self.chk_is_bulk.toggled.connect(self._on_bulk_toggled)
            uf.addWidget(self.chk_is_bulk)
            uf.addWidget(QLabel("UOM:"))
            uf.addWidget(self.cmb_uom)
        else:
            self.chk_is_bulk.setVisible(False)
            self.cmb_uom.setVisible(False)
            lbl_ea = QLabel("1 EA (Locked for Assemblies & Products)")
            lbl_ea.setStyleSheet(f"color: {self.colors['accent_success']};")
            uf.addWidget(lbl_ea)
        uf.addStretch(1)
        g2.addLayout(uf, 2, 1)

        g2.addWidget(QLabel("Lifecycle & Revision:"), 3, 0)
        pf = QHBoxLayout()
        self.chk_is_proto = QCheckBox("Prototype (Numbered Rev 1, 2...)")
        self.chk_is_proto.toggled.connect(self._on_proto_toggled)
        pf.addWidget(self.chk_is_proto)
        pf.addWidget(QLabel("Rev:"))
        self.ent_rev = QLineEdit("A")
        self.ent_rev.setFixedWidth(50)
        self.ent_rev.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        pf.addWidget(self.ent_rev)
        pf.addStretch(1)
        g2.addLayout(pf, 3, 1)

        g2.addWidget(QLabel("Tied to Open ECO:"), 4, 0)
        ecf = QHBoxLayout()
        self.cmb_eco = QComboBox()
        self.cmb_eco.setFixedWidth(240)
        ecf.addWidget(self.cmb_eco)
        ecf.addWidget(make_btn("Pull ECO #...", "designer", self.app.quick_pull_eco))
        ecf.addStretch(1)
        g2.addLayout(ecf, 4, 1)

        self.btn_submit = make_btn(f"Save New {self.part_type.title()} (Pending ECO)", "designer", self._submit_form)
        g2.addWidget(self.btn_submit, 5, 1, Qt.AlignmentFlag.AlignLeft)

        form_wrap.addWidget(col2, 1)
        v_split.addWidget(top_widget)

        bottom = QGroupBox(f" {self.part_type} Catalog (Double-Click Any Row to Load into Modify Mode) ")
        blay = QVBoxLayout(bottom)

        tbar = QHBoxLayout()
        tbar.addWidget(QLabel("Wildcard Search:"))
        self.ent_cat_search = make_search_entry(220, f"e.g. {self.default_seed[:3]}* or *BRACKET*")
        self.ent_cat_search.returnPressed.connect(lambda: self.run_catalog_search(force_all=False))
        tbar.addWidget(self.ent_cat_search)
        tbar.addWidget(make_btn("Search", "viewer", lambda: self.run_catalog_search(force_all=False)))
        tbar.addWidget(make_btn("Show All", "viewer", lambda: self.run_catalog_search(force_all=True)))
        tbar.addWidget(make_btn("Clear", "viewer", self._clear_catalog_search))
        self.lbl_cat_count = QLabel("(Enter a search above to display records)")
        self.lbl_cat_count.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        tbar.addWidget(self.lbl_cat_count)
        tbar.addStretch(1)
        tbar.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree, f"{self.part_type.lower().replace(' ', '_')}_catalog.csv", self)))
        blay.addLayout(tbar)

        self.tree = QTreeWidget()
        setup_tree_columns(self.tree, [
            ("pn", "Number", 105),
            ("name", "Noun, Description", 210),
            ("cond", "Cond", 45),
            ("finish", "Finish", 60),
            ("envelope", "Envelope (LXWXH)", 100),
            ("mat_size", "Material Size", 105),
            ("dwg_size", "Dwg Size", 55),
            ("uom", "UOM", 50),
            ("rev", "Rev", 50),
            ("status", "Status", 85),
            ("eco", "ECO #", 80),
            ("created_at", "Created Date", 115),
            ("released_at", "Released Date", 115),
            ("pending_mod", "Staged Modification", 150),
        ])
        self.tree.itemDoubleClicked.connect(self._on_table_double_click)
        blay.addWidget(self.tree, 1)
        v_split.addWidget(bottom)
        v_split.setStretchFactor(0, 0)
        v_split.setStretchFactor(1, 1)
        main_lay.addWidget(v_split, 1)

    def _on_noun_picked(self, _index: int):
        val = self.cmb_noun_desc.currentText().strip()
        if val and not val.endswith(","):
            self.cmb_noun_desc.setEditText(f"{val}, ")
        self.cmb_noun_desc.setFocus()

    def _open_clone_dialog(self):
        PartSearchDialogQt(
            self.app, target_entry=None, part_types=[self.part_type],
            on_select_callback=self._clone_from_pn,
            title_override=f"Select Existing {self.part_type.title()} to Clone From"
        ).exec()

    def _clone_from_pn(self, source_pn: str):
        self.rb_add.setChecked(True)
        self._on_mode_change()
        self._populate_form(source_pn)
        QMessageBox.information(self, "Cloned Attributes", f"Copied attributes from '{source_pn}' into the form for a new {self.part_type}.")

    def _on_mode_change(self):
        if self.rb_add.isChecked():
            self.ent_seed.setEnabled(True)
            self.ent_existing_pn.setEnabled(False)
            self.btn_find_existing.setEnabled(False)
            self.btn_submit.setText(f"Save New {self.part_type.title()} (Pending ECO)")
            self.update_seed_preview()
        else:
            self.ent_seed.setEnabled(False)
            self.lbl_next_pn.setText("Modify Mode Active")
            self.lbl_next_pn.setStyleSheet(f"color: {self.colors['accent_warning']}; font-weight: bold;")
            self.ent_existing_pn.setEnabled(True)
            self.btn_find_existing.setEnabled(True)
            self.btn_submit.setText(f"Save Modification to {self.part_type.title()} (Pending ECO)")

    def _on_bulk_toggled(self):
        if not self.is_regular_part:
            return
        if self.chk_is_bulk.isChecked():
            uoms = get_active_bulk_uoms(self.app.user_settings)
            self.cmb_uom.clear()
            self.cmb_uom.addItems(uoms)
            self.cmb_uom.setEnabled(True)
        else:
            self.cmb_uom.clear()
            self.cmb_uom.addItems(["EA"])
            self.cmb_uom.setEnabled(False)

    def _on_proto_toggled(self):
        self.ent_rev.setText("1" if self.chk_is_proto.isChecked() else "A")

    def update_seed_preview(self):
        if not self.rb_add.isChecked():
            return
        try:
            with session_scope() as s:
                nxt = preview_next_part_number(s, self.ent_seed.text())
                self.lbl_next_pn.setText(f"Next PN: {nxt}")
                self.lbl_next_pn.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        except Exception:
            self.lbl_next_pn.setText("Invalid Seed")
            self.lbl_next_pn.setStyleSheet(f"color: {self.colors['accent_danger']}; font-weight: bold;")

    def _on_table_double_click(self, item: QTreeWidgetItem, _col: int):
        pn = item.text(0)
        self.rb_mod.setChecked(True)
        self._on_mode_change()
        self.ent_existing_pn.setText(pn)
        self._load_existing_record()

    def _load_existing_record(self):
        pn = self.ent_existing_pn.text().strip().upper()
        if pn:
            self._populate_form(pn)

    def _populate_form(self, pn: str):
        with session_scope() as s:
            svc = BOMService(s)
            p = svc.get_part(pn)
            if not p:
                QMessageBox.critical(self, "Not Found", f"'{pn}' does not exist.")
                return
            upd = svc.get_pending_update_for_part(pn)
            if upd and self.rb_mod.isChecked():
                self.cmb_noun_desc.setEditText(f"{upd.new_noun_rel.name}, {upd.new_description}")
                self.cmb_mat.setCurrentText(upd.new_material_rel.name if upd.new_material_rel else "")
                self.cmb_finish.setCurrentText(upd.new_finish)
                self.ent_envelope.setText(upd.new_envelope)
                self.ent_mat_size.setText(upd.new_material_size)
                self.cmb_dwg_size.setCurrentText(upd.new_drawing_size)
                self.ent_cond_code.setText(upd.new_condition_code)
                self.chk_is_bulk.setChecked(upd.new_is_bulk)
                self._on_bulk_toggled()
                if upd.new_is_bulk:
                    self.cmb_uom.setCurrentText(upd.new_uom)
                self.chk_is_proto.setChecked(upd.new_is_prototype)
                self.ent_rev.setText(upd.new_revision)
                for i in range(self.cmb_eco.count()):
                    if self.cmb_eco.itemText(i).startswith(upd.eco_number):
                        self.cmb_eco.setCurrentIndex(i)
                        break
            else:
                self.cmb_noun_desc.setEditText(p.standard_name)
                self.cmb_mat.setCurrentText(p.material_rel.name if p.material_rel else "")
                self.cmb_finish.setCurrentText(p.finish)
                self.ent_envelope.setText(p.envelope)
                self.ent_unit_weight.setText(f"{p.unit_weight:g}")
                self.cmb_source_type.setCurrentText(p.source_type or "MAKE")
                self.ent_mat_size.setText(p.material_size)
                self.cmb_dwg_size.setCurrentText(p.drawing_size)
                self.ent_cond_code.setText(p.condition_code)
                self.chk_is_bulk.setChecked(p.is_bulk)
                self._on_bulk_toggled()
                if p.is_bulk:
                    self.cmb_uom.setCurrentText(p.uom)
                self.chk_is_proto.setChecked(p.is_prototype)
                self.ent_rev.setText(p.revision)

    def _submit_form(self):
        eco_raw = self.cmb_eco.currentText().split(" | ")[0].strip()
        try:
            with session_scope() as s:
                svc = BOMService(s)
                if self.rb_add.isChecked():
                    p = svc.create_part(
                        noun_desc=self.cmb_noun_desc.currentText(), eco_number=eco_raw,
                        part_type=self.part_type, material=self.cmb_mat.currentText() or None,
                        finish=self.cmb_finish.currentText(), envelope=self.ent_envelope.text(),
                        source_type=self.cmb_source_type.currentText(),
                        unit_weight=float(self.ent_unit_weight.text() or 0.0),
                        material_size=self.ent_mat_size.text(), drawing_size=self.cmb_dwg_size.currentText(),
                        condition_code=self.ent_cond_code.text() if self.is_prod_sub else "",
                        is_bulk=self.chk_is_bulk.isChecked() if self.is_regular_part else False,
                        uom=self.cmb_uom.currentText() if self.is_regular_part else "EA",
                        is_prototype=self.chk_is_proto.isChecked(), starting_code=self.ent_seed.text(),
                        revision=self.ent_rev.text()
                    )
                    QMessageBox.information(
                        self, "Created (Pending ECO)",
                        f"Number: {p.part_number}\nName: {p.standard_name}\nStatus: {p.release_status} under {p.eco_number}"
                    )
                else:
                    msg = svc.modify_existing_part(
                        part_number=self.ent_existing_pn.text(), noun_desc=self.cmb_noun_desc.currentText(),
                        eco_number=eco_raw, material=self.cmb_mat.currentText() or None,
                        finish=self.cmb_finish.currentText(), envelope=self.ent_envelope.text(),
                        source_type=self.cmb_source_type.currentText(),
                        unit_weight=float(self.ent_unit_weight.text() or 0.0),
                        material_size=self.ent_mat_size.text(), drawing_size=self.cmb_dwg_size.currentText(),
                        condition_code=self.ent_cond_code.text() if self.is_prod_sub else "",
                        is_bulk=self.chk_is_bulk.isChecked() if self.is_regular_part else False,
                        uom=self.cmb_uom.currentText() if self.is_regular_part else "EA",
                        is_prototype=self.chk_is_proto.isChecked(), new_revision=self.ent_rev.text()
                    )
                    QMessageBox.information(self, "Modification Staged", msg)
            self.app.refresh_all_data()
        except Exception as e:
            QMessageBox.critical(self, "Validation Error", str(e))

    def _clear_catalog_search(self):
        self.ent_cat_search.clear()
        self.tree.clear()
        self.lbl_cat_count.setText("(Enter a search above to display records)")

    def run_catalog_search(self, force_all: bool = False):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        q = "*" if force_all else self.ent_cat_search.text().strip()
        if not q:
            self.lbl_cat_count.setText("(Enter a search above to display records)")
            self.tree.setSortingEnabled(True)
            return
        with session_scope() as s:
            svc = BOMService(s)
            parts_of_type = svc.search_parts(q, part_types=[self.part_type])
            upd_map = svc.get_pending_updates_map()
            for p in parts_of_type:
                upd = upd_map.get(p.part_number)
                upd_str = f"Pending ({upd.eco_number}): {upd.new_noun_rel.name}, {upd.new_description} [Rev {upd.new_revision}]" if upd else "-"
                is_pend = (p.release_status == "PENDING_ECO" or upd is not None)
                created_str = _fmt_dt(getattr(p, "created_at", None))
                rel_dt = getattr(p.eco_rel, "released_at", None) if (p.release_status == "RELEASED" and p.eco_rel) else None
                released_str = _fmt_dt(rel_dt)
                item = QTreeWidgetItem([
                    p.part_number,
                    p.standard_name,
                    p.condition_code or "-",
                    p.finish,
                    p.envelope or "-",
                    p.material_size or "-",
                    p.drawing_size,
                    f"{p.uom} (BULK)" if p.is_bulk else p.uom,
                    f"{p.revision} ({'PROTO' if p.is_prototype else 'PROD'})",
                    p.release_status,
                    p.eco_number,
                    created_str,
                    released_str,
                    upd_str,
                ])
                fg = QColor(self.colors["accent_warning"] if is_pend else self.colors["fg_primary"])
                for c in range(item.columnCount()):
                    item.setForeground(c, QBrush(fg))
                self.tree.addTopLevelItem(item)
            self.lbl_cat_count.setText(f"Showing {len(parts_of_type)} record(s)")
        self.tree.setSortingEnabled(True)

    def refresh_panel(self, noun_prefixes, mat_names, open_eco_labels):
        curr_nd = self.cmb_noun_desc.currentText()
        self.cmb_noun_desc.clear()
        self.cmb_noun_desc.addItems(noun_prefixes)
        self.cmb_noun_desc.setEditText(curr_nd)

        curr_m = self.cmb_mat.currentText()
        self.cmb_mat.clear()
        self.cmb_mat.addItem("")
        self.cmb_mat.addItems(mat_names)
        if curr_m:
            self.cmb_mat.setCurrentText(curr_m)

        curr_e = self.cmb_eco.currentText()
        self.cmb_eco.clear()
        self.cmb_eco.addItems(open_eco_labels)
        if curr_e and self.cmb_eco.findText(curr_e) >= 0:
            self.cmb_eco.setCurrentText(curr_e)
        elif open_eco_labels:
            self.cmb_eco.setCurrentIndex(0)
        self.update_seed_preview()


# ==============================================================================
# TAB 11: SETTINGS PANEL
# ==============================================================================
class SettingsPanelQt(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.colors = app.colors
        self._color_edits = {}
        self._swatch_labels = {}
        self._build_ui()

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        make_tab_header(main_lay, self.app, "APPLICATION SETTINGS — DRAWING STANDARDS, DIMENSIONAL UNITS & COLOR SCHEMES", "TAB_13_SETTINGS")

        wrap = QSplitter(Qt.Orientation.Horizontal)
        left = QGroupBox(" 1. Engineering Defaults (Drawing Sheet Sizes && Dimensional Units) ")
        gl = QGridLayout(left)

        gl.addWidget(QLabel("Drawing Sheet Size Standard:"), 0, 0)
        self.cmb_dwg_std = QComboBox()
        self.cmb_dwg_std.addItems(["ISO (A4, A3, A2, A1, A0)", "ANSI (A, B, C, D, E)", "BOTH (ISO + ANSI)"])
        self.cmb_dwg_std.setCurrentText(self.app.user_settings.get("drawing_standard", "BOTH (ISO + ANSI)"))
        self.cmb_dwg_std.currentTextChanged.connect(self._on_std_changed)
        gl.addWidget(self.cmb_dwg_std, 0, 1)

        gl.addWidget(QLabel("Default Drawing Size for New Parts:"), 1, 0)
        self.cmb_default_dwg_sz = QComboBox()
        self.cmb_default_dwg_sz.addItems(get_active_drawing_sizes(self.app.user_settings))
        self.cmb_default_dwg_sz.setCurrentText(self.app.user_settings.get("default_drawing_size", "A3"))
        gl.addWidget(self.cmb_default_dwg_sz, 1, 1, Qt.AlignmentFlag.AlignLeft)

        gl.addWidget(QLabel("Default Dimensional Units:"), 2, 0)
        self.cmb_units = QComboBox()
        self.cmb_units.addItems(["METRIC (mm, kg, mL, L)", "INCH (in, lb, oz, gal)"])
        self.cmb_units.setCurrentText(self.app.user_settings.get("unit_system", "METRIC (mm, kg, mL, L)"))
        gl.addWidget(self.cmb_units, 2, 1)

        gl.addWidget(QLabel("Managed Vault Root:"), 3, 0)
        self.ent_vault_root = QLineEdit(self.app.user_settings.get("vault_root", ""))
        gl.addWidget(self.ent_vault_root, 3, 1)
        gl.setRowStretch(4, 1)
        wrap.addWidget(left)

        right = QGroupBox(" 2. Application Color Scheme && Custom Theme Editor ")
        gr = QGridLayout(right)
        gr.addWidget(QLabel("Theme Preset:"), 0, 0)
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(list(THEME_PRESETS.keys()) + ["Custom"])
        self.cmb_theme.setCurrentText(self.app.user_settings.get("theme_name", "Slate & Steel Blue (Default)"))
        self.cmb_theme.currentTextChanged.connect(self._on_preset_selected)
        gr.addWidget(self.cmb_theme, 0, 1, 1, 3)

        color_roles = [
            ("bg_primary", "Primary Background (Slate)"), ("bg_secondary", "Secondary Surface / Tables"),
            ("bg_surface", "Input Field Surface"), ("fg_primary", "Primary Text Color"),
            ("fg_secondary", "Secondary / Muted Text"), ("accent_primary", "Primary Accent (Tabs & Focus)"),
            ("accent_success", "Success / Released Highlight"), ("accent_warning", "Warning / Pending ECO Highlight"),
            ("accent_danger", "Error / Alert Highlight"),
        ]
        for idx, (key, label_text) in enumerate(color_roles, start=1):
            gr.addWidget(QLabel(label_text + ":"), idx, 0)
            val = self.app.colors.get(key, "#182232")
            ent = QLineEdit(val)
            ent.setFixedWidth(100)
            ent.setFont(QFont("Consolas", 9))
            self._color_edits[key] = ent
            gr.addWidget(ent, idx, 1)
            swatch = QLabel("      ")
            swatch.setStyleSheet(f"background-color: {val}; border: 1px solid #FFFFFF; border-radius: 3px;")
            self._swatch_labels[key] = swatch
            gr.addWidget(swatch, idx, 2)
            gr.addWidget(make_btn("Pick Color...", "admin", lambda _chk=False, k=key: self._pick_color(k)), idx, 3)

        wrap.addWidget(right)
        wrap.setStretchFactor(0, 1)
        wrap.setStretchFactor(1, 1)
        main_lay.addWidget(wrap, 1)

        btm = QHBoxLayout()
        btm.addWidget(make_btn("Apply & Save Settings", "admin", self._apply_and_save))
        btm.addWidget(make_btn("Reset to Default Settings", "admin", self._reset_defaults))
        btm.addStretch(1)
        main_lay.addLayout(btm)

    def _on_std_changed(self, std_txt: str):
        sizes = get_active_drawing_sizes({"drawing_standard": std_txt})
        curr = self.cmb_default_dwg_sz.currentText()
        self.cmb_default_dwg_sz.clear()
        self.cmb_default_dwg_sz.addItems(sizes)
        if curr in sizes:
            self.cmb_default_dwg_sz.setCurrentText(curr)

    def _on_preset_selected(self, preset: str):
        if preset in THEME_PRESETS:
            for k, hex_val in THEME_PRESETS[preset].items():
                if k in self._color_edits:
                    self._color_edits[k].setText(hex_val)
                    self._swatch_labels[k].setStyleSheet(f"background-color: {hex_val}; border: 1px solid #FFFFFF; border-radius: 3px;")

    def _pick_color(self, key: str):
        col = QColorDialog.getColor(QColor(self._color_edits[key].text()), self, f"Select Color for {key}")
        if col.isValid():
            hex_val = col.name().upper()
            self._color_edits[key].setText(hex_val)
            self._swatch_labels[key].setStyleSheet(f"background-color: {hex_val}; border: 1px solid #FFFFFF; border-radius: 3px;")
            self.cmb_theme.setCurrentText("Custom")

    def _apply_and_save(self):
        new_colors = {}
        for k, ent in self._color_edits.items():
            val = ent.text().strip()
            if not val.startswith("#") or len(val) not in (4, 7):
                QMessageBox.critical(self, "Invalid Color", f"Color '{val}' must be a hex code (e.g. #182232).")
                return
            new_colors[k] = val
            self._swatch_labels[k].setStyleSheet(f"background-color: {val}; border: 1px solid #FFFFFF; border-radius: 3px;")

        self.app.user_settings["drawing_standard"] = self.cmb_dwg_std.currentText()
        self.app.user_settings["default_drawing_size"] = self.cmb_default_dwg_sz.currentText()
        self.app.user_settings["unit_system"] = self.cmb_units.currentText()
        self.app.user_settings["vault_root"] = self.ent_vault_root.text().strip()
        self.app.user_settings["theme_name"] = self.cmb_theme.currentText()
        self.app.user_settings["colors"] = new_colors

        save_user_settings(self.app.user_settings)
        self.app.apply_runtime_settings()
        QMessageBox.information(self, "Settings Applied", "Settings saved and applied!")

    def _reset_defaults(self):
        self.app.user_settings = dict(DEFAULT_SETTINGS)
        self.app.user_settings["colors"] = dict(THEME_PRESETS["Slate & Steel Blue (Default)"])
        save_user_settings(self.app.user_settings)
        self.cmb_dwg_std.setCurrentText(self.app.user_settings["drawing_standard"])
        self._on_std_changed(self.app.user_settings["drawing_standard"])
        self.cmb_default_dwg_sz.setCurrentText(self.app.user_settings["default_drawing_size"])
        self.cmb_units.setCurrentText(self.app.user_settings["unit_system"])
        self.cmb_theme.setCurrentText(self.app.user_settings["theme_name"])
        self._on_preset_selected(self.app.user_settings["theme_name"])
        self.app.apply_runtime_settings()


# ==============================================================================
# TAB 12: ADMINISTRATION PANEL (USER ACCOUNTS + STARTING CODE SEEDS)
# ==============================================================================
class AdministrationPanelQt(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.colors = app.colors
        self._build_ui()

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        make_tab_header(
            main_lay, self.app,
            "STEP 12: SYSTEM ADMINISTRATION — USER ACCOUNTS, RBAC ROLES & STARTING CODE SEEDS (ADMIN ONLY)",
            "TAB_13_SETTINGS"
        )
        wrap_split = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_col = QVBoxLayout(left_widget)
        left_col.setContentsMargins(0, 0, 0, 0)

        left = QGroupBox(" 1. Create or Update User Account ")
        gl = QGridLayout(left)
        gl.addWidget(QLabel("User ID (Login):"), 0, 0)
        self.ent_uid = QLineEdit()
        gl.addWidget(self.ent_uid, 0, 1)

        gl.addWidget(QLabel("Full Name:"), 1, 0)
        self.ent_fullname = QLineEdit()
        gl.addWidget(self.ent_fullname, 1, 1)

        gl.addWidget(QLabel("E-Mail Address:"), 2, 0)
        self.ent_email = QLineEdit()
        gl.addWidget(self.ent_email, 2, 1)

        gl.addWidget(QLabel("Permission Role:"), 3, 0)
        self.cmb_role = QComboBox()
        self.cmb_role.addItems(USER_ROLES)
        gl.addWidget(self.cmb_role, 3, 1)

        gl.addWidget(QLabel("Account Status:"), 4, 0)
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["ACTIVE", "INACTIVE"])
        gl.addWidget(self.cmb_status, 4, 1, Qt.AlignmentFlag.AlignLeft)

        gl.addWidget(QLabel("Set / Reset Password:"), 5, 0)
        self.ent_password = QLineEdit()
        self.ent_password.setEchoMode(QLineEdit.EchoMode.Password)
        gl.addWidget(self.ent_password, 5, 1)

        bbar = QHBoxLayout()
        bbar.addWidget(make_btn("Save / Update User", "admin", self._save_user))
        bbar.addStretch(1)
        bbar.addWidget(make_btn("Clear Form", "viewer", self._clear_form))
        gl.addLayout(bbar, 6, 0, 1, 2)
        left_col.addWidget(left)

        seed_gb = QGroupBox(" 2. Default Starting Code Seeds (Tab 1 Product, Tab 2 Subassembly && Tab 3 Part) ")
        sg = QGridLayout(seed_gb)
        sg.setVerticalSpacing(8)
        sg.setHorizontalSpacing(10)

        saved_seeds = self.app.user_settings.get("starting_codes", {})
        if not isinstance(saved_seeds, dict):
            saved_seeds = {}

        prod_seed = saved_seeds.get("PRODUCT", STARTING_CODES.get("PRODUCT", "3PR00000000"))
        sub_seed = saved_seeds.get("PRODUCTION SUBASSEMBLY", STARTING_CODES.get("PRODUCTION SUBASSEMBLY", "2AS00000000"))
        part_seed = saved_seeds.get("PART", STARTING_CODES.get("PART", "1AF00000000"))

        sg.addWidget(QLabel("Tab 1 — Product Seed (3PR):"), 0, 0)
        self.ent_seed_prod = QLineEdit(prod_seed)
        self.ent_seed_prod.setFixedWidth(160)
        self.ent_seed_prod.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_seed_prod.textChanged.connect(self._update_admin_seed_previews)
        sg.addWidget(self.ent_seed_prod, 0, 1, Qt.AlignmentFlag.AlignLeft)
        self.lbl_prev_prod = QLabel("Next: ...")
        self.lbl_prev_prod.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        sg.addWidget(self.lbl_prev_prod, 0, 2)

        sg.addWidget(QLabel("Tab 2 — Prod Subassembly Seed (2AS):"), 1, 0)
        self.ent_seed_sub = QLineEdit(sub_seed)
        self.ent_seed_sub.setFixedWidth(160)
        self.ent_seed_sub.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_seed_sub.textChanged.connect(self._update_admin_seed_previews)
        sg.addWidget(self.ent_seed_sub, 1, 1, Qt.AlignmentFlag.AlignLeft)
        self.lbl_prev_sub = QLabel("Next: ...")
        self.lbl_prev_sub.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        sg.addWidget(self.lbl_prev_sub, 1, 2)

        sg.addWidget(QLabel("Tab 3 — Piece Part Seed (1AF):"), 2, 0)
        self.ent_seed_part = QLineEdit(part_seed)
        self.ent_seed_part.setFixedWidth(160)
        self.ent_seed_part.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_seed_part.textChanged.connect(self._update_admin_seed_previews)
        sg.addWidget(self.ent_seed_part, 2, 1, Qt.AlignmentFlag.AlignLeft)
        self.lbl_prev_part = QLabel("Next: ...")
        self.lbl_prev_part.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        sg.addWidget(self.lbl_prev_part, 2, 2)

        seed_hint = QLabel("Seeds must end with numeric digits (e.g. 3PR00000000). Saving updates Tabs 1–3 immediately.")
        seed_hint.setStyleSheet(f"color: {self.colors['fg_secondary']}; font-size: 8pt;")
        sg.addWidget(seed_hint, 3, 0, 1, 3)

        sbar = QHBoxLayout()
        sbar.addWidget(make_btn("Save Starting Code Seeds", "admin", self._save_starting_seeds))
        sbar.addStretch(1)
        sbar.addWidget(make_btn("Reset Default Seeds", "viewer", self._reset_starting_seeds))
        sg.addLayout(sbar, 4, 0, 1, 3)

        left_col.addWidget(seed_gb)
        left_col.addStretch(1)
        wrap_split.addWidget(left_widget)

        right = QGroupBox(" 3. Registered System Users (Click Any Row to Edit) ")
        rl = QVBoxLayout(right)
        tbar = QHBoxLayout()
        tbar.addWidget(make_btn("Refresh Users", "viewer", self.refresh_users))
        tbar.addStretch(1)
        rl.addLayout(tbar)

        self.tree_users = QTreeWidget()
        setup_tree_columns(self.tree_users, [
            ("userid", "User ID", 100), ("full_name", "Full Name", 170),
            ("role", "Permission Role", 210), ("status", "Status", 90), ("email", "E-Mail Address", 200)
        ])
        self.tree_users.itemSelectionChanged.connect(self._on_user_selected)
        rl.addWidget(self.tree_users, 1)
        wrap_split.addWidget(right)
        wrap_split.setStretchFactor(0, 2)
        wrap_split.setStretchFactor(1, 3)

        main_lay.addWidget(wrap_split, 1)
        self.refresh_users()
        self._update_admin_seed_previews()

    def _update_admin_seed_previews(self):
        pairs = [
            (self.ent_seed_prod, self.lbl_prev_prod),
            (self.ent_seed_sub, self.lbl_prev_sub),
            (self.ent_seed_part, self.lbl_prev_part),
        ]
        with session_scope() as s:
            for ent, lbl in pairs:
                try:
                    nxt = preview_next_part_number(s, ent.text().strip())
                    lbl.setText(f"Next PN: {nxt}")
                    lbl.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
                except Exception:
                    lbl.setText("Invalid Seed")
                    lbl.setStyleSheet(f"color: {self.colors['accent_danger']}; font-weight: bold;")

    def _save_starting_seeds(self):
        raw_map = {
            "PRODUCT": self.ent_seed_prod.text().strip().upper(),
            "PRODUCTION SUBASSEMBLY": self.ent_seed_sub.text().strip().upper(),
            "PART": self.ent_seed_part.text().strip().upper(),
        }
        try:
            with session_scope() as s:
                for ptype, seed_val in raw_map.items():
                    parse_starting_code(seed_val)
                    sync_sequence_with_seed(s, seed_val)
        except Exception as e:
            QMessageBox.critical(self, "Invalid Starting Code Seed", str(e))
            return

        self.app.user_settings["starting_codes"] = raw_map
        save_user_settings(self.app.user_settings)
        self._apply_seeds_to_setup_tabs(raw_map)
        self._update_admin_seed_previews()
        QMessageBox.information(
            self,
            "Starting Code Seeds Saved",
            f"Updated default starting code seeds:\n\n"
            f"• Tab 1 (Product)           : {raw_map['PRODUCT']}\n"
            f"• Tab 2 (Prod Subassembly)  : {raw_map['PRODUCTION SUBASSEMBLY']}\n"
            f"• Tab 3 (Part)              : {raw_map['PART']}"
        )

    def _reset_starting_seeds(self):
        defaults = {
            "PRODUCT": "3PR00000000",
            "PRODUCTION SUBASSEMBLY": "2AS00000000",
            "PART": "1AF00000000",
        }
        self.ent_seed_prod.setText(defaults["PRODUCT"])
        self.ent_seed_sub.setText(defaults["PRODUCTION SUBASSEMBLY"])
        self.ent_seed_part.setText(defaults["PART"])
        self._save_starting_seeds()

    def _apply_seeds_to_setup_tabs(self, seed_map: dict):
        tab_mapping = [
            (self.app.tab_prod_setup, "PRODUCT"),
            (self.app.tab_sub_setup, "PRODUCTION SUBASSEMBLY"),
            (self.app.tab_part_setup, "PART"),
        ]
        for panel, key in tab_mapping:
            if key in seed_map:
                panel.default_seed = seed_map[key]
                panel.ent_seed.setText(seed_map[key])
                panel.update_seed_preview()

    def refresh_users(self):
        self.tree_users.setSortingEnabled(False)
        self.tree_users.clear()
        with session_scope() as s:
            for u in BOMService(s).list_users():
                self.tree_users.addTopLevelItem(QTreeWidgetItem([u.userid, u.full_name, u.role, u.status, u.email]))
        self.tree_users.setSortingEnabled(True)

    def _on_user_selected(self):
        items = self.tree_users.selectedItems()
        if not items:
            return
        it = items[0]
        self.ent_uid.setText(it.text(0))
        self.ent_fullname.setText(it.text(1))
        self.cmb_role.setCurrentText(it.text(2))
        self.cmb_status.setCurrentText(it.text(3))
        self.ent_email.setText(it.text(4))
        self.ent_password.clear()

    def _clear_form(self):
        self.ent_uid.clear()
        self.ent_fullname.clear()
        self.ent_email.clear()
        self.cmb_role.setCurrentIndex(0)
        self.cmb_status.setCurrentText("ACTIVE")
        self.ent_password.clear()

    def _save_user(self):
        uid = self.ent_uid.text().strip().lower()
        fname = self.ent_fullname.text().strip()
        email = self.ent_email.text().strip()
        role = self.cmb_role.currentText()
        st = self.cmb_status.currentText()
        pwd = self.ent_password.text().strip()
        try:
            with session_scope() as s:
                BOMService(s).save_or_update_user(uid, role, fname, st, email, new_password=pwd if pwd else None)
            self.ent_password.clear()
            self.refresh_users()
            QMessageBox.information(self, "User Saved", f"User account '{uid}' saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Administration Error", str(e))


# ==============================================================================
# LOGIN DIALOG
# ==============================================================================
class LoginDialogQt(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_settings = load_user_settings()
        self.colors = dict(self.user_settings["colors"])
        self.authenticated_user: Optional[dict] = None

        self.setWindowTitle("hBOM — User Authentication Login")
        self.setFixedSize(480, 490)
        self.setStyleSheet(build_app_stylesheet(self.colors))

        logo_path = _find_logo_path()
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)

        if logo_path:
            lbl_logo = QLabel()
            pix = QPixmap(logo_path).scaled(115, 115, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl_logo.setPixmap(pix)
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl_logo)

        lbl_title = QLabel("hBOM Engineering BOM & ECO Manager")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-size: 11pt; font-weight: bold;")
        lay.addWidget(lbl_title)

        frm = QGroupBox(" Sign In to Engineering Workspace ")
        grid = QGridLayout(frm)
        grid.addWidget(QLabel("User ID:"), 0, 0)
        self.ent_userid = QLineEdit(self.user_settings.get("active_userid", "admin"))
        grid.addWidget(self.ent_userid, 0, 1)

        grid.addWidget(QLabel("Password:"), 1, 0)
        self.ent_password = QLineEdit("demo")
        self.ent_password.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self.ent_password, 1, 1)

        hint_text = (
            "Default Demo Accounts (Password for all: demo)\n"
            "  • viewer   — VIEWER (Read-Only)\n"
            "  • engineer — DESIGNER (Create/Modify)\n"
            "  • approver — APPROVER (Approve/Release)\n"
            "  • admin    — ADMIN (Full Access + Administration Tab)"
        )
        lbl_hint = QLabel(hint_text)
        lbl_hint.setStyleSheet(f"color: {self.colors['fg_secondary']}; font-size: 8pt;")
        grid.addWidget(lbl_hint, 2, 0, 1, 2)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch(1)
        btn_bar.addWidget(make_btn("Exit Application", "viewer", self.reject))
        btn_bar.addWidget(make_btn("Sign In", "designer", self._attempt_login))
        grid.addLayout(btn_bar, 3, 0, 1, 2)

        lay.addWidget(frm, 1)
        self.ent_userid.returnPressed.connect(self.ent_password.setFocus)
        self.ent_password.returnPressed.connect(self._attempt_login)
        self.ent_userid.setFocus()
        self.ent_userid.selectAll()

    def _attempt_login(self):
        uid = self.ent_userid.text().strip().lower()
        pwd = self.ent_password.text()
        try:
            with session_scope() as s:
                user = BOMService(s).authenticate_user(uid, pwd)
                self.authenticated_user = {
                    "userid": user.userid,
                    "role": user.role,
                    "full_name": user.full_name,
                    "status": user.status,
                    "email": user.email,
                }
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Authentication Failed", str(e))
            self.ent_password.clear()
            self.ent_password.setFocus()


# ==============================================================================
# MAIN WINDOW: BOMPyQtApp
# ==============================================================================
class BOMPyQtApp(QMainWindow):
    def __init__(self, user_dict: Optional[dict] = None):
        super().__init__()
        self.setWindowTitle("hBOM — Engineering BOM & ECO Manager (v8.0)")
        self.resize(1480, 900)
        self.setMinimumSize(1220, 740)

        logo_path = _find_logo_path()
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        self.user_settings = load_user_settings()
        if user_dict:
            self.user_settings["active_userid"] = user_dict["userid"]
            self.user_settings["active_user"] = user_dict["full_name"]
            self.user_settings["user_role"] = user_dict["role"]
            save_user_settings(self.user_settings)

        self.colors = dict(self.user_settings["colors"])
        self.setStyleSheet(build_app_stylesheet(self.colors))

        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Branded Top Header Bar
        self.header_bar = QFrame()
        self.header_bar.setFixedHeight(46)
        self.header_bar.setStyleSheet(
            f"background-color: {self.colors['bg_secondary']}; border-bottom: 2px solid #26354D;"
        )
        hlay = QHBoxLayout(self.header_bar)
        hlay.setContentsMargins(12, 4, 12, 4)

        if logo_path:
            lbl_hdr_icon = QLabel()
            pix = QPixmap(logo_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl_hdr_icon.setPixmap(pix)
            lbl_hdr_icon.setStyleSheet("border: none;")
            hlay.addWidget(lbl_hdr_icon)

        self.lbl_app_title = QLabel("hBOM — ENGINEERING BOM & ECO MANAGER (v8.0)")
        self.lbl_app_title.setStyleSheet(f"color: {self.colors['fg_primary']}; font-size: 11pt; font-weight: bold; border: none;")
        hlay.addWidget(self.lbl_app_title)
        hlay.addStretch(1)

        self.lbl_active_role_badge = QLabel("")
        self.lbl_active_role_badge.setStyleSheet(
            "background-color: #0F172A; color: #38BDF8; font-weight: bold; padding: 4px 12px; border: 1px solid #334155; border-radius: 4px;"
        )
        hlay.addWidget(self.lbl_active_role_badge)

        hlay.addWidget(make_btn("Refresh All Data", "viewer", self.refresh_all_data))
        hlay.addWidget(make_btn("Switch User / Logout", "viewer", self.prompt_switch_user))
        root_lay.addWidget(self.header_bar)

        body_wrap = QVBoxLayout()
        body_wrap.setContentsMargins(8, 8, 8, 6)
        self.notebook = QTabWidget()
        body_wrap.addWidget(self.notebook, 1)
        root_lay.addLayout(body_wrap, 1)

        # Persistent Bottom Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.tab_prod_setup = CategorySetupPanelQt(self, "PRODUCT", "TAB_6_PROD")
        self.tab_sub_setup = CategorySetupPanelQt(self, "PRODUCTION SUBASSEMBLY", "TAB_5_SUB")
        self.tab_part_setup = CategorySetupPanelQt(self, "PART", "TAB_4_PART")
        self.tab_bom_build = QWidget()
        self.tab_ecos = QWidget()
        self.tab_dwg_reg = QWidget()
        self.tab_bom_lookup = QWidget()
        self.tab_where_used = QWidget()
        self.tab_compare = QWidget()
        self.tab_dwg_view = QWidget()
        self.tab_settings = SettingsPanelQt(self)
        self.tab_admin = AdministrationPanelQt(self)

        self.notebook.addTab(self.tab_prod_setup, " 1. Product Setup ")
        self.notebook.addTab(self.tab_sub_setup, " 2. Prod Subassembly ")
        self.notebook.addTab(self.tab_part_setup, " 3. Part Setup ")
        self.notebook.addTab(self.tab_bom_build, " 4. BOM Builder ")
        self.notebook.addTab(self.tab_ecos, " 5. ECO Manager ")
        self.notebook.addTab(self.tab_dwg_reg, " 6. Drawing Registration ")
        self.notebook.addTab(self.tab_bom_lookup, " 7. BOM Lookup ")
        self.notebook.addTab(self.tab_where_used, " 8. Where-Used ")
        self.notebook.addTab(self.tab_compare, " 9. Compare BOMs ")
        self.notebook.addTab(self.tab_dwg_view, " 10. Drawing Viewer ")
        self.notebook.addTab(self.tab_settings, " 11. Settings ")
        self.notebook.addTab(self.tab_admin, " 12. Administration ")

        self._build_bom_builder_tab()
        self._build_ecos_tab()
        self._build_drawing_registration_tab()
        self._build_bom_lookup_tab()
        self._build_where_used_tab()
        self._build_compare_tab()
        self._build_drawing_viewer_tab()

        self.apply_runtime_settings()
        self.refresh_all_data()
        self._populate_ecos(force_all=True)
        self._update_eco_status_badge()

    def set_status_message(self, msg: str):
        if hasattr(self, "status_bar") and self.status_bar is not None:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            role_str = self.user_settings.get("user_role", "ADMIN").split()[0]
            uid = self.user_settings.get("active_userid", "admin")
            self.status_bar.showMessage(f"  ✓ {msg}   |   Signed In: {uid} [{role_str}]   |   Updated: {ts}")

    def apply_runtime_settings(self):
        role_str = self.user_settings.get("user_role", "ADMIN (Full Access)").split(" ")[0]
        eng_str = self.user_settings.get("active_user", "System Administrator")
        self.lbl_active_role_badge.setText(f"Active User: {eng_str} [{role_str}]")

        self.colors.update(self.user_settings["colors"])
        self.setStyleSheet(build_app_stylesheet(self.colors))
        self.header_bar.setStyleSheet(f"background-color: {self.colors['bg_secondary']}; border-bottom: 2px solid #26354D;")

        active_sizes = get_active_drawing_sizes(self.user_settings)
        def_sz = self.user_settings.get("default_drawing_size", active_sizes[0])
        bulk_uoms = get_active_bulk_uoms(self.user_settings)

        for panel in (self.tab_part_setup, self.tab_sub_setup, self.tab_prod_setup):
            panel.colors = self.colors
            panel.cmb_dwg_size.clear()
            panel.cmb_dwg_size.addItems(active_sizes)
            if def_sz in active_sizes:
                panel.cmb_dwg_size.setCurrentText(def_sz)
            if panel.is_regular_part and panel.chk_is_bulk.isChecked():
                panel.cmb_uom.clear()
                panel.cmb_uom.addItems(bulk_uoms)

        self._enforce_admin_tab_visibility()
        self.set_status_message("Workspace settings and visual theme applied")

    def _enforce_admin_tab_visibility(self):
        role_str = self.user_settings.get("user_role", "VIEWER").upper()
        is_admin = role_str.startswith("ADMIN")
        idx = self.notebook.indexOf(self.tab_admin)
        if is_admin:
            if idx == -1:
                self.notebook.addTab(self.tab_admin, " 12. Administration ")
            else:
                self.notebook.setTabVisible(idx, True)
        else:
            if idx != -1:
                if self.notebook.currentIndex() == idx:
                    self.notebook.setCurrentIndex(0)
                self.notebook.setTabVisible(idx, False)

    def prompt_switch_user(self):
        dlg = LoginDialogQt(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.authenticated_user:
            u = dlg.authenticated_user
            self.user_settings["active_userid"] = u["userid"]
            self.user_settings["active_user"] = u["full_name"]
            self.user_settings["user_role"] = u["role"]
            save_user_settings(self.user_settings)
            self.apply_runtime_settings()
            self.refresh_all_data()

    def quick_pull_eco(self):
        role = self.user_settings.get("user_role", "ADMIN (Full Access)")
        if role.startswith("VIEWER"):
            QMessageBox.critical(self, "Permission Denied", "Current role is VIEWER (Read-Only).\n\nViewers cannot pull or request ECO numbers.")
            return
        is_designer = role.startswith("DESIGNER")
        ECORequestDialogQt(self, is_designer=is_designer).exec()

    def _resolve_wildcard_entry_pn(self, entry_widget: QLineEdit, on_resolved_callback) -> Optional[str]:
        raw = entry_widget.text().strip().upper()
        if not raw:
            return None
        with session_scope() as s:
            svc = BOMService(s)
            if "*" not in raw and "?" not in raw:
                exact = svc.get_part(raw)
                if exact:
                    return exact.part_number
            matches = svc.search_parts(raw, limit=50)
            if len(matches) == 1:
                resolved = matches[0].part_number
                entry_widget.setText(resolved)
                return resolved
        PartSearchDialogQt(self, entry_widget, on_select_callback=lambda _pn=None: on_resolved_callback(), initial_query=raw).exec()
        return None

    # ==========================================================================
    # TAB 4: BOM BUILDER (INTERACTIVE QSPLITTER + DRAG-AND-DROP)
    # ==========================================================================
    def _build_bom_builder_tab(self):
        lay = QVBoxLayout(self.tab_bom_build)
        make_tab_header(lay, self, "STEP 4: BOM BUILDER & MARKUP MANAGER (DRAG-AND-DROP)", "TAB_7_BOM")

        wrap_split = QSplitter(Qt.Orientation.Horizontal)

        left = QGroupBox(" Master Part Catalog (Drag or Double-Click to Add to BOM) ")
        ll = QVBoxLayout(left)
        sb = QHBoxLayout()
        sb.addWidget(QLabel("Wildcard Search:"))
        self.ent_bom_search = make_search_entry(190, "e.g. 1AF*5 or *BOLT*")
        self.ent_bom_search.returnPressed.connect(lambda: self._populate_bom_search(force_all=False))
        sb.addWidget(self.ent_bom_search)
        sb.addWidget(make_btn("Search", "viewer", lambda: self._populate_bom_search(force_all=False)))
        sb.addWidget(make_btn("Show All", "viewer", lambda: self._populate_bom_search(force_all=True)))
        sb.addWidget(make_btn("Clear", "viewer", lambda: (self.ent_bom_search.clear(), self._populate_bom_search())))
        sb.addStretch(1)
        ll.addLayout(sb)

        self.tree_bom_catalog = QTreeWidget()
        setup_tree_columns(self.tree_bom_catalog, [
            ("pn", "Part #", 100), ("name", "Description", 180), ("cond", "Cond", 45),
            ("uom", "UOM", 45), ("type", "Category", 110), ("status", "Status", 80), ("rev", "Rev", 40)
        ])
        self.tree_bom_catalog.itemDoubleClicked.connect(self._on_catalog_double_click)
        self.tree_bom_catalog.setDragEnabled(True)
        self.tree_bom_catalog.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        ll.addWidget(self.tree_bom_catalog, 1)
        wrap_split.addWidget(left)

        right = QGroupBox(" Active Assembly BOM Structure && Staged ECO Markups ")
        rl = QVBoxLayout(right)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Parent Assembly PN:"))
        self.ent_bom_parent = make_search_entry(150, "3PR* or 2AS*")
        self.ent_bom_parent.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_bom_parent.returnPressed.connect(self._load_parent_bom)
        pr.addWidget(self.ent_bom_parent)
        pr.addWidget(make_btn("Find...", "viewer", lambda: PartSearchDialogQt(self, self.ent_bom_parent, on_select_callback=lambda _p=None: self._load_parent_bom()).exec()))
        pr.addWidget(make_btn("Load BOM", "viewer", self._load_parent_bom))
        self.lbl_parent_info = QLabel("Load an assembly to edit BOM")
        self.lbl_parent_info.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        pr.addWidget(self.lbl_parent_info, 1)
        rl.addLayout(pr)

        self.tree_assembly_bom = QTreeWidget()
        setup_tree_columns(self.tree_assembly_bom, [
            ("find", "Find #", 55), ("pn", "Child PN", 110), ("name", "Description", 200),
            ("qty", "Qty", 60), ("uom", "UOM", 45), ("cond", "Cond", 45),
            ("supply", "Supply Class", 95), ("status", "BOM Status", 90)
        ])
        self.tree_assembly_bom.itemDoubleClicked.connect(self._on_assembly_row_double_click)
        self.tree_assembly_bom.setAcceptDrops(True)
        self.tree_assembly_bom.setDropIndicatorShown(True)
        self.tree_assembly_bom.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.tree_assembly_bom.dropEvent = self._handle_bom_drop_event
        rl.addWidget(self.tree_assembly_bom, 1)

        ctrl = QHBoxLayout()
        ctrl.addWidget(make_btn("Remove Selected Child", "designer", self._remove_assembly_child))
        ctrl.addWidget(make_btn("Move Up", "designer", lambda: self._move_assembly_row(-1)))
        ctrl.addWidget(make_btn("Move Down", "designer", lambda: self._move_assembly_row(1)))
        ctrl.addStretch(1)
        rl.addLayout(ctrl)

        save_frm = QGroupBox(" Save BOM Markups to Open ECO ")
        sl = QHBoxLayout(save_frm)
        sl.addWidget(QLabel("Select Open ECO:"))
        self.cmb_bom_eco = QComboBox()
        self.cmb_bom_eco.setFixedWidth(280)
        sl.addWidget(self.cmb_bom_eco)
        sl.addStretch(1)
        sl.addWidget(make_btn("SAVE BOM MARKUPS TO ECO", "designer", self._save_bom_markups_action))
        rl.addWidget(save_frm)

        wrap_split.addWidget(right)
        wrap_split.setStretchFactor(0, 2)
        wrap_split.setStretchFactor(1, 3)
        lay.addWidget(wrap_split, 1)

    def _handle_bom_drop_event(self, event):
        source_item = self.tree_bom_catalog.currentItem()
        if source_item:
            self._insert_staged_part(
                source_item.text(0), source_item.text(1),
                source_item.text(3), source_item.text(2), source_item.text(4)
            )
        event.acceptProposedAction()

    # ==========================================================================
    # TAB 5: ECO MANAGER (INTERACTIVE VERTICAL & HORIZONTAL QSPLITTERS)
    # ==========================================================================
    def _build_ecos_tab(self):
        lay = QVBoxLayout(self.tab_ecos)
        make_tab_header(lay, self, "STEP 5: ENGINEERING CHANGE ORDER (ECO) MANAGER", "TAB_3_ECO")

        main_v_split = QSplitter(Qt.Orientation.Vertical)

        self.lf_master_log = QGroupBox(" 1. Engineering Change Orders Master Log (Click Any Row to Load ECO — Double-Click for Workflow Flowchart) ")
        mlay = QVBoxLayout(self.lf_master_log)

        ebar = QHBoxLayout()
        ebar.addWidget(QLabel("Wildcard Search:"))
        self.ent_eco_search = make_search_entry(210, "e.g. ECO*2, *BUCKET*, OPEN")
        self.ent_eco_search.returnPressed.connect(lambda: self._populate_ecos(force_all=False))
        ebar.addWidget(self.ent_eco_search)
        ebar.addWidget(make_btn("Search", "viewer", lambda: self._populate_ecos(force_all=False)))
        ebar.addWidget(make_btn("Show All", "viewer", lambda: self._populate_ecos(force_all=True)))
        ebar.addWidget(make_btn("Clear", "viewer", self._clear_eco_search))
        self.lbl_eco_count = QLabel("(Enter a search above to display ECOs)")
        self.lbl_eco_count.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        ebar.addWidget(self.lbl_eco_count)
        ebar.addStretch(1)
        ebar.addWidget(make_btn("Export PDF...", "viewer", self._quick_export_selected_eco_pdf))
        ebar.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_ecos, "eco_master_log.csv", self)))
        mlay.addLayout(ebar)

        self.tree_ecos = QTreeWidget()
        setup_tree_columns(self.tree_ecos, [
            ("eco", "ECO #", 95),
            ("type", "Type", 85),
            ("status", "Workflow Status", 115),
            ("created", "Created Date", 115),
            ("released", "Released Date", 115),
            ("new_cnt", "New #s", 55),
            ("mod_cnt", "Mod #s", 55),
            ("bom_cnt", "BOM Rows", 65),
            ("dwg_reg", "Dwg Reg", 75),
            ("title", "ECO Title", 190),
            ("reason", "Change Summary", 280),
        ])
        self.tree_ecos.itemSelectionChanged.connect(self._on_eco_row_selected)
        self.tree_ecos.itemDoubleClicked.connect(lambda _it, _col: ECOWorkflowDialogQt(self).exec())
        mlay.addWidget(self.tree_ecos, 1)
        main_v_split.addWidget(self.lf_master_log)

        btm_h_split = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_col = QVBoxLayout(left_widget)
        left_col.setContentsMargins(0, 0, 0, 0)

        self.lf_pull_edit = QGroupBox(" 2. Active ECO Details, New ECO Pull && Workflow Control ")
        pgrid = QGridLayout(self.lf_pull_edit)

        pgrid.addWidget(QLabel("Pull New ECO:"), 0, 0)
        pull_row = QHBoxLayout()
        self.cmb_eco_type = QComboBox()
        self.cmb_eco_type.addItems(list(ECO_TYPES))
        self.cmb_eco_type.setCurrentText("PRODUCTION")
        self.cmb_eco_type.currentTextChanged.connect(self._on_eco_type_changed)
        pull_row.addWidget(self.cmb_eco_type)

        pull_row.addWidget(QLabel("Seed:"))
        self.ent_eco_seed = QLineEdit(get_default_seed_for_eco("PRODUCTION"))
        self.ent_eco_seed.setFixedWidth(115)
        self.ent_eco_seed.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_eco_seed.textChanged.connect(self._update_eco_seed_preview)
        pull_row.addWidget(self.ent_eco_seed)

        self.lbl_next_eco = QLabel("Next: ...")
        self.lbl_next_eco.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        pull_row.addWidget(self.lbl_next_eco)
        pull_row.addWidget(make_btn("1. Pull / Request ECO", "designer", self._pull_eco_action))
        pull_row.addStretch(1)
        pgrid.addLayout(pull_row, 0, 1)

        pgrid.addWidget(QLabel("Active ECO & Title:"), 1, 0)
        t_row = QHBoxLayout()
        self.cmb_active_eco = QComboBox()
        self.cmb_active_eco.setFixedWidth(135)
        self.cmb_active_eco.currentTextChanged.connect(self._load_selected_eco_into_editor)
        t_row.addWidget(self.cmb_active_eco)
        self.ent_eco_title = QLineEdit()
        t_row.addWidget(self.ent_eco_title, 1)
        pgrid.addLayout(t_row, 1, 1)

        pgrid.addWidget(QLabel("Detailed Change Info\n& Engineering Reason:"), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.txt_eco_reason = QTextEdit()
        self.txt_eco_reason.setFixedHeight(68)
        pgrid.addWidget(self.txt_eco_reason, 2, 1)

        bb = QHBoxLayout()
        bb.addWidget(make_btn("Save Info", "designer", self._save_eco_info))
        bb.addWidget(make_btn("Summary Report / PDF...", "viewer", self._show_eco_summary_report))
        btn_wf = make_btn("❖ Manage Workflow / Approvals...", "designer", lambda: ECOWorkflowDialogQt(self).exec())
        btn_wf.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: bold; padding: 5px 14px; border-radius: 4px;")
        bb.addWidget(btn_wf)
        self.lbl_eco_status_badge = QLabel(" ● STATUS: --- ")
        self.lbl_eco_status_badge.setStyleSheet("background-color: #1E293B; color: #38BDF8; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        bb.addWidget(self.lbl_eco_status_badge)
        bb.addStretch(1)
        pgrid.addLayout(bb, 3, 1)

        left_col.addWidget(self.lf_pull_edit, 1)

        self.lf_live_preview = QGroupBox(" 3. Live ECO Summary Report Preview ")
        lplay = QVBoxLayout(self.lf_live_preview)
        self.txt_eco_inspector = QTextEdit()
        self.txt_eco_inspector.setReadOnly(True)
        self.txt_eco_inspector.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lplay.addWidget(self.txt_eco_inspector, 1)
        left_col.addWidget(self.lf_live_preview, 2)

        btm_h_split.addWidget(left_widget)

        right_widget = QWidget()
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(0, 0, 0, 0)

        sw_bar = QHBoxLayout()
        lbl_dv = QLabel("Deliverables View:")
        lbl_dv.setStyleSheet("color: #38BDF8; font-weight: bold;")
        sw_bar.addWidget(lbl_dv)
        self.btn_deliv_smart = make_btn("📋 1. Smart Drawing Checklist", "viewer", lambda: self._switch_deliverables_view("smart"))
        self.btn_deliv_attach = make_btn("📎 2. Registered Drawings & Attachments", "designer", lambda: self._switch_deliverables_view("attach"))
        self.btn_deliv_split = make_btn("⊞ Split View", "viewer", lambda: self._switch_deliverables_view("split"))
        sw_bar.addWidget(self.btn_deliv_smart)
        sw_bar.addWidget(self.btn_deliv_attach)
        sw_bar.addWidget(self.btn_deliv_split)
        sw_bar.addStretch(1)
        right_col.addLayout(sw_bar)

        self.deliv_v_split = QSplitter(Qt.Orientation.Vertical)

        self.lf_smart_dwg = QGroupBox(" Smart Drawing Update Checklist (Click Row to Toggle [✓] / [ ] Checkmark) ")
        sdlay = QVBoxLayout(self.lf_smart_dwg)
        lbl_auto = QLabel("Auto-detected from ECO markups:")
        lbl_auto.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        sdlay.addWidget(lbl_auto)

        self.tree_eco_candidates = QTreeWidget()
        setup_tree_columns(self.tree_eco_candidates, [
            ("chk", "Include?", 65), ("pn", "Part #", 105), ("name", "Description", 180),
            ("role", "Change Type", 155), ("dwg_no", "Drawing #", 120), ("dtype", "Mode", 85)
        ])
        self.tree_eco_candidates.itemClicked.connect(self._on_candidate_row_clicked)
        sdlay.addWidget(self.tree_eco_candidates, 1)

        c_ctrl = QHBoxLayout()
        c_ctrl.addWidget(QLabel("Selected Row Dwg #:"))
        self.ent_cand_dwg = QLineEdit()
        self.ent_cand_dwg.setFixedWidth(120)
        c_ctrl.addWidget(self.ent_cand_dwg)
        c_ctrl.addWidget(QLabel("Mode:"))
        self.cmb_cand_dtype = QComboBox()
        self.cmb_cand_dtype.addItems(DRAWING_TYPES)
        self.cmb_cand_dtype.setFixedWidth(105)
        c_ctrl.addWidget(self.cmb_cand_dtype)
        c_ctrl.addWidget(make_btn("Set Dwg/Mode", "designer", self._apply_cand_dwg_override))
        c_ctrl.addStretch(1)
        c_ctrl.addWidget(make_btn("Apply Checked [✓] Drawings to ECO", "designer", self._save_checked_candidates_to_eco))
        sdlay.addLayout(c_ctrl)
        self.deliv_v_split.addWidget(self.lf_smart_dwg)

        self.lf_reg_attach = QGroupBox(" Official Drawing Registration List && File Attachments ")
        ralay = QVBoxLayout(self.lf_reg_attach)
        self.tree_eco_atts = QTreeWidget()
        setup_tree_columns(self.tree_eco_atts, [
            ("kind", "Item Type", 85), ("ref", "Dwg / File", 160),
            ("status", "Status", 105), ("desc", "Notes", 140), ("path", "Path", 110)
        ])
        self.tree_eco_atts.itemDoubleClicked.connect(lambda _it, _col: self._open_or_jump_from_eco_items())
        ralay.addWidget(self.tree_eco_atts, 1)

        att_bar = QHBoxLayout()
        att_bar.addWidget(QLabel("Attach File:"))
        self.ent_eco_att_path = QLineEdit()
        att_bar.addWidget(self.ent_eco_att_path, 1)
        att_bar.addWidget(make_btn("Browse...", "designer", lambda: self._browse_into(self.ent_eco_att_path)))
        att_bar.addWidget(make_btn("Attach", "designer", self._save_eco_att))
        self.btn_remove_eco_att = make_btn("Remove File", "designer", self._remove_eco_att)
        self.btn_remove_eco_att.setEnabled(False)
        att_bar.addWidget(self.btn_remove_eco_att)
        ralay.addLayout(att_bar)

        abtns = QHBoxLayout()
        abtns.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_eco_atts, "eco_items.csv", self)))
        abtns.addStretch(1)
        abtns.addWidget(make_btn("Open File / Go to Drawing Registration", "viewer", self._open_or_jump_from_eco_items))
        ralay.addLayout(abtns)
        self.deliv_v_split.addWidget(self.lf_reg_attach)

        right_col.addWidget(self.deliv_v_split, 1)
        btm_h_split.addWidget(right_widget)
        btm_h_split.setStretchFactor(0, 1)
        btm_h_split.setStretchFactor(1, 1)

        main_v_split.addWidget(btm_h_split)
        main_v_split.setStretchFactor(0, 2)
        main_v_split.setStretchFactor(1, 3)
        lay.addWidget(main_v_split, 1)

        self._switch_deliverables_view("attach")

    def _switch_deliverables_view(self, mode: str):
        if mode == "smart":
            self.lf_smart_dwg.setVisible(True)
            self.lf_reg_attach.setVisible(False)
            self.btn_deliv_smart.setProperty("role", "designer")
            self.btn_deliv_attach.setProperty("role", "viewer")
            self.btn_deliv_split.setProperty("role", "viewer")
        elif mode == "attach":
            self.lf_smart_dwg.setVisible(False)
            self.lf_reg_attach.setVisible(True)
            self.btn_deliv_smart.setProperty("role", "viewer")
            self.btn_deliv_attach.setProperty("role", "designer")
            self.btn_deliv_split.setProperty("role", "viewer")
        else:
            self.lf_smart_dwg.setVisible(True)
            self.lf_reg_attach.setVisible(True)
            self.btn_deliv_smart.setProperty("role", "viewer")
            self.btn_deliv_attach.setProperty("role", "viewer")
            self.btn_deliv_split.setProperty("role", "designer")
        for b in (self.btn_deliv_smart, self.btn_deliv_attach, self.btn_deliv_split):
            b.style().unpolish(b)
            b.style().polish(b)

    def _update_eco_status_badge(self, eco_num: str = "", status_str: str = ""):
        if not eco_num and hasattr(self, "cmb_active_eco"):
            eco_num = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if eco_num and not status_str:
            with session_scope() as s:
                e = s.get(EngineeringChange, eco_num)
                if e:
                    status_str = (e.status or "OPEN").upper()
        if not status_str:
            self.lbl_eco_status_badge.setText(" ● NO ECO SELECTED ")
            self.lbl_eco_status_badge.setStyleSheet("background-color: #1E293B; color: #94A3B8; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
            return
        fg_col, _ = STATUS_COLORS.get(status_str, ("#38BDF8", "#E0F2FE"))
        self.lbl_eco_status_badge.setText(f" ● {eco_num}: {status_str} ")
        self.lbl_eco_status_badge.setStyleSheet(f"background-color: #0F172A; color: {fg_col}; font-weight: bold; padding: 4px 8px; border: 1px solid {fg_col}; border-radius: 4px;")

    # ==========================================================================
    # TAB 6: DRAWING REGISTRATION
    # ==========================================================================
    def _build_drawing_registration_tab(self):
        lay = QVBoxLayout(self.tab_dwg_reg)
        make_tab_header(lay, self, "STEP 6: DRAWING REGISTRATION VAULT", "TAB_8_DWG_REG")

        reg_frm = QGroupBox(" Register CAD / PDF Drawing (Single, LH/RH Pair, Tabulated) ")
        rl = QVBoxLayout(reg_frm)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Drawing Number:"))
        self.ent_reg_dwg = QLineEdit()
        self.ent_reg_dwg.setFixedWidth(170)
        self.ent_reg_dwg.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_reg_dwg.setPlaceholderText("Defaults to Part #")
        r1.addWidget(self.ent_reg_dwg)
        r1.addWidget(QLabel("Drawing Mode:"))
        self.cmb_reg_dtype = QComboBox()
        self.cmb_reg_dtype.addItems(DRAWING_TYPES)
        self.cmb_reg_dtype.setFixedWidth(130)
        self.cmb_reg_dtype.currentTextChanged.connect(self._on_reg_dtype_changed)
        r1.addWidget(self.cmb_reg_dtype)
        r1.addWidget(QLabel("Governing ECO #:"))
        self.cmb_reg_eco = QComboBox()
        self.cmb_reg_eco.setFixedWidth(220)
        r1.addWidget(self.cmb_reg_eco)
        r1.addStretch(1)
        rl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Linked Part # (Primary / LH):"))
        self.ent_reg_p1 = QLineEdit()
        self.ent_reg_p1.setFixedWidth(140)
        self.ent_reg_p1.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_reg_p1.textChanged.connect(self._sync_default_dwg_from_part)
        r2.addWidget(self.ent_reg_p1)
        r2.addWidget(make_btn("Find...", "viewer", lambda: PartSearchDialogQt(self, self.ent_reg_p1, on_select_callback=self._sync_default_dwg_from_part).exec()))

        self.lbl_reg_p2 = QLabel("Linked Part # 2 (RH / Tabulated):")
        self.ent_reg_p2 = QLineEdit()
        self.ent_reg_p2.setFixedWidth(140)
        self.ent_reg_p2.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.btn_reg_p2 = make_btn("Find...", "viewer", lambda: PartSearchDialogQt(self, self.ent_reg_p2).exec())
        r2.addWidget(self.lbl_reg_p2)
        r2.addWidget(self.ent_reg_p2)
        r2.addWidget(self.btn_reg_p2)
        self.lbl_reg_p2.setVisible(False)
        self.ent_reg_p2.setVisible(False)
        self.btn_reg_p2.setVisible(False)
        r2.addStretch(1)
        rl.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Drawing File Path (PDF):"))
        self.ent_reg_path = QLineEdit()
        r3.addWidget(self.ent_reg_path, 1)
        r3.addWidget(make_btn("Browse...", "designer", lambda: self._browse_into(self.ent_reg_path)))
        r3.addWidget(make_btn("Register Drawing", "designer", self._register_drawing_action))
        rl.addLayout(r3)
        lay.addWidget(reg_frm)

        btm = QGroupBox(" ECO Drawing Registration Checklist (Search by ECO #, Dwg #, or Part #) ")
        blay = QVBoxLayout(btm)
        dbar = QHBoxLayout()
        dbar.addWidget(QLabel("Wildcard Search:"))
        self.ent_dwg_chk_search = make_search_entry(210, "e.g. ECO*2 or 1AF*")
        self.ent_dwg_chk_search.returnPressed.connect(lambda: self._populate_dwg_checklist(force_all=False))
        dbar.addWidget(self.ent_dwg_chk_search)
        dbar.addWidget(make_btn("Search", "viewer", lambda: self._populate_dwg_checklist(force_all=False)))
        dbar.addWidget(make_btn("Show All", "viewer", lambda: self._populate_dwg_checklist(force_all=True)))
        dbar.addWidget(make_btn("Clear", "viewer", self._clear_dwg_checklist))
        self.lbl_dwg_chk_count = QLabel("(Enter a search and click Search, or click Show All)")
        self.lbl_dwg_chk_count.setStyleSheet(f"color: {self.colors['fg_secondary']};")
        dbar.addWidget(self.lbl_dwg_chk_count)
        dbar.addStretch(1)
        blay.addLayout(dbar)

        self.tree_dwg_checklist = QTreeWidget()
        setup_tree_columns(self.tree_dwg_checklist, [
            ("eco", "ECO #", 90), ("status", "ECO Status", 110), ("dwg_no", "Drawing #", 130),
            ("dtype", "Mode", 95), ("pn", "Part #", 100), ("rev", "Rev", 45),
            ("size", "Size", 45), ("reg_status", "Registration Status", 140), ("notes", "Notes", 220)
        ])
        self.tree_dwg_checklist.itemDoubleClicked.connect(self._on_dwg_checklist_double_click)
        blay.addWidget(self.tree_dwg_checklist, 1)
        lay.addWidget(btm, 1)

    # ==========================================================================
    # TAB 7: BOM LOOKUP
    # ==========================================================================
    def _build_bom_lookup_tab(self):
        lay = QVBoxLayout(self.tab_bom_lookup)
        make_tab_header(lay, self, "STEP 7: INDENTED BOM LOOKUP EXPLORER", "TAB_9_LOOKUP")

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Part / Assembly PN:"))
        self.ent_lookup_pn = make_search_entry(165, "e.g. 3PR*1 or 2AS*")
        self.ent_lookup_pn.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_lookup_pn.returnPressed.connect(self._run_bom_lookup)
        bar.addWidget(self.ent_lookup_pn)
        bar.addWidget(make_btn("Find...", "viewer", lambda: PartSearchDialogQt(self, self.ent_lookup_pn, on_select_callback=lambda _p=None: self._run_bom_lookup()).exec()))

        self.rb_lookup_multi = QRadioButton("Full Multi-Level")
        self.rb_lookup_single = QRadioButton("Single-Level Only")
        self.rb_lookup_multi.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_lookup_multi)
        grp.addButton(self.rb_lookup_single)
        bar.addWidget(self.rb_lookup_multi)
        bar.addWidget(self.rb_lookup_single)

        self.chk_lookup_pending = QCheckBox("Pending ECOs")
        self.chk_lookup_pending.toggled.connect(self._run_bom_lookup)
        bar.addWidget(self.chk_lookup_pending)

        bar.addWidget(QLabel("Cond Filter:"))
        self.ent_lookup_cond_filter = make_search_entry(85, "e.g. B04")
        self.ent_lookup_cond_filter.returnPressed.connect(self._run_bom_lookup)
        bar.addWidget(self.ent_lookup_cond_filter)

        bar.addWidget(make_btn("Explode BOM Tree", "viewer", self._run_bom_lookup))
        bar.addStretch(1)
        bar.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_lookup, "indented_bom.csv", self)))
        lay.addLayout(bar)

        self.tree_lookup = QTreeWidget()
        setup_tree_columns(self.tree_lookup, [
            ("tree_pn", "Parent / Child Hierarchy PN", 240), ("desc", "Noun, Description", 230),
            ("type", "Category", 130), ("source_type", "Source", 70), ("cond", "Cond", 50),
            ("supply", "Supply Class", 95), ("find", "Find", 45), ("ext_qty", "Ext Qty", 65),
            ("unit_weight", "Unit Wt", 65), ("ext_weight", "Ext Wt", 65), ("uom", "UOM", 45),
            ("rev", "Rev", 45), ("material", "Material", 130)
        ])
        lay.addWidget(self.tree_lookup, 1)

    # ==========================================================================
    # TAB 8: WHERE-USED
    # ==========================================================================
    def _build_where_used_tab(self):
        lay = QVBoxLayout(self.tab_where_used)
        make_tab_header(lay, self, "STEP 8: WHERE-USED INQUIRY TRACE", "TAB_10_WU")

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Component PN:"))
        self.ent_wu_pn = make_search_entry(165, "e.g. 1AF*5 or 2AS*")
        self.ent_wu_pn.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.ent_wu_pn.returnPressed.connect(self._run_where_used)
        bar.addWidget(self.ent_wu_pn)
        bar.addWidget(make_btn("Find...", "viewer", lambda: PartSearchDialogQt(self, self.ent_wu_pn, on_select_callback=lambda _p=None: self._run_where_used()).exec()))

        self.rb_wu_multi = QRadioButton("Full Multi-Level Up")
        self.rb_wu_single = QRadioButton("Single-Level Up")
        self.rb_wu_multi.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_wu_multi)
        grp.addButton(self.rb_wu_single)
        bar.addWidget(self.rb_wu_multi)
        bar.addWidget(self.rb_wu_single)

        bar.addWidget(make_btn("Trace Where-Used", "viewer", self._run_where_used))
        bar.addStretch(1)
        bar.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_wu, "where_used.csv", self)))
        lay.addLayout(bar)

        self.tree_wu = QTreeWidget()
        setup_tree_columns(self.tree_wu, [
            ("tree_pn", "Where-Used Parent Hierarchy", 280), ("parent_desc", "Parent Noun, Description", 260),
            ("parent_type", "Parent Category", 140), ("cond", "Cond", 55),
            ("supply", "Supply Class", 95), ("qty_per", "Qty Per", 65), ("uom", "UOM", 45), ("rev", "Rev", 45)
        ])
        lay.addWidget(self.tree_wu, 1)

    # ==========================================================================
    # TAB 9: COMPARE BOMS
    # ==========================================================================
    def _build_compare_tab(self):
        lay = QVBoxLayout(self.tab_compare)
        make_tab_header(lay, self, "STEP 9: MULTI-BOM COMPARISON MATRIX", "TAB_11_COMPARE")

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Assembly PNs (2 to 4, comma-separated):"))
        self.ent_comp_pns = make_search_entry(340, "e.g. 3PR00000001, 3PR00000002")
        self.ent_comp_pns.setFont(QFont("Consolas", 9))
        ctrl.addWidget(self.ent_comp_pns)
        self.chk_comp_pending = QCheckBox("Pending ECOs")
        ctrl.addWidget(self.chk_comp_pending)
        ctrl.addWidget(QLabel("Cond Filter:"))
        self.ent_comp_cond_filter = make_search_entry(85, "e.g. B04")
        ctrl.addWidget(self.ent_comp_cond_filter)
        ctrl.addWidget(make_btn("Compare BOMs", "viewer", self._run_compare_boms))
        ctrl.addStretch(1)
        ctrl.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(self.tree_comp, "bom_comparison.csv", self)))
        lay.addLayout(ctrl)

        self.tree_comp = QTreeWidget()
        setup_tree_columns(self.tree_comp, [
            ("pn", "Part Number", 110), ("name", "Noun, Description", 220), ("cat", "Category", 130),
            ("cond", "Cond", 50), ("uom", "UOM", 45), ("rev", "Rev", 45), ("status", "Diff Status", 85),
            ("q1", "Assembly 1 Qty", 95), ("q2", "Assembly 2 Qty", 95), ("q3", "Assembly 3 Qty", 95), ("q4", "Assembly 4 Qty", 95)
        ])
        lay.addWidget(self.tree_comp, 1)

    # ==========================================================================
    # TAB 10: DRAWING VIEWER (LATEST REVISION ONLY + RIGHT-CLICK CONTEXT MENU)
    # ==========================================================================
    def _build_drawing_viewer_tab(self):
        lay = QVBoxLayout(self.tab_dwg_view)
        make_tab_header(lay, self, "STEP 10: DRAWING VIEWER & REVISION VAULT", "TAB_12_DWG_VIEW")

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Wildcard Search:"))
        self.ent_view_dwg_q = make_search_entry(240, "e.g. 1AF*79, 3PR*, or *EAR*")
        self.ent_view_dwg_q.returnPressed.connect(lambda: self._populate_drawing_viewer(force_all=False))
        bar.addWidget(self.ent_view_dwg_q)
        bar.addWidget(make_btn("Search", "viewer", lambda: self._populate_drawing_viewer(force_all=False)))
        bar.addWidget(make_btn("Show All", "viewer", lambda: self._populate_drawing_viewer(force_all=True)))
        bar.addWidget(make_btn("Clear", "viewer", self._clear_drawing_viewer))

        self.lbl_dwg_view_hint = QLabel("💡 Showing Latest Revisions Only — Right-click any drawing row for Revision History or Supplier/Technical Docs")
        self.lbl_dwg_view_hint.setStyleSheet(f"color: {self.colors['accent_primary']}; font-weight: bold; padding-left: 8px;")
        bar.addWidget(self.lbl_dwg_view_hint)

        bar.addStretch(1)
        bar.addWidget(make_btn("Open Highlighted Drawing", "viewer", self._open_selected_drawing_revision))
        lay.addLayout(bar)

        self.tree_dwg_hist = QTreeWidget()
        setup_tree_columns(self.tree_dwg_hist, [
            ("dwg_no", "Drawing #", 145),
            ("dtype", "Drawing Mode", 110),
            ("summary", "Linked Parts Summary", 280),
            ("rev", "Latest Rev", 80),
            ("eco", "ECO #", 95),
            ("reg_by", "Registered By", 115),
            ("size", "Size", 55),
            ("sheets", "Sheets", 60),
            ("status", "Vault State", 125),
            ("date", "Registration Date", 140),
        ])
        self.tree_dwg_hist.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_dwg_hist.customContextMenuRequested.connect(self._show_drawing_context_menu)
        self.tree_dwg_hist.itemDoubleClicked.connect(lambda _it, _col: self._open_selected_drawing_revision())
        lay.addWidget(self.tree_dwg_hist, 1)

    def _clear_drawing_viewer(self):
        self.ent_view_dwg_q.clear()
        self.tree_dwg_hist.clear()

    def _populate_drawing_viewer(self, filter_dwg: Optional[str] = None, force_all: bool = False):
        self.tree_dwg_hist.setSortingEnabled(False)
        self.tree_dwg_hist.clear()
        q = "*" if force_all else self.ent_view_dwg_q.text().strip()
        if not q and not filter_dwg:
            self.tree_dwg_hist.setSortingEnabled(True)
            return
        with session_scope() as s:
            svc = BOMService(s)
            revs = svc.list_drawing_revisions(filter_dwg or q)
            latest_revs = [r for r in revs if r.is_current]
            for rev in latest_revs:
                st = "ACTIVE (LATEST)"
                item = QTreeWidgetItem([
                    rev.drawing_number,
                    rev.drawing_type,
                    rev.linked_parts_summary,
                    rev.revision,
                    rev.eco_number or "-",
                    rev.registered_by,
                    rev.sheet_size,
                    str(rev.sheet_count),
                    st,
                    rev.registered_at.strftime("%Y-%m-%d %H:%M"),
                ])
                fg = QColor(self.colors["accent_success"])
                for c in range(item.columnCount()):
                    item.setForeground(c, QBrush(fg))
                self.tree_dwg_hist.addTopLevelItem(item)
        self.tree_dwg_hist.setSortingEnabled(True)

    def _show_drawing_context_menu(self, pos):
        item = self.tree_dwg_hist.itemAt(pos)
        if not item:
            return
        self.tree_dwg_hist.setCurrentItem(item)
        dwg_no = item.text(0)
        latest_rev = item.text(3)

        with session_scope() as s:
            all_revs = s.scalars(
                select(DrawingRevisionHistory)
                .where(DrawingRevisionHistory.drawing_number == dwg_no)
                .order_by(DrawingRevisionHistory.registered_at.desc())
            ).all()
            supp_docs = s.scalars(
                select(DrawingSupportingDoc)
                .where(DrawingSupportingDoc.drawing_number == dwg_no)
                .order_by(DrawingSupportingDoc.uploaded_at.desc())
            ).all()
            rev_count = len(all_revs)
            doc_count = len(supp_docs)

        menu = QMenu(self)
        act_open = menu.addAction(f"📄 Open Latest Drawing PDF ({dwg_no} — Rev {latest_rev})")
        menu.addSeparator()
        act_hist = menu.addAction(f"📜 View Drawing Revision History ({rev_count} revision{'s' if rev_count != 1 else ''})...")
        act_docs = menu.addAction(f"📎 View Supplier Drawings & Supporting Docs ({doc_count} attached)...")

        chosen = menu.exec(self.tree_dwg_hist.viewport().mapToGlobal(pos))
        if chosen == act_open:
            self._open_selected_drawing_revision()
        elif chosen == act_hist:
            self._open_drawing_history_dialog(dwg_no)
        elif chosen == act_docs:
            self._open_supporting_docs_dialog(dwg_no)

    def _open_drawing_history_dialog(self, dwg_no: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Drawing Revision History — {dwg_no}")
        dlg.resize(980, 420)
        v = QVBoxLayout(dlg)

        hdr = QLabel(f"Complete Revision History for Drawing: {dwg_no} (Double-Click Any Row to Open PDF)")
        hdr.setStyleSheet(f"color: {self.colors['accent_primary']}; font-size: 10pt; font-weight: bold;")
        v.addWidget(hdr)

        tree = QTreeWidget()
        setup_tree_columns(tree, [
            ("dwg_no", "Drawing #", 135),
            ("dtype", "Mode", 95),
            ("summary", "Linked Parts Summary", 220),
            ("rev", "Rev", 55),
            ("eco", "ECO #", 95),
            ("reg_by", "Registered By", 110),
            ("size", "Size", 50),
            ("sheets", "Sheets", 55),
            ("status", "Vault State", 140),
            ("date", "Registration Date", 135),
        ])
        tree.setSortingEnabled(False)

        with session_scope() as s:
            revs = s.scalars(
                select(DrawingRevisionHistory)
                .where(DrawingRevisionHistory.drawing_number == dwg_no)
                .order_by(DrawingRevisionHistory.registered_at.desc(), DrawingRevisionHistory.id.desc())
            ).all()
            for r in revs:
                st = "ACTIVE (LATEST)" if r.is_current else "SUPERSEDED (PREV REV)"
                it = QTreeWidgetItem([
                    r.drawing_number,
                    r.drawing_type,
                    r.linked_parts_summary,
                    r.revision,
                    r.eco_number or "-",
                    r.registered_by,
                    r.sheet_size,
                    str(r.sheet_count),
                    st,
                    r.registered_at.strftime("%Y-%m-%d %H:%M"),
                ])
                it.setData(0, Qt.ItemDataRole.UserRole, r.file_path)
                fg = QColor(self.colors["accent_success"] if r.is_current else self.colors["fg_secondary"])
                for c in range(it.columnCount()):
                    it.setForeground(c, QBrush(fg))
                tree.addTopLevelItem(it)
        tree.setSortingEnabled(True)

        def _open_picked():
            sel = tree.selectedItems()
            if not sel:
                QMessageBox.warning(dlg, "Select Revision", "Please select a revision row first.")
                return
            fpath = sel[0].data(0, Qt.ItemDataRole.UserRole)
            open_file_externally(fpath, dlg)

        tree.itemDoubleClicked.connect(lambda _it, _col: _open_picked())
        v.addWidget(tree, 1)

        btm = QHBoxLayout()
        btm.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(tree, f"{dwg_no}_revision_history.csv", dlg)))
        btm.addStretch(1)
        btm.addWidget(make_btn("Open Selected Revision PDF", "designer", _open_picked))
        btm.addWidget(make_btn("Close", "viewer", dlg.accept))
        v.addLayout(btm)
        dlg.exec()

    def _open_supporting_docs_dialog(self, dwg_no: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Supplier Drawings & Supporting Technical Documents — {dwg_no}")
        dlg.resize(920, 380)
        v = QVBoxLayout(dlg)

        hdr = QLabel(f"Attached Supplier Drawings & Technical Documents for: {dwg_no}")
        hdr.setStyleSheet(f"color: {self.colors['accent_primary']}; font-size: 10pt; font-weight: bold;")
        v.addWidget(hdr)

        tree = QTreeWidget()
        setup_tree_columns(tree, [
            ("dwg_no", "Drawing #", 135),
            ("doc_type", "Document Type", 150),
            ("filename", "File Name", 230),
            ("desc", "Description", 260),
            ("date", "Upload Date", 135),
        ])
        tree.setSortingEnabled(False)

        with session_scope() as s:
            docs = s.scalars(
                select(DrawingSupportingDoc)
                .where(DrawingSupportingDoc.drawing_number == dwg_no)
                .order_by(DrawingSupportingDoc.uploaded_at.desc())
            ).all()
            for doc in docs:
                it = QTreeWidgetItem([
                    doc.drawing_number,
                    doc.doc_type,
                    doc.file_name,
                    doc.description or "-",
                    doc.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                ])
                it.setData(0, Qt.ItemDataRole.UserRole, doc.file_path)
                tree.addTopLevelItem(it)
        tree.setSortingEnabled(True)

        if tree.topLevelItemCount() == 0:
            lbl_empty = QLabel(f"No supplier drawings or supporting technical documents are currently attached to {dwg_no}.")
            lbl_empty.setStyleSheet(f"color: {self.colors['accent_warning']}; font-style: italic; padding: 6px;")
            v.addWidget(lbl_empty)

        def _open_doc():
            sel = tree.selectedItems()
            if not sel:
                QMessageBox.warning(dlg, "Select Document", "Please select a document row first.")
                return
            fpath = sel[0].data(0, Qt.ItemDataRole.UserRole)
            open_file_externally(fpath, dlg)

        tree.itemDoubleClicked.connect(lambda _it, _col: _open_doc())
        v.addWidget(tree, 1)

        btm = QHBoxLayout()
        btm.addWidget(make_btn("Export CSV...", "viewer", lambda: export_tree_to_csv_qt(tree, f"{dwg_no}_supporting_docs.csv", dlg)))
        btm.addStretch(1)
        btm.addWidget(make_btn("Open Selected Document", "designer", _open_doc))
        btm.addWidget(make_btn("Close", "viewer", dlg.accept))
        v.addLayout(btm)
        dlg.exec()

    def _open_selected_drawing_revision(self):
        items = self.tree_dwg_hist.selectedItems()
        if not items:
            QMessageBox.warning(self, "Selection", "Select a drawing row first.")
            return
        dwg_no, rev = items[0].text(0), items[0].text(3)
        with session_scope() as s:
            rev_obj = s.scalar(
                select(DrawingRevisionHistory).where(
                    DrawingRevisionHistory.drawing_number == dwg_no,
                    DrawingRevisionHistory.revision == rev
                )
            )
            if rev_obj:
                open_file_externally(rev_obj.file_path, self)

    # ==========================================================================
    # HANDLERS & ACTIONS (BOM BUILDER, ECO MANAGER, LOOKUP, WHERE-USED, COMPARE)
    # ==========================================================================
    def _load_parent_bom(self):
        p_pn = self._resolve_wildcard_entry_pn(self.ent_bom_parent, self._load_parent_bom)
        if not p_pn:
            return
        self.tree_assembly_bom.setSortingEnabled(False)
        self.tree_assembly_bom.clear()
        with session_scope() as s:
            svc = BOMService(s)
            parent = svc.get_part(p_pn)
            if not parent:
                QMessageBox.critical(self, "Not Found", f"Parent '{p_pn}' does not exist.")
                self.tree_assembly_bom.setSortingEnabled(True)
                return
            self.lbl_parent_info.setText(f"{parent.standard_name} [{parent.part_type}, Rev {parent.revision}]")
            self.lbl_parent_info.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
            data = svc.get_bom_for_editor(p_pn)
            for item in data["items"]:
                self.tree_assembly_bom.addTopLevelItem(QTreeWidgetItem([
                    str(item.find_number or "-"), item.child_pn, item.child.standard_name,
                    f"{item.quantity:g}", item.child.uom, item.condition_code or "-",
                    item.supply_class, data["mode"]
                ]))
        self.tree_assembly_bom.setSortingEnabled(True)
        self.set_status_message(f"Loaded BOM structure for {p_pn}")

    def _on_catalog_double_click(self, item: QTreeWidgetItem, _col: int):
        self._insert_staged_part(item.text(0), item.text(1), item.text(3), item.text(2), item.text(4))

    def _insert_staged_part(self, child_pn: str, desc: str, uom: str, cond: str, _ptype: str):
        parent_pn = self.ent_bom_parent.text().strip().upper()
        if child_pn == parent_pn:
            QMessageBox.warning(self, "Self-Reference", "A parent part cannot contain itself.")
            return
        if parent_pn:
            with session_scope() as s:
                parent_obj = BOMService(s).get_part(parent_pn)
                child_obj = BOMService(s).get_part(child_pn)
                if parent_obj and child_obj:
                    try:
                        BOMService.validate_bom_parent_child_types(parent_obj, child_obj)
                    except ValueError as ve:
                        QMessageBox.warning(self, "Hierarchy Rule Violation", str(ve))
                        return
        for i in range(self.tree_assembly_bom.topLevelItemCount()):
            it = self.tree_assembly_bom.topLevelItem(i)
            if it.text(1) == child_pn:
                it.setText(3, str(float(it.text(3)) + 1.0))
                return
        find_no = (self.tree_assembly_bom.topLevelItemCount() + 1) * 10
        self.tree_assembly_bom.addTopLevelItem(QTreeWidgetItem([
            str(find_no), child_pn, desc, "1", uom, cond, "AVAILABLE", "PENDING"
        ]))

    def _on_assembly_row_double_click(self, item: QTreeWidgetItem, _col: int):
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit BOM Line Item")
        dlg.resize(360, 220)
        grid = QGridLayout(dlg)
        lbl_c = QLabel(f"Child PN: {item.text(1)}")
        lbl_c.setStyleSheet("font-weight: bold;")
        grid.addWidget(lbl_c, 0, 0, 1, 2)
        grid.addWidget(QLabel("Quantity:"), 1, 0)
        ent_q = QLineEdit(item.text(3))
        grid.addWidget(ent_q, 1, 1)
        grid.addWidget(QLabel("Find Number:"), 2, 0)
        ent_f = QLineEdit(item.text(0))
        grid.addWidget(ent_f, 2, 1)
        grid.addWidget(QLabel("Condition Code:"), 3, 0)
        ent_c = QLineEdit(item.text(5))
        grid.addWidget(ent_c, 3, 1)
        grid.addWidget(QLabel("Supply Class:"), 4, 0)
        cmb_sup = QComboBox()
        cmb_sup.addItems(["AVAILABLE", "NOT AVAILABLE"])
        cmb_sup.setCurrentText(item.text(6))
        grid.addWidget(cmb_sup, 4, 1)

        def _save_edit():
            item.setText(3, ent_q.text().strip() or "1")
            item.setText(0, ent_f.text().strip() or "-")
            item.setText(5, ent_c.text().strip().upper())
            item.setText(6, cmb_sup.currentText())
            dlg.accept()

        grid.addWidget(make_btn("Apply", "designer", _save_edit), 5, 1, Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _remove_assembly_child(self):
        for it in self.tree_assembly_bom.selectedItems():
            idx = self.tree_assembly_bom.indexOfTopLevelItem(it)
            if idx >= 0:
                self.tree_assembly_bom.takeTopLevelItem(idx)

    def _move_assembly_row(self, direction: int):
        items = self.tree_assembly_bom.selectedItems()
        if not items:
            return
        self.tree_assembly_bom.setSortingEnabled(False)
        it = items[0]
        idx = self.tree_assembly_bom.indexOfTopLevelItem(it)
        new_idx = max(0, min(idx + direction, self.tree_assembly_bom.topLevelItemCount() - 1))
        if new_idx != idx:
            taken = self.tree_assembly_bom.takeTopLevelItem(idx)
            self.tree_assembly_bom.insertTopLevelItem(new_idx, taken)
            self.tree_assembly_bom.setCurrentItem(taken)

    def _save_bom_markups_action(self):
        p_pn = self.ent_bom_parent.text().strip().upper()
        eco_raw = self.cmb_bom_eco.currentText().split(" | ")[0].strip()
        if not p_pn or not eco_raw:
            QMessageBox.warning(self, "Required", "Load a Parent Assembly and select an Open ECO.")
            return
        rows_to_save = []
        for i in range(self.tree_assembly_bom.topLevelItemCount()):
            it = self.tree_assembly_bom.topLevelItem(i)
            rows_to_save.append({
                "find_number": it.text(0), "child_pn": it.text(1),
                "quantity": float(it.text(3)), "condition_code": it.text(5),
                "supply_class": it.text(6)
            })
        try:
            with session_scope() as s:
                BOMService(s).save_temporary_bom(p_pn, eco_raw, rows_to_save)
            QMessageBox.information(self, "BOM Saved", f"Successfully staged BOM markups for '{p_pn}' under ECO '{eco_raw}'.")
            self.refresh_all_data()
            self.set_status_message(f"Saved BOM markups for {p_pn} under {eco_raw}")
        except Exception as e:
            QMessageBox.critical(self, "BOM Error", str(e))

    def _on_reg_dtype_changed(self, dtype: str):
        vis = (dtype == "LH/RH PAIR")
        self.lbl_reg_p2.setVisible(vis)
        self.ent_reg_p2.setVisible(vis)
        self.btn_reg_p2.setVisible(vis)

    def _on_dwg_checklist_double_click(self, item: QTreeWidgetItem, _col: int):
        eco_no, dwg_no, dtype, part_pn = item.text(0), item.text(2), item.text(3), item.text(4)
        self.ent_reg_dwg.setText(dwg_no)
        self.cmb_reg_dtype.setCurrentText(dtype)
        self._on_reg_dtype_changed(dtype)
        self.ent_reg_p1.setText(part_pn)
        for i in range(self.cmb_reg_eco.count()):
            if self.cmb_reg_eco.itemText(i).startswith(eco_no):
                self.cmb_reg_eco.setCurrentIndex(i)
                break

    def _sync_default_dwg_from_part(self, *_args):
        p1 = self.ent_reg_p1.text().strip().upper()
        curr_dwg = self.ent_reg_dwg.text().strip().upper()
        if p1 and (not curr_dwg or curr_dwg.startswith(("1AF", "2AS", "3PR")) or p1.startswith(curr_dwg) or curr_dwg.startswith(p1)):
            self.ent_reg_dwg.setText(p1)

    def _register_drawing_action(self):
        p1 = self.ent_reg_p1.text().strip().upper()
        dwg = self.ent_reg_dwg.text().strip().upper() or p1
        self.ent_reg_dwg.setText(dwg)
        dtype = self.cmb_reg_dtype.currentText()
        eco_raw = self.cmb_reg_eco.currentText().split(" | ")[0].strip()
        path = self.ent_reg_path.text().strip()
        p2 = self.ent_reg_p2.text().strip().upper()
        if not dwg or not path or not p1:
            QMessageBox.warning(self, "Required", "Drawing Number, File Path, and Primary Part Number are required.")
            return
        links = [{"part_pn": p1, "config_label": "STD"}]
        if dtype == "LH/RH PAIR":
            if not p2:
                QMessageBox.warning(self, "Required", "LH/RH Pair drawings require Part Number 2 (RH).")
                return
            links = [{"part_pn": p1, "config_label": "LH"}, {"part_pn": p2, "config_label": "RH"}]
        elif dtype == "TABULATED" and p2:
            links.append({"part_pn": p2, "config_label": "CONFIG-2"})
        try:
            with session_scope() as s:
                BOMService(s).register_drawing(
                    dwg, path, links, drawing_type=dtype,
                    eco_number=eco_raw or None, sheet_count=detect_pdf_page_count(path)
                )
            QMessageBox.information(self, "Registered", f"Drawing '{dwg}' registered successfully!")
            self.refresh_all_data()
            self.set_status_message(f"Registered drawing {dwg} into vault")
        except Exception as e:
            QMessageBox.critical(self, "Registration Error", str(e))

    def _run_bom_lookup(self):
        asm_pn = self._resolve_wildcard_entry_pn(self.ent_lookup_pn, self._run_bom_lookup)
        if not asm_pn:
            return
        # Keep tree order intact during hierarchical explosion
        self.tree_lookup.setSortingEnabled(False)
        self.tree_lookup.clear()
        inc_p = self.chk_lookup_pending.isChecked()
        single = self.rb_lookup_single.isChecked()
        cond_f = self.ent_lookup_cond_filter.text().strip()
        try:
            with session_scope() as s:
                rows = BOMService(s).get_indented_bom(asm_pn, include_pending=inc_p, single_level_only=single, condition_filter=cond_f)
                for r in rows:
                    self.tree_lookup.addTopLevelItem(QTreeWidgetItem([
                        r["tree_pn"], r["description"], r["type"], r["source_type"],
                        r["condition_code"], r["supply_class"], str(r["find"]),
                        f"{r['ext_qty']:g}", f"{r['unit_weight']:g}", f"{r['ext_weight']:g}",
                        r["uom"], r["revision"], r["material"]
                    ]))
            self.set_status_message(f"Exploded BOM tree for {asm_pn} ({len(rows)} rows)")
        except Exception as e:
            QMessageBox.critical(self, "BOM Lookup Error", str(e))

    def _run_where_used(self):
        t_pn = self._resolve_wildcard_entry_pn(self.ent_wu_pn, self._run_where_used)
        if not t_pn:
            return
        self.tree_wu.setSortingEnabled(False)
        self.tree_wu.clear()
        single = self.rb_wu_single.isChecked()
        try:
            with session_scope() as s:
                rows = BOMService(s).where_used(t_pn, include_pending=True, single_level_only=single)
                for r in rows:
                    self.tree_wu.addTopLevelItem(QTreeWidgetItem([
                        r["tree_pn"], r["parent_description"], r["parent_type"],
                        r["condition_code"], r["supply_class"], f"{r['qty_per']:g}",
                        r["uom"], r["rev"]
                    ]))
            self.set_status_message(f"Traced Where-Used impact for {t_pn} ({len(rows)} parent hits)")
        except Exception as e:
            QMessageBox.critical(self, "Where-Used Error", str(e))

    def _run_compare_boms(self):
        raw = self.ent_comp_pns.text().strip()
        if not raw:
            return
        pns = [p.strip().upper() for p in raw.split(",") if p.strip()]
        self.tree_comp.setSortingEnabled(False)
        self.tree_comp.clear()
        try:
            with session_scope() as s:
                data = BOMService(s).compare_boms(pns, include_pending=self.chk_comp_pending.isChecked(), condition_filter=self.ent_comp_cond_filter.text().strip())
                headers = data["headers"]
                self.tree_comp.setColumnCount(len(headers))
                self.tree_comp.setHeaderLabels(headers)
                for row_data in data["rows"]:
                    item = QTreeWidgetItem([str(x) for x in row_data])
                    fg = QColor(self.colors["accent_warning"] if row_data[6] == "DIFF" else self.colors["accent_success"])
                    for c in range(item.columnCount()):
                        item.setForeground(c, QBrush(fg))
                    self.tree_comp.addTopLevelItem(item)
            self.tree_comp.setSortingEnabled(True)
            self.set_status_message(f"Compared BOMs across {len(pns)} assemblies")
        except Exception as e:
            QMessageBox.critical(self, "Compare Error", str(e))

    def _populate_bom_search(self, force_all: bool = False):
        self.tree_bom_catalog.setSortingEnabled(False)
        self.tree_bom_catalog.clear()
        q = "*" if force_all else self.ent_bom_search.text().strip()
        if not q:
            self.tree_bom_catalog.setSortingEnabled(True)
            return
        with session_scope() as s:
            for p in BOMService(s).search_parts(q):
                self.tree_bom_catalog.addTopLevelItem(QTreeWidgetItem([
                    p.part_number, p.standard_name, p.condition_code or "-",
                    p.uom, p.part_type, p.release_status, p.revision
                ]))
        self.tree_bom_catalog.setSortingEnabled(True)

    def _on_candidate_row_clicked(self, item: QTreeWidgetItem, col: int):
        self.ent_cand_dwg.setText(item.text(4))
        self.cmb_cand_dtype.setCurrentText(item.text(5))
        if col == 0:
            is_now_checked = (item.text(0) != "[✓]")
            item.setText(0, "[✓]" if is_now_checked else "[ ]")
            fg = QColor(self.colors["accent_success"] if is_now_checked else self.colors["fg_secondary"])
            for c in range(item.columnCount()):
                item.setForeground(c, QBrush(fg))

    def _apply_cand_dwg_override(self):
        for item in self.tree_eco_candidates.selectedItems():
            item.setText(0, "[✓]")
            if self.ent_cand_dwg.text().strip():
                item.setText(4, self.ent_cand_dwg.text().strip().upper())
            item.setText(5, self.cmb_cand_dtype.currentText())
            fg = QColor(self.colors["accent_success"])
            for c in range(item.columnCount()):
                item.setForeground(c, QBrush(fg))

    def _save_checked_candidates_to_eco(self):
        eno = self.cmb_active_eco.currentText().strip()
        if not eno:
            return
        selected_rows = []
        for i in range(self.tree_eco_candidates.topLevelItemCount()):
            it = self.tree_eco_candidates.topLevelItem(i)
            if it.text(0) == "[✓]":
                selected_rows.append({
                    "part_pn": it.text(1), "role": it.text(3),
                    "drawing_number": it.text(4), "drawing_type": it.text(5)
                })
        try:
            with session_scope() as s:
                cnt = BOMService(s).sync_eco_drawing_registration_list(eno, selected_rows)
            self.refresh_all_data()
            self._load_selected_eco_into_editor()
            QMessageBox.information(self, "Drawing List Updated", f"Updated ECO '{eno}' with {cnt} checked drawing(s).")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _quick_export_selected_eco_pdf(self):
        eno = self.cmb_active_eco.currentText().strip()
        if not eno:
            return
        with session_scope() as s:
            rep = BOMService(s).generate_eco_summary_report(eno)
        p, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{eno}_Summary_Report.pdf", "PDF Document (*.pdf)")
        if p:
            generate_eco_pdf_file(p, eno, rep)
            QMessageBox.information(self, "PDF Generated", f"Saved PDF to:\n{p}")
            open_file_externally(p, self)

    def _approve_ecr_action(self):
        eno = self.cmb_active_eco.currentText().strip()
        if not eno:
            return
        try:
            with session_scope() as s:
                old_req, new_eco = BOMService(s).approve_eco_request(eno, self.ent_eco_seed.text())
                issued_no = new_eco.eco_number
            self.refresh_all_data()
            self.cmb_active_eco.setCurrentText(issued_no)
            self._load_selected_eco_into_editor()
            self._populate_ecos(force_all=True)
            QMessageBox.information(self, "Request Approved", f"Approved Request '{old_req}' and issued Official ECO Number: {issued_no} (Status: OPEN).")
        except Exception as e:
            QMessageBox.critical(self, "Approve Request Error", str(e))

    def _on_eco_type_changed(self, etype: str):
        self.ent_eco_seed.setText(get_default_seed_for_eco(etype))
        self._update_eco_seed_preview()

    def _update_eco_seed_preview(self):
        try:
            with session_scope() as s:
                nxt = preview_next_eco_number(s, self.ent_eco_seed.text())
                self.lbl_next_eco.setText(f"Next: {nxt}")
                self.lbl_next_eco.setStyleSheet(f"color: {self.colors['accent_success']}; font-weight: bold;")
        except Exception:
            self.lbl_next_eco.setText("Next: Invalid")
            self.lbl_next_eco.setStyleSheet(f"color: {self.colors['accent_danger']}; font-weight: bold;")

    def _pull_eco_action(self):
        role = self.user_settings.get("user_role", "ADMIN (Full Access)")
        if role.startswith("VIEWER"):
            QMessageBox.critical(self, "Permission Denied", "Current role is VIEWER (Read-Only).")
            return
        try:
            with session_scope() as s:
                eco = BOMService(s).pull_eco_number(
                    self.cmb_eco_type.currentText(), self.ent_eco_seed.text(),
                    title=self.ent_eco_title.text() or "New Engineering Change",
                    reason=self.txt_eco_reason.toPlainText().strip()
                )
                eno, st = eco.eco_number, eco.status
            self.refresh_all_data()
            self.cmb_active_eco.setCurrentText(eno)
            self._load_selected_eco_into_editor()
            self._populate_ecos(force_all=True)
            if st == "REQUESTED":
                QMessageBox.information(self, "ECO Request Logged", f"Logged ECO Request '{eno}' (Status: REQUESTED).")
            else:
                QMessageBox.information(self, "ECO Number Pulled", f"Pulled Official ECO Number: {eno} (Status: OPEN).")
        except Exception as e:
            QMessageBox.critical(self, "ECO Error", str(e))

    def _load_selected_eco_into_editor(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            return
        with session_scope() as s:
            svc = BOMService(s)
            ecos = svc.list_ecos()
            eco_obj = next((e for e in ecos if e.eco_number == eno), None)
            if eco_obj:
                self.ent_eco_title.setText(eco_obj.title)
                self.txt_eco_reason.setPlainText(eco_obj.reason)
                self.btn_remove_eco_att.setEnabled(eco_obj.status == "OPEN")
                self._update_eco_status_badge(eno, eco_obj.status)

                rep = svc.generate_eco_summary_report(eno)
                insert_colored_eco_report_qt(self.txt_eco_inspector, rep)

                self.tree_eco_candidates.setSortingEnabled(False)
                self.tree_eco_candidates.clear()
                for cand in svc.get_eco_drawing_candidates(eno):
                    chk_str = "[✓]" if cand["checked"] else "[ ]"
                    it = QTreeWidgetItem([
                        chk_str, cand["part_pn"], cand["name"],
                        cand["role"], cand["drawing_number"], cand["drawing_type"]
                    ])
                    fg = QColor(self.colors["accent_success"] if cand["checked"] else self.colors["fg_secondary"])
                    for c in range(it.columnCount()):
                        it.setForeground(c, QBrush(fg))
                    self.tree_eco_candidates.addTopLevelItem(it)
                self.tree_eco_candidates.setSortingEnabled(True)

                self.tree_eco_atts.setSortingEnabled(False)
                self.tree_eco_atts.clear()
                for reg in svc.list_drawing_registration_items(eno):
                    st = "REGISTERED" if reg.is_registered else "PENDING"
                    self.tree_eco_atts.addTopLevelItem(QTreeWidgetItem(["DRAWING", reg.drawing_number, st, reg.notes, reg.part_pn]))
                for att in svc.list_eco_attachments(eno):
                    self.tree_eco_atts.addTopLevelItem(QTreeWidgetItem(["ATTACHMENT", att.file_name, "ATTACHED", att.description or "-", att.file_path]))
                self.tree_eco_atts.setSortingEnabled(True)

    def _on_eco_row_selected(self):
        items = self.tree_ecos.selectedItems()
        if not items:
            return
        eno = items[0].text(0)
        self.cmb_active_eco.setCurrentText(eno)
        self._load_selected_eco_into_editor()

    def _save_eco_info(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            return
        try:
            with session_scope() as s:
                BOMService(s).update_eco_info(eno, self.ent_eco_title.text(), self.txt_eco_reason.toPlainText().strip())
            self.refresh_all_data()
            self._populate_ecos(force_all=True)
            QMessageBox.information(self, "Saved", f"Updated ECO '{eno}' details.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _show_eco_summary_report(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            return
        with session_scope() as s:
            rep = BOMService(s).generate_eco_summary_report(eno)
        ECOSummaryReportModalQt(self, eno, rep).exec()

    def _submit_eco_action(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            return
        try:
            with session_scope() as s:
                BOMService(s).submit_eco_for_approval(eno)
            self.refresh_all_data()
            self._populate_ecos(force_all=True)
            QMessageBox.information(self, "Submitted", f"Submitted ECO '{eno}' for approval.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _approve_eco_action(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            return
        try:
            with session_scope() as s:
                BOMService(s).approve_eco(eno)
            self.refresh_all_data()
            self._populate_ecos(force_all=True)
            QMessageBox.information(self, "Approved", f"Approved ECO '{eno}'.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _reject_eco_action(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            QMessageBox.warning(self, "No Active ECO", "Please select an active ECO first.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Reject ECO — {eno}")
        dlg.resize(480, 280)
        lay = QVBoxLayout(dlg)
        lbl = QLabel(f"Reject ECO '{eno}' Back to Engineering:\nEnter correction notes / required changes:")
        lbl.setStyleSheet("font-weight: bold;")
        lay.addWidget(lbl)
        txt_box = QTextEdit()
        lay.addWidget(txt_box, 1)

        bbar = QHBoxLayout()
        bbar.addStretch(1)
        bbar.addWidget(make_btn("Cancel", "viewer", dlg.reject))

        def _confirm_reject():
            reason = txt_box.toPlainText().strip()
            if not reason:
                QMessageBox.warning(dlg, "Reason Required", "Please enter rejection notes explaining what needs to be corrected.")
                return
            try:
                with session_scope() as s:
                    BOMService(s).reject_eco(eno, reason)
                self.refresh_all_data()
                self._load_selected_eco_into_editor()
                self._populate_ecos(force_all=True)
                dlg.accept()
                QMessageBox.information(self, "ECO Rejected", f"ECO '{eno}' has been returned to OPEN status for corrections.")
            except Exception as e:
                QMessageBox.critical(dlg, "Rejection Error", str(e))

        bbar.addWidget(make_btn("Confirm Rejection", "approver", _confirm_reject))
        lay.addLayout(bbar)
        dlg.exec()

    def _release_eco(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            return
        try:
            with session_scope() as s:
                BOMService(s).release_eco(eno)
            self.refresh_all_data()
            self._populate_ecos(force_all=True)
            QMessageBox.information(self, "Released", f"Released ECO '{eno}' successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Release Error", str(e))

    def _browse_into(self, entry_widget: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(self, "Select File")
        if p:
            entry_widget.setText(p)

    def _save_eco_att(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        p = self.ent_eco_att_path.text().strip()
        if not eno or not p:
            return
        try:
            with session_scope() as s:
                BOMService(s).attach_file_to_eco(eno, p, description="Attached via ECO Manager")
            self.ent_eco_att_path.clear()
            self.refresh_all_data()
            self._load_selected_eco_into_editor()
            QMessageBox.information(self, "Attached", "File attached to ECO successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _clear_eco_search(self):
        self.ent_eco_search.clear()
        self.tree_ecos.clear()
        self.lbl_eco_count.setText("(Enter a search above to display ECOs)")

    def _populate_ecos(self, force_all: bool = False):
        self.tree_ecos.setSortingEnabled(False)
        self.tree_ecos.clear()
        q = "*" if force_all else self.ent_eco_search.text().strip()
        if not q:
            self.lbl_eco_count.setText("(Enter a search and click Search, or click Show All)")
            self.tree_ecos.setSortingEnabled(True)
            return
        tag_colors = {
            "REQUESTED": "#F472B6",
            "OPEN": self.colors["accent_primary"],
            "PENDING_APPROVAL": self.colors["accent_warning"],
            "APPROVED": "#C084FC",
            "RELEASED": self.colors["accent_success"],
        }
        with session_scope() as s:
            svc = BOMService(s)
            ecos = svc.search_ecos(q)
            counts_map = svc.get_eco_counts_bulk([e.eco_number for e in ecos])
            for e in ecos:
                st = counts_map.get(e.eco_number, {"new": 0, "mod": 0, "bom": 0, "reg_done": 0, "reg_total": 0})
                reg_str = f"{st['reg_done']}/{st['reg_total']} Reg" if st["reg_total"] else "0 Req"
                created_str = _fmt_dt(getattr(e, "created_at", None))
                released_str = _fmt_dt(getattr(e, "released_at", None))
                it = QTreeWidgetItem([
                    e.eco_number,
                    e.eco_type,
                    e.status,
                    created_str,
                    released_str,
                    str(st["new"]),
                    str(st["mod"]),
                    str(st["bom"]),
                    reg_str,
                    e.title,
                    e.reason.replace("\n", " "),
                ])
                fg = QColor(tag_colors.get(e.status, self.colors["fg_primary"]))
                for c in range(it.columnCount()):
                    it.setForeground(c, QBrush(fg))
                self.tree_ecos.addTopLevelItem(it)
            self.lbl_eco_count.setText(f"Showing {len(ecos)} ECO(s)")
        self.tree_ecos.setSortingEnabled(True)

    def _remove_eco_att(self):
        eno = self.cmb_active_eco.currentText().split(" | ")[0].strip()
        if not eno:
            QMessageBox.warning(self, "No Active ECO", "Please select an Open ECO first.")
            return
        items = self.tree_eco_atts.selectedItems()
        if not items:
            QMessageBox.warning(self, "Select Attachment", "Please highlight an ATTACHMENT row to remove.")
            return
        it = items[0]
        kind, file_name, file_path = it.text(0), it.text(1), it.text(4)
        if kind != "ATTACHMENT":
            QMessageBox.warning(self, "Not an Attachment", "Only attached files (Item Type: ATTACHMENT) can be removed with this button.")
            return
        if QMessageBox.question(self, "Confirm Remove File", f"Remove attached file '{file_name}' from ECO '{eno}'?") != QMessageBox.StandardButton.Yes:
            return
        try:
            with session_scope() as s:
                removed = BOMService(s).remove_eco_attachment(eno, file_name, file_path)
            self.refresh_all_data()
            self._load_selected_eco_into_editor()
            QMessageBox.information(self, "Attachment Removed", f"Removed '{removed}' from ECO '{eno}'.")
        except Exception as e:
            QMessageBox.critical(self, "Cannot Remove File", str(e))

    def _open_or_jump_from_eco_items(self):
        items = self.tree_eco_atts.selectedItems()
        active_eco = self.cmb_active_eco.currentText().split(" | ")[0].strip()

        if not items:
            self.notebook.setCurrentWidget(self.tab_dwg_reg)
            for i in range(self.cmb_reg_eco.count()):
                if self.cmb_reg_eco.itemText(i).startswith(active_eco):
                    self.cmb_reg_eco.setCurrentIndex(i)
                    break
            return

        it = items[0]
        kind, ref_str, path_or_pn = it.text(0), it.text(1), it.text(4)
        if kind == "ATTACHMENT":
            open_file_externally(path_or_pn, self)
            return

        dwg_no = ref_str.strip()
        part_pn = path_or_pn.strip()
        dtype = "SINGLE"
        with session_scope() as s:
            regs = BOMService(s).list_drawing_registration_items(active_eco if active_eco else None)
            for r in regs:
                if r.drawing_number == dwg_no and r.part_pn == part_pn:
                    dtype = r.drawing_type
                    active_eco = r.eco_number
                    break

        self.notebook.setCurrentWidget(self.tab_dwg_reg)
        self.ent_reg_dwg.setText(dwg_no)
        self.cmb_reg_dtype.setCurrentText(dtype)
        self._on_reg_dtype_changed(dtype)
        self.ent_reg_p1.setText(part_pn)
        for i in range(self.cmb_reg_eco.count()):
            if self.cmb_reg_eco.itemText(i).startswith(active_eco):
                self.cmb_reg_eco.setCurrentIndex(i)
                break
        if active_eco:
            self.ent_dwg_chk_search.setText(active_eco)
            self._populate_dwg_checklist(force_all=False)

    def _clear_dwg_checklist(self):
        self.ent_dwg_chk_search.clear()
        self.tree_dwg_checklist.clear()
        self.lbl_dwg_chk_count.setText("(Enter a search and click Search, or click Show All)")

    def _populate_dwg_checklist(self, force_all: bool = False):
        self.tree_dwg_checklist.setSortingEnabled(False)
        self.tree_dwg_checklist.clear()
        q = "*" if force_all else self.ent_dwg_chk_search.text().strip()
        if not q:
            self.lbl_dwg_chk_count.setText("(Enter a search and click Search, or click Show All)")
            self.tree_dwg_checklist.setSortingEnabled(True)
            return
        with session_scope() as s:
            items = BOMService(s).search_drawing_registration_items(q)
            for reg in items:
                st = "REGISTERED" if reg.is_registered else "PENDING REGISTRATION"
                it = QTreeWidgetItem([
                    reg.eco_number, reg.eco_rel.status, reg.drawing_number,
                    reg.drawing_type, reg.part_pn, reg.target_rev,
                    reg.sheet_size, st, reg.notes
                ])
                fg = QColor(self.colors["accent_success"] if reg.is_registered else self.colors["accent_warning"])
                for c in range(it.columnCount()):
                    it.setForeground(c, QBrush(fg))
                self.tree_dwg_checklist.addTopLevelItem(it)
            self.lbl_dwg_chk_count.setText(f"Showing {len(items)} checklist item(s)")
        self.tree_dwg_checklist.setSortingEnabled(True)

    def refresh_all_data(self):
        with session_scope() as s:
            meta = BOMService(s).get_fast_dropdown_metadata()
            noun_prefixes = meta["noun_prefixes"]
            mat_names = meta["mat_names"]
            open_labels = meta["open_labels"]
            all_eco_nos = meta["all_eco_nos"]

            for panel in (self.tab_part_setup, self.tab_sub_setup, self.tab_prod_setup):
                panel.refresh_panel(noun_prefixes, mat_names, open_labels)

            for cmb in (self.cmb_bom_eco, self.cmb_reg_eco):
                curr = cmb.currentText()
                cmb.clear()
                cmb.addItems(open_labels)
                if curr and cmb.findText(curr) >= 0:
                    cmb.setCurrentText(curr)
                elif open_labels:
                    cmb.setCurrentIndex(0)

            curr_active = self.cmb_active_eco.currentText()
            self.cmb_active_eco.blockSignals(True)
            self.cmb_active_eco.clear()
            self.cmb_active_eco.addItems(all_eco_nos)
            if curr_active and self.cmb_active_eco.findText(curr_active) >= 0:
                self.cmb_active_eco.setCurrentText(curr_active)
            elif all_eco_nos:
                self.cmb_active_eco.setCurrentIndex(0)
            self.cmb_active_eco.blockSignals(False)

        self._update_eco_seed_preview()
        if self.cmb_active_eco.currentText().strip():
            self._load_selected_eco_into_editor()
        self.set_status_message(f"Workspace synchronized ({len(open_labels)} Open ECOs available)")


_running_main_window: Optional[BOMPyQtApp] = None


def launch_pyqt_app():
    global _running_main_window
    os.environ["XMODIFIERS"] = "@im=none"
    app = QApplication.instance() or QApplication(sys.argv)

    login = LoginDialogQt()
    if login.exec() == QDialog.DialogCode.Accepted and login.authenticated_user:
        _running_main_window = BOMPyQtApp(login.authenticated_user)
        _running_main_window.show()
        _running_main_window.raise_()
        _running_main_window.activateWindow()
        app.exec()


if __name__ == "__main__":
    launch_pyqt_app()
