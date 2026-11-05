from sqlalchemy import inspect as sa_inspect
from models import UserAccount
import hashlib
"""
High-Efficiency Engineering BOM & ECO Service Layer (hBOM Engine v2.0):
- Single-Query Bulk Adjacency Graph for Indented BOM, Where-Used & Cycle Detection (eliminates N+1 queries)
- Preserves SUPERSEDED BOM rows on ECO release for historical auditability
- Rolls up Extended Weight (`ext_weight`) across all assembly levels
- Supports Condition Code Filtering (e.g. 'B01, V02') on BOM Lookup & Multi-BOM Comparison
- Computes SHA-256 checksums and copies files into Managed Vault on Drawing/ECO attachment registration
- Enforces User Role permissions and records `created_by`, `approved_by`, and `released_by`
"""

import os
import re
import datetime
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session, joinedload

from models import (
    Noun, Material, Part, PartPendingUpdate, BOMItem,
    Drawing, DrawingPartLink, DrawingRevisionHistory, DrawingSupportingDoc,
    EngineeringChange, ECOAttachment, ECODrawingRegistrationItem,
    PART_TYPES, SOURCE_TYPES, ECO_TYPES, SUPPLY_CLASSES
)
from pn_generator import (
    generate_next_part_number, get_default_seed_for_type,
    generate_next_eco_number, get_default_seed_for_eco
)
from vault_manager import store_in_managed_vault
from settings_manager import load_user_settings


def detect_pdf_page_count(file_path: str) -> int:
    if not file_path or not file_path.lower().endswith(".pdf") or not os.path.isfile(file_path):
        return 1
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        matches = re.findall(rb"/Type\s*/Page\b", data)
        return max(1, len(matches))
    except Exception:
        return 1


class BOMService:
    def _relink_eco_children(self, old_eco_num: str, new_eco_num: str):
        """Safely migrates all child foreign keys when an ECR/PECO number changes or is approved."""
        from models import Part, PartPendingUpdate, BOMItem, Drawing, DrawingRevisionHistory, ECODrawingRegistrationItem, ECOAttachment
        with self.session.no_autoflush:
            if old_eco_num and new_eco_num and old_eco_num != new_eco_num:
                self.session.query(BOMItem).filter(BOMItem.eco_number == old_eco_num).update({BOMItem.eco_number: new_eco_num}, synchronize_session=False)
                self.session.query(Part).filter(Part.eco_number == old_eco_num).update({Part.eco_number: new_eco_num}, synchronize_session=False)
                self.session.query(PartPendingUpdate).filter(PartPendingUpdate.eco_number == old_eco_num).update({PartPendingUpdate.eco_number: new_eco_num}, synchronize_session=False)
                self.session.query(Drawing).filter(Drawing.eco_number == old_eco_num).update({Drawing.eco_number: new_eco_num}, synchronize_session=False)
                self.session.query(DrawingRevisionHistory).filter(DrawingRevisionHistory.eco_number == old_eco_num).update({DrawingRevisionHistory.eco_number: new_eco_num}, synchronize_session=False)
                self.session.query(ECODrawingRegistrationItem).filter(ECODrawingRegistrationItem.eco_number == old_eco_num).update({ECODrawingRegistrationItem.eco_number: new_eco_num}, synchronize_session=False)
                self.session.query(ECOAttachment).filter(ECOAttachment.eco_number == old_eco_num).update({ECOAttachment.eco_number: new_eco_num}, synchronize_session=False)
            # Also repair any orphaned None eco_numbers in session before flush
            target_num = new_eco_num or old_eco_num
            if target_num:
                for obj in list(self.session.dirty) + list(self.session.new):
                    if isinstance(obj, BOMItem) and not getattr(obj, "eco_number", None):
                        obj.eco_number = target_num

    def __init__(self, session: Session):
        self.session = session
        from sqlalchemy import event
        from models import BOMItem
        @event.listens_for(self.session, "before_flush")
        def _prevent_null_bom_eco(session, flush_context, instances):
            for obj in session.dirty:
                if isinstance(obj, BOMItem) and obj.eco_number is None:
                    hist = sa_inspect(obj).attrs.eco_number.history
                    if hist.deleted:
                        obj.eco_number = hist.deleted[0]

        self.settings = load_user_settings()


    # --- User Authentication & Administration ---
    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256((password or "").encode("utf-8")).hexdigest()

    def get_active_userid(self) -> str:
        settings = load_user_settings()
        return (settings.get("active_userid") or settings.get("active_user") or "admin").strip().lower()

    def authenticate_user(self, userid: str, password: str) -> UserAccount:
        uid = (userid or "").strip().lower()
        if not uid or not password:
            raise ValueError("Please enter both User ID and Password.")
        user = self.session.scalar(select(UserAccount).where(UserAccount.userid == uid))
        if not user:
            raise ValueError(f"User ID '{uid}' does not exist.")
        if (user.status or "ACTIVE").upper() != "ACTIVE":
            raise ValueError(f"Account '{uid}' is currently INACTIVE. Please contact an Administrator.")
        if user.password_hash != self._hash_password(password):
            raise ValueError("Invalid password.")
        return user

    def list_users(self) -> List[UserAccount]:
        return list(self.session.scalars(select(UserAccount).order_by(UserAccount.userid)).all())

    def save_or_update_user(self, userid: str, role: str, full_name: str, status: str, email: str, new_password: Optional[str] = None) -> UserAccount:
        uid = (userid or "").strip().lower()
        if not uid:
            raise ValueError("User ID is required.")
        if not full_name or not full_name.strip():
            raise ValueError("Full Name is required.")
        st = (status or "ACTIVE").strip().upper()

        user = self.session.scalar(select(UserAccount).where(UserAccount.userid == uid))
        if user is None:
            pwd = (new_password or "demo").strip()
            user = UserAccount(
                userid=uid, password_hash=self._hash_password(pwd),
                role=role, full_name=full_name.strip(), status=st, email=(email or "").strip()
            )
            self.session.add(user)
        else:
            if uid == "admin" and st != "ACTIVE":
                raise ValueError("The primary 'admin' account cannot be set to INACTIVE.")
            user.role = role
            user.full_name = full_name.strip()
            user.status = st
            user.email = (email or "").strip()
            if new_password and new_password.strip():
                user.password_hash = self._hash_password(new_password.strip())
        self.session.flush()
        return user

    def _check_write_permission(self, require_approver: bool = False):
        role = self.settings.get("user_role", "ADMIN (Full Access)")
        if role.startswith("VIEWER"):
            raise PermissionError("Current role is VIEWER (Read-Only). Switch role in Tab 13 Settings to make changes.")
        if require_approver and role.startswith("DESIGNER"):
            raise PermissionError("Current role is DESIGNER. Approving or releasing an ECO requires APPROVER or ADMIN role.")

    @property
    def active_user(self) -> str:
        return (self.settings.get("active_user") or "J. Engineer").strip()

    def parse_and_validate_noun_desc(self, noun_desc_input: str) -> Tuple[Noun, str]:
        raw = (noun_desc_input or "").strip()
        if "," not in raw:
            raise ValueError("Format must be 'NOUN, Description' separated by a comma (e.g., 'BRACKET, Mount Ear 10mm').")
        noun_part, desc_part = raw.split(",", 1)
        clean_noun = noun_part.strip().upper()
        clean_desc = desc_part.strip()
        if not clean_noun or not clean_desc:
            raise ValueError("Both Noun and Description are required.")
        noun_obj = self.session.scalar(select(Noun).where(Noun.name == clean_noun))
        if not noun_obj:
            raise ValueError(f"Noun '{clean_noun}' does not exist in Noun Database (Tab 1).")
        return noun_obj, clean_desc

    @staticmethod
    def validate_bom_parent_child_types(parent: Part, child: Part) -> None:
        """
        Enforces strict multi-tier BOM hierarchy:
        1. A top-level PRODUCT (3PR...) may ONLY contain PRODUCTION SUBASSEMBLY (2AS...) items at Level 1.
        2. A top-level PRODUCT (3PR...) can never be a child inside another assembly.
        3. A PART (1AF... weldment) may only contain other PART (1AF...) items.
        """
        if parent.part_type == "PRODUCT" and child.part_type != "PRODUCTION SUBASSEMBLY":
            raise ValueError(
                f"Hierarchy Rule Violation: Top-level PRODUCT '{parent.part_number}' can ONLY contain "
                f"PRODUCTION SUBASSEMBLY (2AS...) items one level down. "
                f"Cannot attach {child.part_type} '{child.part_number}' directly to a PRODUCT — "
                f"place '{child.part_number}' inside a PRODUCTION SUBASSEMBLY instead."
            )
        if child.part_type == "PRODUCT":
            raise ValueError(
                f"Hierarchy Rule Violation: Top-level PRODUCT '{child.part_number}' cannot be added as a child component."
            )
        if parent.part_type == "PART" and child.part_type != "PART":
            raise ValueError(
                f"Hierarchy Rule Violation: Part/Weldment '{parent.part_number}' can only contain PART (1AF...) items, "
                f"not {child.part_type} '{child.part_number}'."
            )

    @staticmethod
    def to_sql_wildcard(query_text: str) -> str:
        """
        Translates user wildcard patterns ('*' and '?') into SQL LIKE/ILIKE wildcards ('%' and '_').
        Example:
          '1AF*5'  -> '%1AF%5%' (matches '1AF00000005', '1AF00000015', etc.)
          'BRK?01' -> '%BRK_01%'
        """
        q = (query_text or "").strip()
        if not q:
            return "%"
        sql_pat = q.replace("%", r"\%").replace("_", r"\_")
        sql_pat = sql_pat.replace("*", "%").replace("?", "_")
        if not sql_pat.startswith("%"):
            sql_pat = "%" + sql_pat
        if not sql_pat.endswith("%"):
            sql_pat = sql_pat + "%"
        while "%%" in sql_pat:
            sql_pat = sql_pat.replace("%%", "%")
        return sql_pat

    def get_pending_updates_map(self) -> Dict[str, PartPendingUpdate]:
        """Batch-loads all PENDING_ECO updates in a single SQL query (eliminates N+1 loops)."""
        rows = self.session.scalars(
            select(PartPendingUpdate)
            .options(joinedload(PartPendingUpdate.new_noun_rel), joinedload(PartPendingUpdate.new_material_rel))
            .where(PartPendingUpdate.status == "PENDING_ECO")
        ).all()
        return {u.part_number: u for u in rows}

    @staticmethod
    def validate_revision_format(revision: str, is_prototype: bool) -> str:
        rev_clean = revision.strip().upper()
        if not rev_clean:
            raise ValueError("Revision cannot be empty.")
        if is_prototype and not rev_clean.isdigit():
            raise ValueError(f"Prototype items must use a NUMBERED revision (1, 2, 3...). Got '{rev_clean}'.")
        if not is_prototype and not rev_clean.isalpha():
            raise ValueError(f"Production items must use a LETTER revision (A, B, C...). Got '{rev_clean}'.")
        return rev_clean

    @staticmethod
    def validate_condition_code(condition_code: Optional[str]) -> str:
        c = (condition_code or "").strip().upper()
        if c and (len(c) != 3 or not c.isalnum()):
            raise ValueError(f"Condition code must be blank or 3 alphanumeric chars (e.g. '101', 'B01'). Got '{c}'.")
        return c

    @staticmethod
    def validate_envelope_str(envelope: Optional[str]) -> str:
        return (envelope or "").strip().upper().replace(" ", "")

    @staticmethod
    def resolve_part_uom(part_type: str, is_bulk: bool, requested_uom: Optional[str]) -> Tuple[bool, str]:
        clean_type = part_type.strip().upper()
        if clean_type in ("PRODUCTION SUBASSEMBLY", "PRODUCT") or not is_bulk:
            return False, "EA"
        uom_clean = (requested_uom or "EA").strip().upper()
        return True, (uom_clean if uom_clean else "EA")

    # --- Master Dictionaries ---
    def register_noun(self, name: str, short_definition: str) -> Noun:
        self._check_write_permission()
        clean_name = name.strip().upper()
        clean_def = (short_definition or "").strip()
        if not clean_name or not clean_def:
            raise ValueError("Both Noun name and Short Definition are required.")
        existing = self.session.scalar(select(Noun).where(Noun.name == clean_name))
        if existing:
            existing.short_definition = clean_def
            self.session.commit()
            return existing
        noun = Noun(name=clean_name, short_definition=clean_def)
        self.session.add(noun)
        self.session.commit()
        return noun

    def register_material(self, name: str, specification: Optional[str] = None) -> Material:
        self._check_write_permission()
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Material name cannot be empty.")
        existing = self.session.scalar(select(Material).where(Material.name == clean_name))
        if existing:
            return existing
        mat = Material(name=clean_name, specification=specification.strip() if specification else None)
        self.session.add(mat)
        self.session.commit()
        return mat

    def search_nouns(self, query_text: str = "", limit: int = 300) -> List[Noun]:
        stmt = select(Noun)
        q = (query_text or "").strip()
        if q and q != "*":
            pat = self.to_sql_wildcard(q)
            stmt = stmt.where(or_(Noun.name.ilike(pat), Noun.short_definition.ilike(pat)))
        return list(self.session.scalars(stmt.order_by(Noun.name).limit(limit)).all())

    def search_materials(self, query_text: str = "", limit: int = 300) -> List[Material]:
        stmt = select(Material)
        q = (query_text or "").strip()
        if q and q != "*":
            pat = self.to_sql_wildcard(q)
            stmt = stmt.where(or_(Material.name.ilike(pat), Material.specification.ilike(pat)))
        return list(self.session.scalars(stmt.order_by(Material.name).limit(limit)).all())

    def has_any_parts(self) -> bool:
        """O(1) existence check so `run.py` never loads the full Part table on startup."""
        return self.session.scalar(select(Part.part_number).limit(1)) is not None

    def get_fast_dropdown_metadata(self) -> Dict[str, List[str]]:
        """Fetches lightweight string lists for startup comboboxes in 3 tiny column queries."""
        noun_names = list(self.session.scalars(select(Noun.name).order_by(Noun.name)).all())
        mat_names = list(self.session.scalars(select(Material.name).order_by(Material.name)).all())
        eco_rows = self.session.execute(
            select(EngineeringChange.eco_number, EngineeringChange.eco_type, EngineeringChange.title, EngineeringChange.status)
            .order_by(EngineeringChange.eco_number.desc())
        ).all()
        all_eco_nos = [r[0] for r in eco_rows]
        open_labels = [f"{r[0]} | {r[1]} | {r[2]}" for r in eco_rows if r[3] in ("OPEN", "PENDING_APPROVAL")]
        return {
            "noun_prefixes": [f"{n}, " for n in noun_names],
            "mat_names": [""] + mat_names,
            "all_eco_nos": all_eco_nos,
            "open_labels": open_labels,
        }

    def get_eco_counts_bulk(self, eco_numbers: List[str]) -> Dict[str, Dict[str, int]]:
        """Batch-calculates New Parts, Modified Parts, BOM Rows, and Drawing Reg counts in 4 GROUP BY queries."""
        if not eco_numbers:
            return {}
        stats = {eno: {"new": 0, "mod": 0, "bom": 0, "reg_done": 0, "reg_total": 0} for eno in eco_numbers}

        for eno, cnt in self.session.execute(
            select(Part.eco_number, func.count(Part.part_number))
            .where(Part.eco_number.in_(eco_numbers))
            .group_by(Part.eco_number)
        ).all():
            stats[eno]["new"] = cnt

        for eno, cnt in self.session.execute(
            select(PartPendingUpdate.eco_number, func.count(PartPendingUpdate.id))
            .where(PartPendingUpdate.eco_number.in_(eco_numbers))
            .group_by(PartPendingUpdate.eco_number)
        ).all():
            stats[eno]["mod"] = cnt

        for eno, cnt in self.session.execute(
            select(BOMItem.eco_number, func.count(BOMItem.id))
            .where(BOMItem.eco_number.in_(eco_numbers))
            .group_by(BOMItem.eco_number)
        ).all():
            stats[eno]["bom"] = cnt

        for eno, is_reg, cnt in self.session.execute(
            select(
                ECODrawingRegistrationItem.eco_number,
                ECODrawingRegistrationItem.is_registered,
                func.count(ECODrawingRegistrationItem.id)
            )
            .where(ECODrawingRegistrationItem.eco_number.in_(eco_numbers))
            .group_by(ECODrawingRegistrationItem.eco_number, ECODrawingRegistrationItem.is_registered)
        ).all():
            stats[eno]["reg_total"] += cnt
            if is_reg:
                stats[eno]["reg_done"] += cnt

        return stats

    def search_drawing_registration_items(self, query_text: str = "", limit: int = 300) -> List[ECODrawingRegistrationItem]:
        """On-demand wildcard search for the Drawing Registration Checklist table."""
        stmt = (
            select(ECODrawingRegistrationItem)
            .options(joinedload(ECODrawingRegistrationItem.eco_rel), joinedload(ECODrawingRegistrationItem.part))
            .order_by(ECODrawingRegistrationItem.eco_number.desc(), ECODrawingRegistrationItem.drawing_number)
        )
        q = (query_text or "").strip()
        if q and q != "*":
            pat = self.to_sql_wildcard(q)
            stmt = stmt.where(
                or_(
                    ECODrawingRegistrationItem.eco_number.ilike(pat),
                    ECODrawingRegistrationItem.drawing_number.ilike(pat),
                    ECODrawingRegistrationItem.part_pn.ilike(pat),
                    ECODrawingRegistrationItem.drawing_type.ilike(pat),
                    ECODrawingRegistrationItem.notes.ilike(pat),
                )
            )
        return list(self.session.scalars(stmt.limit(limit)).all())

    def list_nouns(self) -> List[Noun]:
        return list(self.session.scalars(select(Noun).order_by(Noun.name)).all())

    def list_materials(self) -> List[Material]:
        return list(self.session.scalars(select(Material).order_by(Material.name)).all())

    def list_parts(self, part_types: Optional[List[str]] = None) -> List[Part]:
        stmt = select(Part).options(joinedload(Part.noun_rel), joinedload(Part.material_rel))
        if part_types:
            stmt = stmt.where(Part.part_type.in_(part_types))
        return list(self.session.scalars(stmt.order_by(Part.part_number)).all())

    def get_part(self, part_number: str) -> Optional[Part]:
        return self.session.get(Part, part_number.strip().upper()) if part_number else None

    def get_pending_update_for_part(self, part_number: str) -> Optional[PartPendingUpdate]:
        if not part_number:
            return None
        return self.session.scalar(
            select(PartPendingUpdate).where(
                PartPendingUpdate.part_number == part_number.strip().upper(),
                PartPendingUpdate.status == "PENDING_ECO"
            )
        )

    def search_parts(self, query_text: str = "", part_types: Optional[List[str]] = None, limit: int = 300) -> List[Part]:
        stmt = select(Part).join(Noun).options(joinedload(Part.noun_rel), joinedload(Part.material_rel))
        if part_types:
            stmt = stmt.where(Part.part_type.in_(part_types))
        q = (query_text or "").strip()
        if q and q != "*":
            pat = self.to_sql_wildcard(q)
            stmt = stmt.where(
                or_(
                    Part.part_number.ilike(pat),
                    Part.description.ilike(pat),
                    Noun.name.ilike(pat),
                    Part.condition_code.ilike(pat),
                )
            )
        return list(self.session.scalars(stmt.order_by(Part.part_number).limit(limit)).all())

    def list_drawings(self) -> List[Drawing]:
        return list(self.session.scalars(select(Drawing).order_by(Drawing.drawing_number)).all())

    def list_drawing_revisions(self, query_text: str = "") -> List[DrawingRevisionHistory]:
        stmt = select(DrawingRevisionHistory).order_by(DrawingRevisionHistory.drawing_number, DrawingRevisionHistory.id.desc())
        q = (query_text or "").strip()
        if q and q != "*":
            pat = self.to_sql_wildcard(q)
            stmt = stmt.where(
                or_(
                    DrawingRevisionHistory.drawing_number.ilike(pat),
                    DrawingRevisionHistory.linked_parts_summary.ilike(pat),
                    DrawingRevisionHistory.eco_number.ilike(pat)
                )
            )
        return list(self.session.scalars(stmt.limit(300)).all())

    def list_supporting_docs(self, drawing_number: Optional[str] = None) -> List[DrawingSupportingDoc]:
        stmt = select(DrawingSupportingDoc).order_by(DrawingSupportingDoc.id.desc())
        if drawing_number:
            stmt = stmt.where(DrawingSupportingDoc.drawing_number == drawing_number.strip().upper())
        return list(self.session.scalars(stmt).all())

    def search_ecos(self, query_text: str = "", limit: int = 300) -> List[EngineeringChange]:
        """Wildcard search across ECO Number, Title, Reason, Status, and Created By."""
        stmt = select(EngineeringChange)
        q = (query_text or "").strip()
        if q and q != "*":
            pat = self.to_sql_wildcard(q)
            stmt = stmt.where(
                or_(
                    EngineeringChange.eco_number.ilike(pat),
                    EngineeringChange.title.ilike(pat),
                    EngineeringChange.reason.ilike(pat),
                    EngineeringChange.status.ilike(pat),
                    EngineeringChange.created_by.ilike(pat),
                )
            )
        return list(self.session.scalars(stmt.order_by(EngineeringChange.eco_number.desc()).limit(limit)).all())

    def list_ecos(self, statuses: Optional[List[str]] = None) -> List[EngineeringChange]:
        stmt = select(EngineeringChange)
        if statuses:
            stmt = stmt.where(EngineeringChange.status.in_(statuses))
        return list(self.session.scalars(stmt.order_by(EngineeringChange.eco_number.desc())).all())

    def remove_eco_attachment(self, eco_number: str, file_name: str, file_path: str = "") -> str:
        """Removes an attached file from an ECO ONLY if the ECO status is OPEN."""
        eno = (eco_number or "").strip().upper()
        eco = self.session.scalar(select(EngineeringChange).where(EngineeringChange.eco_number == eno))
        if not eco:
            raise ValueError(f"ECO '{eno}' not found.")
        if eco.status != "OPEN":
            raise ValueError(
                f"Cannot remove file from ECO '{eno}' (Current Status: {eco.status}).\n\n"
                "Attached files can only be removed while the ECO is OPEN."
            )

        atts = self.list_eco_attachments(eno)
        target = None
        for a in atts:
            if (file_path and a.file_path == file_path) or a.file_name == file_name:
                target = a
                break
        if not target:
            raise ValueError(f"Attachment '{file_name}' not found on ECO '{eno}'.")

        removed_name = target.file_name
        self.session.delete(target)
        self.session.flush()
        return removed_name

    def list_eco_attachments(self, eco_number: Optional[str] = None) -> List[ECOAttachment]:
        stmt = select(ECOAttachment).order_by(ECOAttachment.id.desc())
        if eco_number:
            stmt = stmt.where(ECOAttachment.eco_number == eco_number.strip().upper())
        return list(self.session.scalars(stmt).all())

    def list_drawing_registration_items(self, eco_number: Optional[str] = None, only_unregistered: bool = False) -> List[ECODrawingRegistrationItem]:
        stmt = select(ECODrawingRegistrationItem).options(joinedload(ECODrawingRegistrationItem.eco_rel), joinedload(ECODrawingRegistrationItem.part)).order_by(ECODrawingRegistrationItem.eco_number, ECODrawingRegistrationItem.drawing_number, ECODrawingRegistrationItem.part_pn)
        if eco_number:
            stmt = stmt.where(ECODrawingRegistrationItem.eco_number == eco_number.strip().upper())
        if only_unregistered:
            stmt = stmt.where(ECODrawingRegistrationItem.is_registered.is_(False))
        return list(self.session.scalars(stmt).all())

    # =======================================================================
    # STEP 1: Role-Gated ECO Request (ECR) & Direct ECO Pull
    # =======================================================================
    def pull_eco_number(
        self,
        eco_type: str = "PRODUCTION",
        starting_code: Optional[str] = None,
        title: str = "New Engineering Change",
        reason: str = ""
    ) -> EngineeringChange:
        """
        Role-Gated ECO Creation:
        - VIEWER   : Blocked completely.
        - DESIGNER : Cannot pull an official ECO # directly; creates an ECO Request (`ECR-000001`)
                     with status='REQUESTED' awaiting Approver/Admin approval.
        - APPROVER / ADMIN : Pulls an official `ECO-...` / `PECO-...` number in 'OPEN' status.
        """
        self._check_write_permission(require_approver=False)
        role = self.settings.get("user_role", "ADMIN (Full Access)")
        clean_type = eco_type.strip().upper()
        if clean_type not in ECO_TYPES:
            raise ValueError("ECO type must be PRODUCTION or PROTOTYPE.")

        if role.startswith("DESIGNER"):
            # Designers submit an ECO Request (ECR-...) that must be approved first
            ecr_no = generate_next_eco_number(self.session, "ECR-000000")
            req_title = title.strip() if (title and title.strip() and title != "New Engineering Change") else f"ECO Request ({clean_type})"
            eco_req = EngineeringChange(
                eco_number=ecr_no,
                eco_type=clean_type,
                title=req_title,
                reason=reason.strip() or f"ECO Request submitted by {self.active_user} (Awaiting Approver/Admin to issue ECO #).",
                status="REQUESTED",
                created_by=self.active_user
            )
            self.session.add(eco_req)
            self.session.commit()
            return eco_req

        # APPROVER or ADMIN pulls official ECO number directly
        seed = starting_code.strip() if (starting_code and starting_code.strip()) else get_default_seed_for_eco(clean_type)
        final_eco = generate_next_eco_number(self.session, seed)
        eco = EngineeringChange(
            eco_number=final_eco,
            eco_type=clean_type,
            title=title.strip() or f"Engineering Change {final_eco}",
            reason=reason.strip(),
            status="OPEN",
            created_by=self.active_user
        )
        self.session.add(eco)
        self.session.commit()
        return eco

    def approve_eco_request(self, request_number: str, starting_code: Optional[str] = None) -> Tuple[str, EngineeringChange]:
        """
        Approver/Admin action: Approves a 'REQUESTED' ECR (`ECR-000001`), assigns the next
        official `ECO-...` or `PECO-...` sequence number, and transitions status to 'OPEN'.
        Returns (old_ecr_number, new_open_eco_obj).
        """
        self._check_write_permission(require_approver=True)
        req_no = request_number.strip().upper()
        req = self.session.get(EngineeringChange, req_no)
        if not req:
            raise ValueError(f"Record '{req_no}' not found.")
        if req.status != "REQUESTED":
            raise ValueError(f"'{req_no}' is already in '{req.status}' status (not a pending ECO Request).")

        seed = starting_code.strip() if (starting_code and starting_code.strip()) else get_default_seed_for_eco(req.eco_type)
        official_eco_no = generate_next_eco_number(self.session, seed)

        new_title = req.title
        if new_title.startswith("ECO Request"):
            new_title = f"Engineering Change {official_eco_no}"

        audit_note = f"[Request {req_no} by {req.created_by} Approved -> Issued {official_eco_no} by {self.active_user}]"
        new_reason = f"{req.reason}\n{audit_note}".strip() if req.reason else audit_note

        new_eco = EngineeringChange(
            eco_number=official_eco_no,
            eco_type=req.eco_type,
            title=new_title,
            reason=new_reason,
            status="OPEN",
            created_by=req.created_by,
            approved_by=self.active_user,
            created_at=req.created_at,
        )
        self.session.add(new_eco)
        self.session.flush()

        # Re-link any attachments that were uploaded to the ECR
        for att in list(req.attachments):
            att.eco_number = official_eco_no

        self.session.delete(req)
        self.session.commit()
        return req_no, new_eco

    def update_eco_info(self, eco_number: str, title: str, reason: str) -> EngineeringChange:
        self._check_write_permission()
        e_no = eco_number.strip().upper()
        eco = self.session.get(EngineeringChange, e_no)
        if not eco or eco.status == "RELEASED":
            raise ValueError(f"ECO '{e_no}' not found or already RELEASED.")
        if not title.strip() or not reason.strip():
            raise ValueError("Both ECO Title and Detailed Change Information are required.")
        eco.title = title.strip()
        eco.reason = reason.strip()
        self.session.commit()
        return eco

    def attach_file_to_eco(self, eco_number: str, file_path: str, description: Optional[str] = None) -> ECOAttachment:
        self._check_write_permission()
        e_no = eco_number.strip().upper()
        if not self.session.get(EngineeringChange, e_no):
            raise ValueError(f"ECO '{e_no}' not found.")
        clean_path = file_path.strip()
        if not clean_path:
            raise ValueError("File path is required.")
        stored_path, sha_hex = store_in_managed_vault(
            clean_path, self.settings.get("vault_root", ""), "eco_attachments",
            e_no, bool(self.settings.get("managed_vault_copy", True))
        )
        att = ECOAttachment(
            eco_number=e_no,
            file_name=os.path.basename(clean_path) or clean_path,
            file_path=stored_path,
            file_sha256=sha_hex,
            description=(description or "").strip()
        )
        self.session.add(att)
        self.session.commit()
        return att

    # =======================================================================
    # STEP 2: Add / Modify Parts (Including Source Type & Unit Weight) & BOM Markups
    # =======================================================================
    def _verify_editable_eco(self, eco_number: str) -> EngineeringChange:
        self._check_write_permission()
        if not eco_number or not eco_number.strip():
            raise ValueError("Pull or select an OPEN ECO number first.")
        eco = self.session.get(EngineeringChange, eco_number.strip().upper())
        if not eco or eco.status not in ("OPEN", "PENDING_APPROVAL"):
            raise ValueError(f"Changes can only be added to an OPEN ECO.")
        return eco

    def create_part(
        self, noun_desc: str, eco_number: str, part_type: str = "PART",
        material: Optional[str] = None, finish: str = "RAW", envelope: str = "",
        material_size: str = "", drawing_size: str = "D", condition_code: str = "",
        source_type: str = "MAKE", unit_weight: float = 0.0,
        is_bulk: bool = False, uom: str = "EA", is_prototype: bool = False,
        starting_code: Optional[str] = None, revision: Optional[str] = None
    ) -> Part:
        clean_type = part_type.strip().upper()
        eco = self._verify_editable_eco(eco_number)
        noun_obj, clean_desc = self.parse_and_validate_noun_desc(noun_desc)

        val_rev = self.validate_revision_format(revision or ("1" if is_prototype else "A"), is_prototype)
        val_cond = self.validate_condition_code(condition_code) if clean_type == "PRODUCTION SUBASSEMBLY" else ""
        final_bulk, final_uom = self.resolve_part_uom(clean_type, is_bulk, uom)
        clean_src = (source_type or "MAKE").strip().upper()
        if clean_src not in SOURCE_TYPES:
            clean_src = "MAKE"

        mat_obj = None
        if material and material.strip():
            mat_obj = self.session.scalar(select(Material).where(Material.name == material.strip()))
            if not mat_obj:
                raise ValueError(f"Material '{material}' does not exist in Material DB.")
        elif clean_type == "PART":
            raise ValueError("Parts of category 'PART' require a valid Material.")

        seed = starting_code.strip() if (starting_code and starting_code.strip()) else get_default_seed_for_type(clean_type)
        final_pn = generate_next_part_number(self.session, seed)

        part = Part(
            part_number=final_pn, noun_id=noun_obj.id, description=clean_desc,
            part_type=clean_type, material_id=mat_obj.id if mat_obj else None,
            finish=(finish or "RAW").strip().upper(), envelope=self.validate_envelope_str(envelope),
            material_size=(material_size or "").strip(), drawing_size=(drawing_size or "D").strip().upper(),
            condition_code=val_cond, source_type=clean_src, unit_weight=max(0.0, float(unit_weight or 0.0)),
            is_bulk=final_bulk, uom=final_uom, is_prototype=bool(is_prototype), revision=val_rev,
            eco_number=eco.eco_number, release_status="PENDING_ECO"
        )
        self.session.add(part)
        self.session.commit()
        return part

    def modify_existing_part(
        self, part_number: str, noun_desc: str, eco_number: str,
        material: Optional[str] = None, finish: str = "RAW", envelope: str = "",
        material_size: str = "", drawing_size: str = "D", condition_code: str = "",
        source_type: Optional[str] = None, unit_weight: Optional[float] = None,
        is_bulk: bool = False, uom: str = "EA", is_prototype: bool = False,
        new_revision: Optional[str] = None
    ) -> str:
        clean_pn = part_number.strip().upper()
        part = self.session.get(Part, clean_pn)
        if not part:
            raise ValueError(f"Number '{clean_pn}' does not exist.")
        eco = self._verify_editable_eco(eco_number)
        noun_obj, clean_desc = self.parse_and_validate_noun_desc(noun_desc)

        val_rev = self.validate_revision_format(new_revision or part.revision, is_prototype)
        val_cond = self.validate_condition_code(condition_code) if part.part_type == "PRODUCTION SUBASSEMBLY" else ""
        final_bulk, final_uom = self.resolve_part_uom(part.part_type, is_bulk, uom)
        c_src = (source_type or part.source_type or "MAKE").strip().upper()
        c_wt = max(0.0, float(unit_weight if unit_weight is not None else part.unit_weight))

        mat_obj = None
        if material and material.strip():
            mat_obj = self.session.scalar(select(Material).where(Material.name == material.strip()))
            if not mat_obj:
                raise ValueError(f"Material '{material}' does not exist.")
        elif part.part_type == "PART":
            raise ValueError("Category 'PART' requires a Material.")

        c_fin = (finish or "RAW").strip().upper()
        c_env = self.validate_envelope_str(envelope)
        c_msz = (material_size or "").strip()
        c_dsz = (drawing_size or "D").strip().upper()

        if part.release_status == "PENDING_ECO":
            part.noun_id = noun_obj.id
            part.description = clean_desc
            part.material_id = mat_obj.id if mat_obj else None
            part.finish, part.envelope, part.material_size, part.drawing_size = c_fin, c_env, c_msz, c_dsz
            part.condition_code, part.source_type, part.unit_weight = val_cond, c_src, c_wt
            part.is_bulk, part.uom, part.is_prototype, part.revision = final_bulk, final_uom, bool(is_prototype), val_rev
            part.eco_number = eco.eco_number
            self.session.commit()
            return f"Updated unreleased '{clean_pn}' under ECO '{eco.eco_number}'."

        upd = self.get_pending_update_for_part(clean_pn)
        if not upd:
            upd = PartPendingUpdate(part_number=clean_pn, eco_number=eco.eco_number, status="PENDING_ECO")
            self.session.add(upd)
        upd.eco_number = eco.eco_number
        upd.new_noun_id = noun_obj.id
        upd.new_description = clean_desc
        upd.new_material_id = mat_obj.id if mat_obj else None
        upd.new_finish, upd.new_envelope, upd.new_material_size, upd.new_drawing_size = c_fin, c_env, c_msz, c_dsz
        upd.new_condition_code, upd.new_source_type, upd.new_unit_weight = val_cond, c_src, c_wt
        upd.new_is_bulk, upd.new_uom, upd.new_is_prototype, upd.new_revision = final_bulk, final_uom, bool(is_prototype), val_rev
        self.session.commit()
        return f"Staged modification for '{clean_pn}' under ECO '{eco.eco_number}'."

    def get_bom_for_editor(self, parent_pn: str) -> Dict:
        p_pn = parent_pn.strip().upper()
        parent = self.session.get(Part, p_pn)
        if not parent:
            raise ValueError(f"Parent '{p_pn}' does not exist.")
        if parent.is_bulk:
            raise ValueError(f"Bulk item '{p_pn}' cannot have a child BOM.")
        pending = list(self.session.scalars(select(BOMItem).where(BOMItem.parent_pn == p_pn, BOMItem.status == "PENDING_ECO").order_by(BOMItem.find_number)).all())
        if pending:
            return {"mode": "PENDING_ECO", "eco_number": pending[0].eco_number, "items": pending}
        released = list(self.session.scalars(select(BOMItem).where(BOMItem.parent_pn == p_pn, BOMItem.status == "RELEASED").order_by(BOMItem.find_number)).all())
        return {"mode": "RELEASED", "eco_number": None, "items": released}

    def _load_bulk_adjacency_children(self) -> Dict[str, Set[str]]:
        """Loads the entire parent->child graph in a SINGLE SQL query for O(1) cycle detection."""
        adj: Dict[str, Set[str]] = defaultdict(set)
        rows = self.session.execute(
            select(BOMItem.parent_pn, BOMItem.child_pn).where(BOMItem.status.in_(["RELEASED", "PENDING_ECO"]))
        ).all()
        for p_pn, c_pn in rows:
            adj[p_pn].add(c_pn)
        return adj

    def _creates_cycle_fast(self, adj: Dict[str, Set[str]], candidate_parent: str, target_part: str) -> bool:
        visited = set()
        stack = [candidate_parent]
        while stack:
            curr = stack.pop()
            if curr == target_part:
                return True
            if curr not in visited:
                visited.add(curr)
                stack.extend(adj.get(curr, ()))
        return False

    def save_temporary_bom(self, parent_pn: str, eco_number: str, component_rows: List[Dict]) -> List[BOMItem]:
        p_pn = parent_pn.strip().upper()
        parent = self.session.get(Part, p_pn)
        if not parent or parent.is_bulk:
            raise ValueError(f"Invalid parent '{p_pn}'.")
        eco = self._verify_editable_eco(eco_number)

        adj = self._load_bulk_adjacency_children()
        for r in component_rows:
            c_pn = r["child_pn"].strip().upper()
            child_obj = self.session.get(Part, c_pn)
            if float(r["quantity"]) <= 0 or not child_obj:
                raise ValueError(f"Invalid child or quantity for '{c_pn}'.")
            self.validate_bom_parent_child_types(parent, child_obj)
            if self._creates_cycle_fast(adj, c_pn, p_pn):
                raise ValueError(f"Circular dependency blocked: '{p_pn}' exists inside '{c_pn}'.")

        for old in self.session.scalars(select(BOMItem).where(BOMItem.parent_pn == p_pn, BOMItem.status == "PENDING_ECO")).all():
            self.session.delete(old)
        self.session.flush()

        saved = []
        for idx, r in enumerate(component_rows, start=1):
            child = self.session.get(Part, r["child_pn"].strip().upper())
            sup = (r.get("supply_class") or "AVAILABLE").strip().upper()
            cond = self.validate_condition_code(r.get("condition_code") or child.condition_code)
            item = BOMItem(
                parent_pn=p_pn, child_pn=child.part_number,
                quantity=float(r["quantity"]),
                find_number=int(r["find_number"]) if r.get("find_number") not in (None, "", "-") else idx * 10,
                supply_class=sup if sup in SUPPLY_CLASSES else "AVAILABLE",
                condition_code=cond,
                eco_number=eco.eco_number, status="PENDING_ECO"
            )
            self.session.add(item)
            saved.append(item)
        self.session.commit()
        return saved

    # =======================================================================
    # STEP 3: Smart Auto-Generated Drawing Candidate List for ECO
    # =======================================================================
    def get_eco_drawing_candidates(self, eco_number: str) -> List[Dict]:
        e_no = eco_number.strip().upper()
        sm = self.get_eco_summary(e_no)
        existing_regs = {r.part_pn: r for r in sm["drawing_regs"]}
        has_saved_regs = len(existing_regs) > 0

        candidates: Dict[str, Dict] = {}

        for p in sm["new_parts"]:
            if p.drawing_size == "NONE":
                continue
            reg = existing_regs.get(p.part_number)
            candidates[p.part_number] = {
                "part_pn": p.part_number, "name": p.standard_name,
                "role": "NEW PART CREATED", "target_rev": p.revision, "sheet_size": p.drawing_size,
                "drawing_number": reg.drawing_number if reg else p.part_number,
                "drawing_type": reg.drawing_type if reg else "SINGLE",
                "checked": (p.part_number in existing_regs) if has_saved_regs else True,
                "is_registered": reg.is_registered if reg else False,
            }

        for u in sm["mod_parts"]:
            if u.new_drawing_size == "NONE":
                continue
            reg = existing_regs.get(u.part_number)
            candidates[u.part_number] = {
                "part_pn": u.part_number, "name": f"{u.new_noun_rel.name}, {u.new_description}",
                "role": f"PART MODIFIED (-> Rev {u.new_revision})", "target_rev": u.new_revision,
                "sheet_size": u.new_drawing_size,
                "drawing_number": reg.drawing_number if reg else u.part_number,
                "drawing_type": reg.drawing_type if reg else "SINGLE",
                "checked": (u.part_number in existing_regs) if has_saved_regs else True,
                "is_registered": reg.is_registered if reg else False,
            }

        parent_pns = sorted({b.parent_pn for b in sm["bom_items"]})
        for ppn in parent_pns:
            if ppn in candidates:
                candidates[ppn]["role"] += " + BOM CHANGED"
                continue
            p = self.session.get(Part, ppn)
            if not p or p.drawing_size == "NONE":
                continue
            upd = self.get_pending_update_for_part(ppn)
            reg = existing_regs.get(ppn)
            candidates[ppn] = {
                "part_pn": ppn, "name": p.standard_name, "role": "PARENT BOM CHANGED",
                "target_rev": upd.new_revision if upd else p.revision,
                "sheet_size": upd.new_drawing_size if upd else p.drawing_size,
                "drawing_number": reg.drawing_number if reg else ppn,
                "drawing_type": reg.drawing_type if reg else "SINGLE",
                "checked": (ppn in existing_regs) if has_saved_regs else True,
                "is_registered": reg.is_registered if reg else False,
            }

        child_pns = sorted({b.child_pn for b in sm["bom_items"]})
        for cpn in child_pns:
            if cpn in candidates:
                continue
            p = self.session.get(Part, cpn)
            if not p or p.drawing_size == "NONE":
                continue
            reg = existing_regs.get(cpn)
            candidates[cpn] = {
                "part_pn": cpn, "name": p.standard_name, "role": "UNCHANGED CHILD ON BOM",
                "target_rev": p.revision, "sheet_size": p.drawing_size,
                "drawing_number": reg.drawing_number if reg else cpn,
                "drawing_type": reg.drawing_type if reg else "SINGLE",
                "checked": (cpn in existing_regs) if has_saved_regs else False,
                "is_registered": reg.is_registered if reg else False,
            }

        for p_pn, reg in existing_regs.items():
            if p_pn not in candidates:
                p = reg.part
                candidates[p_pn] = {
                    "part_pn": p_pn, "name": p.standard_name if p else "-", "role": "ADDED TO LIST",
                    "target_rev": reg.target_rev, "sheet_size": reg.sheet_size,
                    "drawing_number": reg.drawing_number, "drawing_type": reg.drawing_type,
                    "checked": True, "is_registered": reg.is_registered,
                }

        return list(candidates.values())

    def sync_eco_drawing_registration_list(self, eco_number: str, selected_rows: List[Dict]) -> int:
        self._check_write_permission()
        e_no = eco_number.strip().upper()
        eco = self.session.get(EngineeringChange, e_no)
        if not eco or eco.status == "RELEASED":
            raise ValueError("Cannot modify Drawing Registration List of a RELEASED ECO.")

        existing_map = {
            r.part_pn: r for r in self.session.scalars(
                select(ECODrawingRegistrationItem).where(ECODrawingRegistrationItem.eco_number == e_no)
            ).all()
        }
        keep_pns = set()

        for row in selected_rows:
            p_pn = row["part_pn"].strip().upper()
            keep_pns.add(p_pn)
            dwg_no = (row.get("drawing_number") or p_pn).strip().upper()
            dtype = (row.get("drawing_type") or "SINGLE").strip().upper()
            part = self.session.get(Part, p_pn)
            upd = self.get_pending_update_for_part(p_pn)
            t_rev = upd.new_revision if upd else (part.revision if part else "A")
            t_sz = upd.new_drawing_size if upd else (part.drawing_size if part else "D")

            if p_pn in existing_map:
                rec = existing_map[p_pn]
                rec.drawing_number = dwg_no
                rec.drawing_type = dtype
                rec.target_rev = t_rev
                rec.sheet_size = t_sz
            else:
                self.session.add(ECODrawingRegistrationItem(
                    eco_number=e_no, part_pn=p_pn, drawing_number=dwg_no,
                    drawing_type=dtype, config_label="STD",
                    target_rev=t_rev, sheet_size=t_sz,
                    notes=row.get("role", "ECO Drawing Update"),
                    is_registered=False
                ))

        for p_pn, old_rec in existing_map.items():
            if p_pn not in keep_pns and not old_rec.is_registered:
                self.session.delete(old_rec)

        self.session.commit()
        return len(keep_pns)

    def add_to_drawing_registration_list(
        self, eco_number: str, part_pn: str,
        drawing_number: Optional[str] = None,
        drawing_type: str = "SINGLE",
        config_label: str = "STD",
        notes: str = ""
    ) -> ECODrawingRegistrationItem:
        self._check_write_permission()
        e_no = eco_number.strip().upper()
        p_pn = part_pn.strip().upper()
        eco = self.session.get(EngineeringChange, e_no)
        part = self.session.get(Part, p_pn)
        if not eco or not part or eco.status == "RELEASED":
            raise ValueError("Valid open ECO and Part Number are required.")

        upd = self.get_pending_update_for_part(p_pn)
        target_rev = upd.new_revision if upd else part.revision
        sheet_sz = upd.new_drawing_size if upd else part.drawing_size
        dwg_no = (drawing_number or "").strip().upper() or p_pn
        dtype = (drawing_type or "SINGLE").strip().upper()

        existing = self.session.scalar(
            select(ECODrawingRegistrationItem).where(
                ECODrawingRegistrationItem.eco_number == e_no,
                ECODrawingRegistrationItem.part_pn == p_pn
            )
        )
        if existing:
            existing.drawing_number, existing.drawing_type, existing.target_rev, existing.sheet_size = dwg_no, dtype, target_rev, sheet_sz
            if notes:
                existing.notes = notes.strip()
            self.session.commit()
            return existing

        reg_item = ECODrawingRegistrationItem(
            eco_number=e_no, part_pn=p_pn, drawing_number=dwg_no,
            drawing_type=dtype, config_label="STD",
            target_rev=target_rev, sheet_size=sheet_sz,
            notes=notes.strip() or f"{dtype} Drawing Registration",
            is_registered=False
        )
        self.session.add(reg_item)
        self.session.commit()
        return reg_item

    # =======================================================================
    # STEP 4: Generate Tabular Color-Coded ECO Summary Report
    # =======================================================================
    def generate_eco_summary_report(self, eco_number: str) -> str:
        """
        Generates a clean, tabular ECO Summary Report where fields sit in column
        headers and data rows are color-coded by prefix:
        - `| + |` -> GREEN row (Added parts & BOM additions)
        - `| - |` -> RED row   (Removed BOM items & Pending drawing registrations)
        - `| ~ |` -> BLUE row  (Modified part BEFORE/AFTER rows & Changed BOM rows)
        - `| = |` -> Default   (Unchanged BOM context rows)
        """
        e_no = eco_number.strip().upper()
        eco = self.session.get(EngineeringChange, e_no)
        if not eco:
            raise ValueError(f"ECO '{e_no}' not found.")

        sm = self.get_eco_summary(e_no)
        mod_by_pn = {u.part_number: u for u in sm["mod_parts"]}

        def _fit(val, width: int) -> str:
            s = str(val if val is not None else "-")
            return (s[:width - 2] + "..") if len(s) > width else s.ljust(width)

        lines = [
            "=" * 146,
            f"hBOM (v1.0) — ENGINEERING CHANGE ORDER (ECO) SUMMARY REPORT: {eco.eco_number}",
            "=" * 146,
            f"ECO Number : {eco.eco_number:<14} | Category : {eco.eco_type:<12} | Status      : {eco.status}",
            f"Created By : {eco.created_by:<14} | Approved : {(eco.approved_by or 'Pending'):<12} | Released By : {eco.released_by or 'Pending'}",
            f"ECO Title  : {eco.title}",
            "-" * 146,
            "1. ECO CHANGE INFORMATION & ENGINEERING REASON:",
            eco.reason or "(No detailed description entered yet.)",
            "-" * 146,
        ]

        # -------------------------------------------------------------------
        # TABLE 2: NEW PARTS / SUBASSEMBLIES / PRODUCTS ADDED
        # -------------------------------------------------------------------
        lines.append(f"2. NEW PARTS / SUBASSEMBLIES / PRODUCTS ADDED ({len(sm['new_parts'])}):")
        if not sm["new_parts"]:
            lines.append("   (None)")
        else:
            p_hdr = (
                f"| Act | {'Part Number':<12} | {'Cat':<7} | {'Rev':<3} | {'Noun, Description':<32} | "
                f"{'Material':<20} | {'Mat Size':<14} | {'Fin':<7} | {'Envelope':<11} | {'Dwg':<3} | {'UOM':<3} | {'Cond':<4} |"
            )
            p_sep = "+" + "-" * (len(p_hdr) - 2) + "+"
            lines.append(p_sep)
            lines.append(p_hdr)
            lines.append(p_sep)
            for p in sm["new_parts"]:
                cat_short = "PART" if p.part_type == "PART" else ("SUBASM" if "SUB" in p.part_type else "PRODUCT")
                mat_name = p.material_rel.name if p.material_rel else "-"
                lines.append(
                    f"| +   | {_fit(p.part_number, 12)} | {_fit(cat_short, 7)} | {_fit(p.revision, 3)} | "
                    f"{_fit(p.standard_name, 32)} | {_fit(mat_name, 20)} | {_fit(p.material_size or '-', 14)} | "
                    f"{_fit(p.finish, 7)} | {_fit(p.envelope or '-', 11)} | {_fit(p.drawing_size, 3)} | "
                    f"{_fit(p.uom, 3)} | {_fit(p.condition_code or '-', 4)} |"
                )
            lines.append(p_sep)

        # -------------------------------------------------------------------
        # TABLE 3: EXISTING PARTS MODIFIED (PAIRED BEFORE / AFTER ROWS)
        # -------------------------------------------------------------------
        lines.append("-" * 146)
        lines.append(f"3. EXISTING PARTS MODIFIED — BEFORE vs. AFTER COMPARISON TABLE ({len(sm['mod_parts'])}):")
        if not sm["mod_parts"]:
            lines.append("   (None)")
        else:
            m_hdr = (
                f"| Act | {'Part Number':<12} | {'State':<6} | {'Rev':<3} | {'Noun, Description':<32} | "
                f"{'Material':<20} | {'Mat Size':<14} | {'Fin':<7} | {'Envelope':<11} | {'Dwg':<3} | {'UOM':<3} | {'Cond':<4} |"
            )
            m_sep = "+" + "-" * (len(m_hdr) - 2) + "+"
            lines.append(m_sep)
            lines.append(m_hdr)
            lines.append(m_sep)
            for u in sm["mod_parts"]:
                orig = u.part
                old_mat = orig.material_rel.name if orig.material_rel else "-"
                new_mat = u.new_material_rel.name if u.new_material_rel else "-"
                new_name = f"{u.new_noun_rel.name}, {u.new_description}"

                # BEFORE Row
                lines.append(
                    f"| ~   | {_fit(u.part_number, 12)} | {'BEFORE':<6} | {_fit(orig.revision, 3)} | "
                    f"{_fit(orig.standard_name, 32)} | {_fit(old_mat, 20)} | {_fit(orig.material_size or '-', 14)} | "
                    f"{_fit(orig.finish, 7)} | {_fit(orig.envelope or '-', 11)} | {_fit(orig.drawing_size, 3)} | "
                    f"{_fit(orig.uom, 3)} | {_fit(orig.condition_code or '-', 4)} |"
                )
                # AFTER Row
                lines.append(
                    f"| ~   | {_fit(u.part_number, 12)} | {'AFTER':<6} | {_fit(u.new_revision, 3)} | "
                    f"{_fit(new_name, 32)} | {_fit(new_mat, 20)} | {_fit(u.new_material_size or '-', 14)} | "
                    f"{_fit(u.new_finish, 7)} | {_fit(u.new_envelope or '-', 11)} | {_fit(u.new_drawing_size, 3)} | "
                    f"{_fit(u.new_uom, 3)} | {_fit(u.new_condition_code or '-', 4)} |"
                )
                direct_parents = self.where_used(u.part_number, single_level_only=True)
                if direct_parents:
                    p_list = ", ".join(f"{dp['parent_pn']} (Qty {dp['qty_per']:g})" for dp in direct_parents)
                    lines.append(f"^-- WHERE-USED IMPACT for {u.part_number}: Used in Parent Assembly [{p_list}]")
                lines.append(m_sep)

        # -------------------------------------------------------------------
        # TABLE 4: BOM MARKUPS TABLE (UNIFIED TABLE PER PARENT ASSEMBLY)
        # -------------------------------------------------------------------
        lines.append("-" * 146)
        lines.append("4. BOM MARKUPS TABLE (+ GREEN = Added, - RED = Removed, ~ BLUE = Changed, = Unchanged):")
        staged_parents = sorted({b.parent_pn for b in sm["bom_items"]})
        if not staged_parents:
            lines.append("   (No assembly BOM structures modified on this ECO)")

        b_hdr = (
            f"| Act | {'Status':<7} | {'Find':<4} | {'Child PN':<12} | {'Noun, Description':<34} | "
            f"{'Old Qty':<7} | {'New Qty':<7} | {'Delta':<7} | {'UOM':<3} | {'Cond (Old->New)':<15} | {'Supply (Old->New)':<23} |"
        )
        b_sep = "+" + "-" * (len(b_hdr) - 2) + "+"

        for parent_pn in staged_parents:
            parent_part = self.session.get(Part, parent_pn)
            lines.append("")
            lines.append(f"PARENT ASSEMBLY: {parent_pn} — {parent_part.standard_name} [{parent_part.part_type}, Rev {parent_part.revision}]")
            lines.append(b_sep)
            lines.append(b_hdr)
            lines.append(b_sep)

            if eco.status == "RELEASED":
                old_list = list(self.session.scalars(
                    select(BOMItem).where(BOMItem.parent_pn == parent_pn, BOMItem.superseded_by_eco == e_no).order_by(BOMItem.find_number)
                ).all())
            else:
                old_list = list(self.session.scalars(
                    select(BOMItem).where(BOMItem.parent_pn == parent_pn, BOMItem.status == "RELEASED").order_by(BOMItem.find_number)
                ).all())

            old_rows = {b.child_pn: b for b in old_list}
            new_list = sorted(
                [b for b in sm["bom_items"] if b.parent_pn == parent_pn],
                key=lambda x: (x.find_number or 9999, x.child_pn)
            )
            new_rows = {b.child_pn: b for b in new_list}

            # 1) Active / Added / Changed Rows in Find # order
            for nb in new_list:
                c_pn = nb.child_pn
                ch = nb.child
                new_cond = nb.condition_code or ch.condition_code or "-"

                if c_pn not in old_rows:
                    # ADDED ROW (GREEN)
                    lines.append(
                        f"| +   | {'ADDED':<7} | {_fit(nb.find_number or '-', 4)} | {_fit(c_pn, 12)} | "
                        f"{_fit(ch.standard_name, 34)} | {'-':<7} | {_fit(f'{nb.quantity:g}', 7)} | "
                        f"{_fit(f'+{nb.quantity:g}', 7)} | {_fit(ch.uom, 3)} | {_fit(new_cond, 15)} | {_fit(nb.supply_class, 23)} |"
                    )
                else:
                    ob = old_rows[c_pn]
                    old_cond = ob.condition_code or ch.condition_code or "-"
                    qty_changed = (float(ob.quantity) != float(nb.quantity))
                    find_changed = ((ob.find_number or 0) != (nb.find_number or 0))
                    cond_changed = (old_cond != new_cond)
                    sup_changed = (ob.supply_class != nb.supply_class)
                    part_modified = (c_pn in mod_by_pn)

                    find_disp = f"{ob.find_number}->{nb.find_number}" if find_changed else str(nb.find_number or "-")
                    cond_disp = f"{old_cond} -> {new_cond}" if cond_changed else new_cond
                    sup_disp = f"{ob.supply_class}->{nb.supply_class}" if sup_changed else nb.supply_class
                    delta_val = nb.quantity - ob.quantity
                    delta_disp = f"{delta_val:+g}" if qty_changed else ("MOD PT" if part_modified else "0")

                    if qty_changed or find_changed or cond_changed or sup_changed or part_modified:
                        # CHANGED ROW (BLUE)
                        lines.append(
                            f"| ~   | {'CHANGED':<7} | {_fit(find_disp, 4)} | {_fit(c_pn, 12)} | "
                            f"{_fit(ch.standard_name, 34)} | {_fit(f'{ob.quantity:g}', 7)} | {_fit(f'{nb.quantity:g}', 7)} | "
                            f"{_fit(delta_disp, 7)} | {_fit(ch.uom, 3)} | {_fit(cond_disp, 15)} | {_fit(sup_disp, 23)} |"
                        )
                    else:
                        # UNCHANGED CONTEXT ROW
                        lines.append(
                            f"| =   | {'SAME':<7} | {_fit(find_disp, 4)} | {_fit(c_pn, 12)} | "
                            f"{_fit(ch.standard_name, 34)} | {_fit(f'{ob.quantity:g}', 7)} | {_fit(f'{nb.quantity:g}', 7)} | "
                            f"{'0':<7} | {_fit(ch.uom, 3)} | {_fit(cond_disp, 15)} | {_fit(sup_disp, 23)} |"
                        )

            # 2) Removed Rows (RED)
            for ob in old_list:
                if ob.child_pn not in new_rows:
                    ch = ob.child
                    old_cond = ob.condition_code or ch.condition_code or "-"
                    lines.append(
                        f"| -   | {'REMOVED':<7} | {_fit(ob.find_number or '-', 4)} | {_fit(ob.child_pn, 12)} | "
                        f"{_fit(ch.standard_name, 34)} | {_fit(f'{ob.quantity:g}', 7)} | {'-':<7} | "
                        f"{_fit(f'-{ob.quantity:g}', 7)} | {_fit(ch.uom, 3)} | {_fit(old_cond, 15)} | {_fit(ob.supply_class, 23)} |"
                    )

            lines.append(b_sep)

        # -------------------------------------------------------------------
        # TABLE 5: DRAWING REGISTRATION CHECKLIST TABLE
        # -------------------------------------------------------------------
        lines.append("-" * 146)
        lines.append(f"5. DRAWING REGISTRATION CHECKLIST TABLE ({len(sm['drawing_regs'])}):")
        if not sm["drawing_regs"]:
            lines.append("   (No drawings listed on registration checklist)")
        else:
            d_hdr = f"| St  | {'Registration Status':<20} | {'Drawing Number':<22} | {'Drawing Mode':<12} | {'Part Number':<12} | {'Rev':<4} | {'Size':<4} | {'Notes':<45} |"
            d_sep = "+" + "-" * (len(d_hdr) - 2) + "+"
            lines.append(d_sep)
            lines.append(d_hdr)
            lines.append(d_sep)
            for reg in sm["drawing_regs"]:
                act = "+" if reg.is_registered else "-"
                st = "REGISTERED" if reg.is_registered else "PENDING REGISTRATION"
                lines.append(
                    f"| {act:<3} | {_fit(st, 20)} | {_fit(reg.drawing_number, 22)} | {_fit(reg.drawing_type, 12)} | "
                    f"{_fit(reg.part_pn, 12)} | {_fit(reg.target_rev, 4)} | {_fit(reg.sheet_size, 4)} | {_fit(reg.notes, 45)} |"
                )
            lines.append(d_sep)

        lines.append("=" * 146)
        return chr(10).join(lines)

    # =======================================================================
    # STEP 5 & 6: Submit -> Approve -> Register Drawings (Vault SHA-256) -> Release (Preserve SUPERSEDED)
    # =======================================================================
    def submit_eco_for_approval(self, eco_number: str) -> EngineeringChange:
        self._check_write_permission()
        e_no = eco_number.strip().upper()
        eco = self.session.get(EngineeringChange, e_no)
        if not eco or eco.status != "OPEN":
            raise ValueError(f"ECO '{e_no}' must be in OPEN status to submit.")
        if not eco.title.strip() or not eco.reason.strip():
            raise ValueError("Enter ECO Title and Detailed Change Information before submitting.")
        eco.status = "PENDING_APPROVAL"
        eco.submitted_at = datetime.datetime.utcnow()
        self.session.commit()
        return eco

    def approve_eco(self, eco_number: str) -> EngineeringChange:
        self._check_write_permission(require_approver=True)
        e_no = eco_number.strip().upper()
        eco = self.session.get(EngineeringChange, e_no)
        if not eco or eco.status not in ("PENDING_APPROVAL", "OPEN"):
            raise ValueError(f"ECO '{e_no}' cannot be approved from current status.")
        eco.status = "APPROVED"
        eco.approved_by = self.active_user
        eco.approved_at = datetime.datetime.utcnow()
        self.session.commit()
        return eco

    def register_drawing(
        self,
        drawing_number: str,
        file_path: str,
        part_links: List[Dict],
        drawing_type: str = "SINGLE",
        eco_number: Optional[str] = None,
        sheet_size: Optional[str] = None,
        sheet_count: int = 1
    ) -> Drawing:
        self._check_write_permission()
        dwg_no = drawing_number.strip().upper()
        dtype = (drawing_type or "SINGLE").strip().upper()
        if not dwg_no or not part_links or not file_path.strip():
            raise ValueError("Drawing Number, File Path, and at least one linked Part Number are required.")
        if dtype == "LH/RH PAIR" and len(part_links) < 2:
            raise ValueError("An LH/RH PAIR drawing requires at least 2 linked part numbers (LH and RH).")

        resolved_parts: List[Tuple[Part, str, str]] = []
        for lk in part_links:
            p_pn = lk["part_pn"].strip().upper()
            part = self.session.get(Part, p_pn)
            if not part:
                raise ValueError(f"Part '{p_pn}' does not exist.")
            upd = self.get_pending_update_for_part(p_pn)
            t_rev = upd.new_revision if upd else part.revision
            t_sz = upd.new_drawing_size if upd else part.drawing_size
            resolved_parts.append((part, t_rev, t_sz))

        revs = {r[1] for r in resolved_parts}
        if len(revs) > 1:
            raise ValueError(f"All parts linked to drawing '{dwg_no}' must share the same revision. Found: {revs}")

        primary_part, target_rev, primary_sz = resolved_parts[0]
        sz = (sheet_size or primary_sz or "D").strip().upper()
        cnt = max(1, int(sheet_count))
        e_no = eco_number.strip().upper() if (eco_number and eco_number.strip()) else primary_part.eco_number

        stored_path, sha_hex = store_in_managed_vault(
            file_path, self.settings.get("vault_root", ""), "drawings",
            f"{dwg_no}_Rev{target_rev}", bool(self.settings.get("managed_vault_copy", True))
        )

        existing = self.session.get(Drawing, dwg_no)
        if existing:
            existing.drawing_type, existing.part_pn, existing.revision = dtype, primary_part.part_number, target_rev
            existing.eco_number, existing.file_path, existing.file_sha256 = e_no, stored_path, sha_hex
            existing.sheet_size, existing.sheet_count = sz, cnt
        else:
            existing = Drawing(
                drawing_number=dwg_no, drawing_type=dtype, part_pn=primary_part.part_number,
                revision=target_rev, eco_number=e_no, file_path=stored_path, file_sha256=sha_hex,
                sheet_size=sz, sheet_count=cnt
            )
            self.session.add(existing)
            self.session.flush()

        for old_lk in self.session.scalars(select(DrawingPartLink).where(DrawingPartLink.drawing_number == dwg_no)).all():
            self.session.delete(old_lk)
        self.session.flush()

        summary_tokens = []
        linked_pn_set = set()
        for part_obj, _, _ in resolved_parts:
            self.session.add(DrawingPartLink(drawing_number=dwg_no, part_pn=part_obj.part_number, config_label="LINKED"))
            summary_tokens.append(part_obj.part_number)
            linked_pn_set.add(part_obj.part_number)

        for old_hist in self.session.scalars(select(DrawingRevisionHistory).where(DrawingRevisionHistory.drawing_number == dwg_no)).all():
            old_hist.is_current = False

        self.session.add(DrawingRevisionHistory(
            drawing_number=dwg_no, drawing_type=dtype,
            linked_parts_summary=", ".join(summary_tokens),
            revision=target_rev, eco_number=e_no, file_path=stored_path, file_sha256=sha_hex,
            registered_by=self.active_user, sheet_size=sz, sheet_count=cnt, is_current=True
        ))

        reg_items = self.session.scalars(
            select(ECODrawingRegistrationItem).where(
                or_(
                    ECODrawingRegistrationItem.drawing_number == dwg_no,
                    ECODrawingRegistrationItem.part_pn.in_(linked_pn_set)
                ),
                ECODrawingRegistrationItem.is_registered.is_(False)
            )
        ).all()
        for reg in reg_items:
            reg.drawing_number, reg.drawing_type, reg.is_registered = dwg_no, dtype, True
            reg.registered_at = datetime.datetime.utcnow()

        self.session.commit()
        return existing

    def attach_supporting_doc_to_drawing(self, drawing_number: str, doc_type: str, file_path: str, description: Optional[str] = None) -> DrawingSupportingDoc:
        self._check_write_permission()
        dwg_no = drawing_number.strip().upper()
        if not self.session.get(Drawing, dwg_no):
            raise ValueError(f"Drawing '{dwg_no}' does not exist.")
        clean_path = file_path.strip()
        stored_path, _ = store_in_managed_vault(
            clean_path, self.settings.get("vault_root", ""), "supporting_docs",
            dwg_no, bool(self.settings.get("managed_vault_copy", True))
        )
        doc = DrawingSupportingDoc(
            drawing_number=dwg_no, doc_type=(doc_type or "SUPPLIER DRAWING").strip().upper(),
            file_name=os.path.basename(clean_path) or clean_path, file_path=stored_path,
            description=(description or "").strip()
        )
        self.session.add(doc)
        self.session.commit()
        return doc


    def reject_eco(self, eco_number: str, rejection_reason: str) -> EngineeringChange:
        """Transitions an ECO back to OPEN status from PENDING_APPROVAL or APPROVED for corrections."""
        eno = (eco_number or "").strip().upper()
        reason = (rejection_reason or "").strip()
        if not reason:
            raise ValueError("A rejection reason / correction note is required to reject an ECO.")

        eco = self.session.scalar(select(EngineeringChange).where(EngineeringChange.eco_number == eno))
        if not eco:
            raise ValueError(f"ECO '{eno}' not found.")
        if eco.status not in ("PENDING_APPROVAL", "APPROVED"):
            raise ValueError(
                f"Cannot reject ECO '{eno}' (Current Status: {eco.status}).\n\n"
                "Only ECOs in PENDING_APPROVAL or APPROVED status can be rejected back to OPEN."
            )

        old_status = eco.status
        eco.status = "OPEN"
        timestamp_note = f"\n[REJECTED from {old_status}]: {reason}"
        eco.reason = (eco.reason or "") + timestamp_note
        self.session.commit()
        return eco

    def release_eco(self, eco_number: str) -> EngineeringChange:
        self._check_write_permission(require_approver=True)
        eco_no = eco_number.strip().upper()
        eco = self.session.get(EngineeringChange, eco_no)
        if not eco or eco.status == "RELEASED":
            raise ValueError(f"ECO '{eco_no}' not found or already RELEASED.")
        if eco.status != "APPROVED":
            raise ValueError(f"ECO '{eco_no}' is '{eco.status}'. Submit & Approve the ECO first.")

        unregistered = self.session.scalars(
            select(ECODrawingRegistrationItem).where(
                ECODrawingRegistrationItem.eco_number == eco_no,
                ECODrawingRegistrationItem.is_registered.is_(False)
            )
        ).all()
        if unregistered:
            missing_str = ", ".join(f"{u.drawing_number} ({u.part_pn})" for u in unregistered)
            raise ValueError(f"Cannot release ECO '{eco_no}' until all checklist drawings are registered on Tab 8! Pending: {missing_str}")

        for p in self.session.scalars(select(Part).where(Part.eco_number == eco_no, Part.release_status == "PENDING_ECO")).all():
            p.release_status = "RELEASED"

        staged_updates = self.session.scalars(
            select(PartPendingUpdate).where(PartPendingUpdate.eco_number == eco_no, PartPendingUpdate.status == "PENDING_ECO")
        ).all()
        for upd in staged_updates:
            tp = upd.part
            tp.noun_id, tp.description, tp.material_id = upd.new_noun_id, upd.new_description, upd.new_material_id
            tp.finish, tp.envelope, tp.material_size, tp.drawing_size = upd.new_finish, upd.new_envelope, upd.new_material_size, upd.new_drawing_size
            tp.condition_code, tp.source_type, tp.unit_weight = upd.new_condition_code, upd.new_source_type, upd.new_unit_weight
            tp.is_bulk, tp.uom, tp.is_prototype, tp.revision = upd.new_is_bulk, upd.new_uom, upd.new_is_prototype, upd.new_revision
            tp.eco_number, tp.release_status = eco_no, "RELEASED"
            upd.status = "APPLIED"

        # Preserve historical BOM rows by flipping status -> SUPERSEDED instead of deleting!
        staged_bom = self.session.scalars(
            select(BOMItem).where(BOMItem.eco_number == eco_no, BOMItem.status == "PENDING_ECO")
        ).all()
        for parent_pn in {item.parent_pn for item in staged_bom}:
            for old_item in self.session.scalars(select(BOMItem).where(BOMItem.parent_pn == parent_pn, BOMItem.status == "RELEASED")).all():
                old_item.status = "SUPERSEDED"
                old_item.superseded_by_eco = eco_no
        for item in staged_bom:
            item.status = "RELEASED"

        eco.status = "RELEASED"
        eco.released_by = self.active_user
        eco.released_at = datetime.datetime.utcnow()
        self.session.commit()
        return eco

    def get_eco_summary(self, eco_number: str) -> Dict:
        eco_no = eco_number.strip().upper()
        return {
            "new_parts": list(self.session.scalars(select(Part).where(Part.eco_number == eco_no)).all()),
            "mod_parts": list(self.session.scalars(select(PartPendingUpdate).where(PartPendingUpdate.eco_number == eco_no)).all()),
            "bom_items": list(self.session.scalars(select(BOMItem).where(BOMItem.eco_number == eco_no)).all()),
            "attachments": list(self.session.scalars(select(ECOAttachment).where(ECOAttachment.eco_number == eco_no)).all()),
            "drawing_regs": list(self.session.scalars(select(ECODrawingRegistrationItem).where(ECODrawingRegistrationItem.eco_number == eco_no)).all()),
        }

    # =======================================================================
    # HIGH-SPEED BULK GRAPH BOM LOOKUP, WHERE-USED & COMPARISON (O(1) SQL Queries)
    # =======================================================================
    def _load_full_bom_graph(self, include_pending: bool = False):
        """Fetches all Parts and active BOMItems in 2 bulk queries to eliminate N+1 latency."""
        parts_map = {
            p.part_number: p for p in self.session.scalars(
                select(Part).options(joinedload(Part.noun_rel), joinedload(Part.material_rel))
            ).all()
        }
        statuses = ["RELEASED", "PENDING_ECO"] if include_pending else ["RELEASED"]
        all_items = self.session.scalars(
            select(BOMItem).where(BOMItem.status.in_(statuses)).order_by(BOMItem.find_number, BOMItem.child_pn)
        ).all()

        by_parent: Dict[str, List[BOMItem]] = defaultdict(list)
        by_child: Dict[str, List[BOMItem]] = defaultdict(list)
        parents_with_pending = {it.parent_pn for it in all_items if it.status == "PENDING_ECO"}

        for it in all_items:
            if include_pending and it.parent_pn in parents_with_pending:
                if it.status == "PENDING_ECO":
                    by_parent[it.parent_pn].append(it)
            else:
                if it.status == "RELEASED":
                    by_parent[it.parent_pn].append(it)
            by_child[it.child_pn].append(it)

        return parts_map, by_parent, by_child

    def get_indented_bom(
        self,
        root_pn: str,
        include_pending: bool = False,
        single_level_only: bool = False,
        condition_filter: Optional[str] = None
    ) -> List[Dict]:
        r_pn = root_pn.strip().upper()
        parts_map, by_parent, _ = self._load_full_bom_graph(include_pending=include_pending)
        if r_pn not in parts_map:
            raise ValueError(f"Part Number '{r_pn}' does not exist.")

        allowed_conds: Optional[Set[str]] = None
        if condition_filter and condition_filter.strip():
            allowed_conds = {c.strip().upper() for c in re.split(r"[,\s]+", condition_filter.strip()) if c.strip()}

        rows: List[Dict] = []

        def _walk(curr_pn: str, level: int, mult: float, parent_node: str):
            for idx, item in enumerate(by_parent.get(curr_pn, ()), start=1):
                c = parts_map.get(item.child_pn)
                if not c:
                    continue
                cond = (item.condition_code or c.condition_code or "").strip().upper()
                if allowed_conds and cond and cond not in allowed_conds:
                    continue

                ext_qty = item.quantity * mult
                ext_wt = (c.unit_weight or 0.0) * ext_qty
                node_id = f"{parent_node}.{idx}_{c.part_number}"
                rows.append({
                    "node_id": node_id, "parent_node_id": parent_node, "level": level + 1,
                    "tree_pn": ("    " * level) + ("|-- " if level > 0 else "") + c.part_number,
                    "part_number": c.part_number, "description": c.standard_name,
                    "type": c.part_type + (" (BULK)" if c.is_bulk else ""),
                    "source_type": c.source_type,
                    "condition_code": cond or "-",
                    "supply_class": item.supply_class, "bom_status": f"{item.status} ({item.eco_number})",
                    "find": item.find_number or "-", "unit_qty": item.quantity, "ext_qty": ext_qty,
                    "unit_weight": c.unit_weight or 0.0, "ext_weight": ext_wt,
                    "uom": c.uom, "revision": c.revision,
                    "material": c.material_rel.name if c.material_rel else "N/A"
                })
                if not single_level_only:
                    _walk(c.part_number, level + 1, ext_qty, node_id)

        _walk(r_pn, 0, 1.0, "ROOT")
        return rows

    def where_used(self, target_pn: str, include_pending: bool = True, single_level_only: bool = False) -> List[Dict]:
        t_pn = target_pn.strip().upper()
        parts_map, _, by_child = self._load_full_bom_graph(include_pending=include_pending)
        if t_pn not in parts_map:
            raise ValueError(f"Part Number '{t_pn}' does not exist.")

        results: List[Dict] = []

        def _walk_up(curr_pn: str, depth: int, parent_node: str):
            for idx, u in enumerate(by_child.get(curr_pn, ()), start=1):
                p = parts_map.get(u.parent_pn)
                c = parts_map.get(u.child_pn)
                if not p or not c:
                    continue
                node_id = f"{parent_node}.{idx}_{p.part_number}"
                results.append({
                    "node_id": node_id, "parent_node_id": parent_node, "tier": depth,
                    "tree_pn": ("    " * (depth - 1)) + ("^-- " if depth > 1 else "") + p.part_number,
                    "parent_pn": p.part_number, "parent_description": p.standard_name,
                    "parent_type": p.part_type, "condition_code": u.condition_code or p.condition_code or "-",
                    "supply_class": u.supply_class, "bom_status": f"{u.status} ({u.eco_number})",
                    "rev": p.revision, "qty_per": u.quantity, "uom": c.uom, "find": u.find_number or "-"
                })
                if not single_level_only:
                    _walk_up(p.part_number, depth + 1, node_id)

        _walk_up(t_pn, 1, "ROOT")
        return results

    def compare_boms(self, assembly_pns: List[str], include_pending: bool = False, condition_filter: Optional[str] = None) -> Dict:
        cleaned = []
        for p in assembly_pns:
            v = p.strip().upper()
            if v and v not in cleaned:
                cleaned.append(v)
        if not (2 <= len(cleaned) <= 4):
            raise ValueError("Provide between 2 and 4 distinct part numbers to compare.")
        rolled: Dict[str, Dict[str, float]] = {}
        all_pns = set()
        for asm in cleaned:
            t = defaultdict(float)
            for r in self.get_indented_bom(asm, include_pending=include_pending, single_level_only=False, condition_filter=condition_filter):
                t[r["part_number"]] += float(r["ext_qty"])
                all_pns.add(r["part_number"])
            rolled[asm] = t
        headers = ["Part Number", "Noun, Description", "Category", "Cond", "UOM", "Rev", "Status"] + [f"{pn} Qty" for pn in cleaned]
        rows = []
        for cp in sorted(all_pns):
            part = self.session.get(Part, cp)
            qtys = [rolled[a].get(cp, 0.0) for a in cleaned]
            status = "SAME" if len(set(qtys)) == 1 else "DIFF"
            rows.append([
                cp, part.standard_name, part.part_type + (" (BULK)" if part.is_bulk else ""),
                part.condition_code or "-", part.uom,
                f"{part.revision} ({'PROTO' if part.is_prototype else 'PROD'})", status
            ] + [f"{q:g}" if q > 0 else "-" for q in qtys])
        return {"headers": headers, "rows": rows}
