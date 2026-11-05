"""Application configuration and engineering constants (v7.0)."""
import os

DEFAULT_SQLITE_URL = "sqlite:///engineering_bom.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
ECHO_SQL = os.getenv("ECHO_SQL", "false").lower() in ("true", "1", "yes")

STARTING_CODES = {
    "PART": "1AF00000000",
    "PRODUCTION SUBASSEMBLY": "2AS00000000",
    "PRODUCT": "3PR00000000",
}

ECO_STARTING_CODES = {
    "PRODUCTION": "ECO-000000",
    "PROTOTYPE": "PECO-000000",
}

BULK_UOM_OPTIONS = ["ML", "L", "OZ", "GAL", "IN", "FT", "MM", "M", "G", "KG", "LB", "AR"]
DRAWING_SHEET_SIZES = ["A", "B", "C", "D", "E", "A0", "A1", "A2", "A3", "A4", "NONE"]
DRAWING_TYPES = ["SINGLE", "LH/RH PAIR", "TABULATED"]
FINISH_OPTIONS = ["RAW", "PAINTED", "PLATED", "N/A"]
SUPPLY_CLASS_OPTIONS = ["AVAILABLE", "NOT AVAILABLE"]

ECR_STARTING_CODE = "ECR-000000"
