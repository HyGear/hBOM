"""
Persistent User Settings, Role Governance & Theme Manager for hBOM.
"""

import os
import json
from typing import Dict, List

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_settings.json")
DEFAULT_VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault_storage")

USER_ROLES = ["ADMIN (Full Access)", "APPROVER (Can Approve & Release)", "DESIGNER (Draft & Markup Only)", "VIEWER (Read-Only)"]

THEME_PRESETS: Dict[str, Dict[str, str]] = {
    "Slate & Steel Blue (Default)": {
        "bg_primary": "#182232",
        "bg_secondary": "#0F172A",
        "bg_surface": "#263349",
        "fg_primary": "#E2E8F0",
        "fg_secondary": "#94A3B8",
        "accent_primary": "#3B82F6",
        "accent_success": "#2DD4BF",
        "accent_warning": "#F59E0B",
        "accent_danger": "#F87171",
    },
    "Obsidian & Emerald": {
        "bg_primary": "#111827",
        "bg_secondary": "#090D16",
        "bg_surface": "#1F2937",
        "fg_primary": "#F3F4F6",
        "fg_secondary": "#9CA3AF",
        "accent_primary": "#10B981",
        "accent_success": "#34D399",
        "accent_warning": "#FBBF24",
        "accent_danger": "#EF4444",
    },
    "Charcoal & Amethyst": {
        "bg_primary": "#1E1B2E",
        "bg_secondary": "#13111C",
        "bg_surface": "#2D2844",
        "fg_primary": "#EDE9FE",
        "fg_secondary": "#A78BFA",
        "accent_primary": "#8B5CF6",
        "accent_success": "#38BDF8",
        "accent_warning": "#F59E0B",
        "accent_danger": "#FB7185",
    },
    "Midnight & Amber Gold": {
        "bg_primary": "#1C2430",
        "bg_secondary": "#10151C",
        "bg_surface": "#2B3648",
        "fg_primary": "#F8FAFC",
        "fg_secondary": "#94A3B8",
        "accent_primary": "#D97706",
        "accent_success": "#38BDF8",
        "accent_warning": "#FBBF24",
        "accent_danger": "#F87171",
    },
}

DEFAULT_SETTINGS = {
    "drawing_standard": "BOTH (ISO + ANSI)",
    "default_drawing_size": "A3",
    "unit_system": "METRIC (mm, kg, mL, L)",
    "active_user": "J. Engineer",
    "user_role": "ADMIN (Full Access)",
    "vault_root": DEFAULT_VAULT_DIR,
    "managed_vault_copy": True,
    "theme_name": "Slate & Steel Blue (Default)",
    "colors": dict(THEME_PRESETS["Slate & Steel Blue (Default)"]),
}


def load_user_settings() -> Dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            colors = dict(DEFAULT_SETTINGS["colors"])
            if isinstance(data.get("colors"), dict):
                colors.update(data["colors"])
            merged["colors"] = colors
            return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_user_settings(settings_dict: Dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings_dict, f, indent=2)


def get_active_drawing_sizes(settings_dict: Dict) -> List[str]:
    std = settings_dict.get("drawing_standard", "BOTH (ISO + ANSI)")
    if std.startswith("ISO"):
        return ["A4", "A3", "A2", "A1", "A0", "NONE"]
    if std.startswith("ANSI"):
        return ["A", "B", "C", "D", "E", "NONE"]
    return ["A4", "A3", "A2", "A1", "A0", "A", "B", "C", "D", "E", "NONE"]


def get_active_bulk_uoms(settings_dict: Dict) -> List[str]:
    unit_sys = settings_dict.get("unit_system", "METRIC (mm, kg, mL, L)")
    if unit_sys.startswith("METRIC"):
        return ["ML", "L", "MM", "M", "G", "KG", "AR", "IN", "FT", "OZ", "GAL", "LB"]
    return ["IN", "FT", "OZ", "GAL", "LB", "AR", "ML", "L", "MM", "M", "G", "KG"]


def get_envelope_unit_hint(settings_dict: Dict) -> str:
    unit_sys = settings_dict.get("unit_system", "METRIC (mm, kg, mL, L)")
    if unit_sys.startswith("METRIC"):
        return "(mm: LXWXH, Wt in kg)"
    return "(in: LXWXH, Wt in lb)"
