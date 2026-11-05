
"""Main entry point for the Engineering BOM & ECO Management System (PyQt6)."""
import os
import sys

os.environ["XMODIFIERS"] = "@im=none"

from database import init_db, ensure_users_and_audit_columns
from qt_gui import launch_pyqt_app

if __name__ == "__main__":
    init_db()
    ensure_users_and_audit_columns()
    launch_pyqt_app()
