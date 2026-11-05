"""Automatic Sequence Generator with MariaDB Row-Level Locking (`SELECT ... FOR UPDATE`)."""
import re
from typing import Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import PartNumberSequence, Part, EngineeringChange
from config import STARTING_CODES, ECO_STARTING_CODES
from settings_manager import load_user_settings


def get_default_seed_for_type(part_type: str) -> str:
    key = part_type.strip().upper()
    try:
        settings = load_user_settings()
        custom_codes = settings.get("starting_codes", {})
        if isinstance(custom_codes, dict) and custom_codes.get(key):
            return str(custom_codes[key]).strip().upper()
    except Exception:
        pass
    return STARTING_CODES.get(key, STARTING_CODES["PART"])


def get_default_seed_for_eco(eco_type: str) -> str:
    return ECO_STARTING_CODES.get(eco_type.strip().upper(), ECO_STARTING_CODES["PRODUCTION"])


def parse_starting_code(code_seed: str) -> Tuple[str, int, int]:
    match = re.match(r"^(.*?)(\d+)$", code_seed.strip())
    if not match:
        raise ValueError(f"Starting code '{code_seed}' must end with numeric digits.")
    return match.group(1).upper(), len(match.group(2)), int(match.group(2))


def sync_sequence_with_seed(session: Session, code_seed: str) -> None:
    """Ensures PartNumberSequence table reflects the configured prefix, digit length, and minimum base value."""
    prefix, width, base_int = parse_starting_code(code_seed)
    seq = session.scalar(select(PartNumberSequence).where(PartNumberSequence.prefix == prefix))
    if not seq:
        seq = PartNumberSequence(prefix=prefix, digits_length=width, current_val=base_int)
        session.add(seq)
    else:
        seq.digits_length = width
        if base_int > seq.current_val:
            seq.current_val = base_int
    session.commit()


def _preview_seq(session: Session, code_seed: str, model_col) -> str:
    prefix, width, base_int = parse_starting_code(code_seed)
    seq = session.scalar(select(PartNumberSequence).where(PartNumberSequence.prefix == prefix))
    effective_base = max(seq.current_val, base_int) if seq else base_int
    next_val = effective_base + 1
    while True:
        cand = f"{prefix}{str(next_val).zfill(width)}"
        if not session.scalar(select(model_col).where(model_col == cand)):
            return cand
        next_val += 1


def _generate_seq(session: Session, code_seed: str, model_col) -> str:
    prefix, width, base_int = parse_starting_code(code_seed)
    stmt = select(PartNumberSequence).where(PartNumberSequence.prefix == prefix).with_for_update()
    seq = session.scalar(stmt)
    if not seq:
        seq = PartNumberSequence(prefix=prefix, digits_length=width, current_val=base_int)
        session.add(seq)
        session.flush()
    else:
        seq.digits_length = width
        if base_int > seq.current_val:
            seq.current_val = base_int
    while True:
        seq.current_val += 1
        cand = f"{seq.prefix}{str(seq.current_val).zfill(seq.digits_length)}"
        if not session.scalar(select(model_col).where(model_col == cand)):
            session.commit()
            return cand


def preview_next_part_number(session: Session, code_seed: str) -> str:
    return _preview_seq(session, code_seed, Part.part_number)


def generate_next_part_number(session: Session, code_seed: str) -> str:
    return _generate_seq(session, code_seed, Part.part_number)


def preview_next_eco_number(session: Session, code_seed: str) -> str:
    return _preview_seq(session, code_seed, EngineeringChange.eco_number)


def generate_next_eco_number(session: Session, code_seed: str) -> str:
    return _generate_seq(session, code_seed, EngineeringChange.eco_number)
