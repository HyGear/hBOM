"""SQLAlchemy ORM Data Models for hBOM (v1.0 / Engine v2.0)."""
import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey,
    DateTime, Enum, Text, CheckConstraint, Index
)
from sqlalchemy.orm import relationship
from database import Base

PART_TYPES = ("PART", "PRODUCTION SUBASSEMBLY", "PRODUCT")
SOURCE_TYPES = ("MAKE", "BUY", "PHANTOM")
ECO_TYPES = ("PRODUCTION", "PROTOTYPE")
ECO_STATUSES = ("REQUESTED", "OPEN", "PENDING_APPROVAL", "APPROVED", "RELEASED")
RELEASE_STATES = ("PENDING_ECO", "RELEASED", "OBSOLETE")
SUPPLY_CLASSES = ("AVAILABLE", "NOT AVAILABLE")
DRAWING_TYPE_ENUM = ("SINGLE", "LH/RH PAIR", "TABULATED")


class PartNumberSequence(Base):
    __tablename__ = "part_number_sequences"
    prefix = Column(String(32), primary_key=True)
    digits_length = Column(Integer, nullable=False, default=8)
    current_val = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Noun(Base):
    __tablename__ = "nouns"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    short_definition = Column(String(255), nullable=False, default="")
    parts = relationship("Part", back_populates="noun_rel")


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    specification = Column(String(120), nullable=True)
    parts = relationship("Part", back_populates="material_rel")


class EngineeringChange(Base):
    __tablename__ = "engineering_changes"
    eco_number = Column(String(32), primary_key=True)
    eco_type = Column(Enum(*ECO_TYPES, name="eco_type_enum"), nullable=False, default="PRODUCTION")
    title = Column(String(150), nullable=False, default="Pending ECO Details")
    reason = Column(Text, nullable=False, default="")
    status = Column(Enum(*ECO_STATUSES, name="eco_status_enum"), default="OPEN", nullable=False)
    created_by = Column(String(64), default="System", nullable=False)
    approved_by = Column(String(64), nullable=True)
    released_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    released_at = Column(DateTime, nullable=True)

    parts_created = relationship("Part", back_populates="eco_rel")
    pending_part_updates = relationship("PartPendingUpdate", back_populates="eco_rel", cascade="all, delete-orphan")
    staged_bom_items = relationship("BOMItem", back_populates="eco_rel")
    attachments = relationship("ECOAttachment", back_populates="eco_rel", cascade="all, delete-orphan")
    drawing_reg_items = relationship("ECODrawingRegistrationItem", back_populates="eco_rel", cascade="all, delete-orphan")


class ECOAttachment(Base):
    __tablename__ = "eco_attachments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    eco_number = Column(String(32), ForeignKey("engineering_changes.eco_number", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(180), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_sha256 = Column(String(64), default="", nullable=False)
    description = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    eco_rel = relationship("EngineeringChange", back_populates="attachments")


class ECODrawingRegistrationItem(Base):
    __tablename__ = "eco_drawing_registration_list"
    id = Column(Integer, primary_key=True, autoincrement=True)
    eco_number = Column(String(32), ForeignKey("engineering_changes.eco_number", ondelete="CASCADE"), nullable=False)
    part_pn = Column(String(64), ForeignKey("parts.part_number", ondelete="CASCADE"), nullable=False)
    drawing_number = Column(String(64), nullable=False)
    drawing_type = Column(String(24), default="SINGLE", nullable=False)
    config_label = Column(String(120), default="STD", nullable=False)
    target_rev = Column(String(8), nullable=False)
    sheet_size = Column(String(16), default="D", nullable=False)
    notes = Column(String(255), default="", nullable=False)
    is_registered = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime, nullable=True)

    eco_rel = relationship("EngineeringChange", back_populates="drawing_reg_items")
    part = relationship("Part")


class Part(Base):
    __tablename__ = "parts"
    part_number = Column(String(64), primary_key=True)
    noun_id = Column(Integer, ForeignKey("nouns.id"), nullable=False)
    description = Column(String(255), nullable=False)
    part_type = Column(Enum(*PART_TYPES, name="part_type_enum"), nullable=False, default="PART")
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)

    finish = Column(String(32), default="RAW", nullable=False)
    envelope = Column(String(64), default="", nullable=False)
    material_size = Column(String(120), default="", nullable=False)
    drawing_size = Column(String(16), default="D", nullable=False)
    condition_code = Column(String(3), default="", nullable=False)

    # New v2.0 Make/Buy/Phantom & Unit Weight fields
    source_type = Column(String(16), default="MAKE", nullable=False)
    unit_weight = Column(Float, default=0.0, nullable=False)

    is_bulk = Column(Boolean, default=False, nullable=False)
    uom = Column(String(16), default="EA", nullable=False)
    is_prototype = Column(Boolean, default=False, nullable=False)
    revision = Column(String(8), default="A", nullable=False)

    eco_number = Column(String(32), ForeignKey("engineering_changes.eco_number"), nullable=False)
    release_status = Column(Enum(*RELEASE_STATES, name="part_release_status_enum"), nullable=False, default="PENDING_ECO")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_part_type_status", "part_type", "release_status"),
    )

    noun_rel = relationship("Noun", back_populates="parts")
    material_rel = relationship("Material", back_populates="parts")
    eco_rel = relationship("EngineeringChange", back_populates="parts_created")
    pending_updates = relationship("PartPendingUpdate", back_populates="part", cascade="all, delete-orphan")
    drawing_links = relationship("DrawingPartLink", back_populates="part", cascade="all, delete-orphan")

    bom_parents = relationship("BOMItem", foreign_keys="[BOMItem.parent_pn]", back_populates="parent", cascade="all, delete-orphan")
    bom_children = relationship("BOMItem", foreign_keys="[BOMItem.child_pn]", back_populates="child")

    @property
    def standard_name(self) -> str:
        n_str = self.noun_rel.name.strip().upper() if self.noun_rel else "UNKNOWN"
        return f"{n_str}, {self.description.strip()}"

    @property
    def lifecycle_label(self) -> str:
        return "PROTOTYPE" if self.is_prototype else "PRODUCTION"


class PartPendingUpdate(Base):
    __tablename__ = "part_pending_updates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_number = Column(String(64), ForeignKey("parts.part_number", ondelete="CASCADE"), nullable=False)
    eco_number = Column(String(32), ForeignKey("engineering_changes.eco_number", ondelete="CASCADE"), nullable=False)

    new_noun_id = Column(Integer, ForeignKey("nouns.id"), nullable=False)
    new_description = Column(String(255), nullable=False)
    new_material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    new_finish = Column(String(32), default="RAW", nullable=False)
    new_envelope = Column(String(64), default="", nullable=False)
    new_material_size = Column(String(120), default="", nullable=False)
    new_drawing_size = Column(String(16), default="D", nullable=False)
    new_condition_code = Column(String(3), default="", nullable=False)
    new_source_type = Column(String(16), default="MAKE", nullable=False)
    new_unit_weight = Column(Float, default=0.0, nullable=False)
    new_is_bulk = Column(Boolean, default=False, nullable=False)
    new_uom = Column(String(16), default="EA", nullable=False)
    new_is_prototype = Column(Boolean, default=False, nullable=False)
    new_revision = Column(String(8), nullable=False)
    status = Column(Enum("PENDING_ECO", "APPLIED", name="pending_update_status_enum"), default="PENDING_ECO", nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    part = relationship("Part", back_populates="pending_updates")
    eco_rel = relationship("EngineeringChange", back_populates="pending_part_updates")
    new_noun_rel = relationship("Noun")
    new_material_rel = relationship("Material")


class BOMItem(Base):
    __tablename__ = "bom_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_pn = Column(String(64), ForeignKey("parts.part_number", ondelete="CASCADE"), nullable=False)
    child_pn = Column(String(64), ForeignKey("parts.part_number"), nullable=False)
    find_number = Column(Integer, nullable=True)
    quantity = Column(Float, nullable=False, default=1.0)
    supply_class = Column(Enum(*SUPPLY_CLASSES, name="supply_class_enum"), default="AVAILABLE", nullable=False)
    condition_code = Column(String(3), default="", nullable=False)
    eco_number = Column(String(32), ForeignKey("engineering_changes.eco_number"), nullable=False)
    superseded_by_eco = Column(String(32), nullable=True)
    status = Column(Enum("PENDING_ECO", "RELEASED", "SUPERSEDED", name="bom_item_status_enum"), default="PENDING_ECO", nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_positive_qty"),
        CheckConstraint("parent_pn != child_pn", name="chk_no_self_ref"),
        Index("ix_bom_parent_status", "parent_pn", "status"),
        Index("ix_bom_child_status", "child_pn", "status"),
    )

    parent = relationship("Part", foreign_keys=[parent_pn], back_populates="bom_parents")
    child = relationship("Part", foreign_keys=[child_pn], back_populates="bom_children")
    eco_rel = relationship("EngineeringChange", back_populates="staged_bom_items")


class Drawing(Base):
    __tablename__ = "drawings"
    drawing_number = Column(String(64), primary_key=True)
    drawing_type = Column(Enum(*DRAWING_TYPE_ENUM, name="drawing_type_enum"), default="SINGLE", nullable=False)
    part_pn = Column(String(64), ForeignKey("parts.part_number", ondelete="CASCADE"), nullable=False)
    revision = Column(String(8), default="A", nullable=False)
    eco_number = Column(String(32), nullable=True)
    file_path = Column(String(512), nullable=False)
    file_sha256 = Column(String(64), default="", nullable=False)
    sheet_size = Column(String(16), default="D", nullable=False)
    sheet_count = Column(Integer, default=1, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    part_links = relationship("DrawingPartLink", back_populates="drawing", cascade="all, delete-orphan")
    revision_history = relationship("DrawingRevisionHistory", back_populates="drawing", cascade="all, delete-orphan")
    supporting_docs = relationship("DrawingSupportingDoc", back_populates="drawing", cascade="all, delete-orphan")


class DrawingPartLink(Base):
    __tablename__ = "drawing_part_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    drawing_number = Column(String(64), ForeignKey("drawings.drawing_number", ondelete="CASCADE"), nullable=False)
    part_pn = Column(String(64), ForeignKey("parts.part_number", ondelete="CASCADE"), nullable=False)
    config_label = Column(String(120), default="STD", nullable=False)

    drawing = relationship("Drawing", back_populates="part_links")
    part = relationship("Part", back_populates="drawing_links")


class DrawingRevisionHistory(Base):
    __tablename__ = "drawing_revision_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    drawing_number = Column(String(64), ForeignKey("drawings.drawing_number", ondelete="CASCADE"), nullable=False)
    drawing_type = Column(String(24), default="SINGLE", nullable=False)
    linked_parts_summary = Column(String(512), nullable=False)
    revision = Column(String(8), nullable=False)
    eco_number = Column(String(32), nullable=True)
    file_path = Column(String(512), nullable=False)
    file_sha256 = Column(String(64), default="", nullable=False)
    registered_by = Column(String(64), default="System", nullable=False)
    sheet_size = Column(String(16), default="D", nullable=False)
    sheet_count = Column(Integer, default=1, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="revision_history")


class DrawingSupportingDoc(Base):
    __tablename__ = "drawing_supporting_docs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    drawing_number = Column(String(64), ForeignKey("drawings.drawing_number", ondelete="CASCADE"), nullable=False)
    doc_type = Column(String(64), default="SUPPLIER DRAWING", nullable=False)
    file_name = Column(String(180), nullable=False)
    file_path = Column(String(512), nullable=False)
    description = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="supporting_docs")


class UserAccount(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    userid = Column(String(50), primary_key=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(40), nullable=False, default="VIEWER (Read-Only)")
    full_name = Column(String(120), nullable=False, default="")
    status = Column(String(20), nullable=False, default="ACTIVE")
    email = Column(String(120), nullable=False, default="")

User = UserAccount
