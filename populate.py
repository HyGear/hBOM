"""
Advanced Colt 1911 ECO Changes Seeder (`populate_eco_changes.py`)
Populates the hBOM database with rich ECO changes including part additions,
part modifications (pending updates), BOM markups, drawing registrations, and attachments.
"""

import datetime
from database import session_scope, init_db
from models import (
    Noun, Material, EngineeringChange, Part, PartPendingUpdate, 
    BOMItem, Drawing, DrawingPartLink, DrawingRevisionHistory, 
    ECODrawingRegistrationItem, ECOAttachment
)

def seed_eco_changes():
    init_db()
    print("Initializing Rich ECO Changes Seeding...")
    
    with session_scope() as s:
        # 1. Ensure Nouns Exist
        nouns_data = [
            ("PISTOL", "Top-level semi-automatic handgun assembly"),
            ("FRAME", "Main structural receiver housing fire control group"),
            ("SLIDE", "Reciprocating upper receiver housing barrel and sights"),
            ("BARREL", "Chambered pressure vessel and rifled projectile guide"),
            ("TRIGGER", "Linear pull actuator for fire control"),
            ("HAMMER", "Pivoting spring-loaded impact striker"),
            ("SAFETY", "Manual thumb safety mechanism"),
            ("MAGAZINE", "Detachable ammunition column container"),
            ("GRIP", "Ergonomic side handle panel"),
            ("BUSHING", "Cylindrical sleeve bearing"),
            ("SPRING", "Energy storage elastic element"),
            ("PIN", "Machined cylindrical pivot or retention shaft")
        ]
        nouns = {}
        for name, defn in nouns_data:
            n = s.query(Noun).filter_by(name=name).first()
            if not n:
                n = Noun(name=name, short_definition=defn)
                s.add(n)
                s.flush()
            nouns[name] = n

        # 2. Ensure Materials Exist
        mats_data = [
            ("Alloy Steel 4140", "SAE 4140 Quenched & Tempered"),
            ("Stainless Steel 416", "ASTM A582 Free-Machining Martensitic Stainless"),
            ("American Walnut", "Mil-Spec Graded Gunstock Timber"),
            ("Carbon Steel 1065", "Spring Steel Heat Treated")
        ]
        mats = {}
        for m_name, spec in mats_data:
            m = s.query(Material).filter_by(name=m_name).first()
            if not m:
                m = Material(name=m_name, specification=spec)
                s.add(m)
                s.flush()
            mats[m_name] = m

        # 3. Create ECOs in Various States
        eco_rel = s.query(EngineeringChange).filter_by(eco_number="ECO-000500").first()
        if not eco_rel:
            eco_rel = EngineeringChange(
                eco_number="ECO-000500", eco_type="PRODUCTION",
                title="M1911A1 Government Baseline Production Release",
                reason="Initial baseline release of standard military specification configuration including frame, slide, barrel, and trigger groups.",
                status="RELEASED", created_by="admin", approved_by="admin", released_by="admin",
                created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10),
                released_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=8)
            )
            s.add(eco_rel)

        eco_app = s.query(EngineeringChange).filter_by(eco_number="ECO-000501").first()
        if not eco_app:
            eco_app = EngineeringChange(
                eco_number="ECO-000501", eco_type="PRODUCTION",
                title="Match Grade Stainless Barrel & Precision Bushing Upgrade",
                reason="1. Transition standard carbon steel barrel to match-grade stainless steel.\n2. Update barrel bushing tolerance for improved lockup accuracy.",
                status="APPROVED", created_by="engineer", approved_by="approver",
                created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5),
                approved_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
            )
            s.add(eco_app)

        eco_pen = s.query(EngineeringChange).filter_by(eco_number="ECO-000502").first()
        if not eco_pen:
            eco_pen = EngineeringChange(
                eco_number="ECO-000502", eco_type="PRODUCTION",
                title="Ambidextrous Extended Safety & Skeletonized Match Trigger",
                reason="Add modular ambidextrous thumb safety kit for tactical operators and replace standard trigger with skeletonized match version.",
                status="PENDING_APPROVAL", created_by="engineer",
                created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
                submitted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
            )
            s.add(eco_pen)

        eco_opn = s.query(EngineeringChange).filter_by(eco_number="ECO-000503").first()
        if not eco_opn:
            eco_opn = EngineeringChange(
                eco_number="ECO-000503", eco_type="PRODUCTION",
                title="Checkered American Walnut Custom Grip Panels & Housing",
                reason="Introduce premium diamond-checkered American Walnut grip panel option and checkered mainspring housing.",
                status="OPEN", created_by="engineer",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            s.add(eco_opn)

        eco_req = s.query(EngineeringChange).filter_by(eco_number="PECO-000504").first()
        if not eco_req:
            eco_req = EngineeringChange(
                eco_number="PECO-000504", eco_type="PROTOTYPE",
                title="Threaded Suppressor Barrel Prototype Evaluation",
                reason="Request experimental 0.578-28 threaded muzzle barrel variant for sound suppressor compatibility testing.",
                status="REQUESTED", created_by="engineer",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            s.add(eco_req)
        s.flush()

        # 4. Create Baseline Parts (Created under ECO-000500)
        parts_eco000500 = [
            ("1AF00000500", nouns["FRAME"], "Stripped Government Frame Receiver Casting", "PART", mats["Alloy Steel 4140"], "BLUED", "140X90X25", "MAKE", 0.42, "Casting", "C", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000501", nouns["SLIDE"], "Government Slide Machined Shell", "PART", mats["Alloy Steel 4140"], "BLUED", "185X35X25", "MAKE", 0.45, "Forging", "C", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000502", nouns["BARREL"], "Standard 5-Inch Carbon Steel Barrel .45 ACP", "PART", mats["Alloy Steel 4140"], "BLUED", "135X20X20", "MAKE", 0.17, "Bar Stock", "B", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000503", nouns["TRIGGER"], "Standard Long Military Trigger Bow", "PART", mats["Alloy Steel 4140"], "BLUED", "45X20X10", "MAKE", 0.03, "Stamped", "A", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000504", nouns["HAMMER"], "Standard Spur Hammer", "PART", mats["Alloy Steel 4140"], "BLUED", "30X25X10", "MAKE", 0.04, "Forging", "A", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000505", nouns["SAFETY"], "Standard Thumb Safety Lock", "PART", mats["Alloy Steel 4140"], "BLUED", "35X20X10", "MAKE", 0.02, "Bar Stock", "A", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000506", nouns["MAGAZINE"], "7-Round Blued Steel Magazine Assembly", "PART", mats["Carbon Steel 1065"], "BLUED", "125X35X15", "BUY", 0.08, "Sheet Metal", "B", False, "EA", "ECO-000500", "RELEASED"),
            ("1AF00000507", nouns["GRIP"], "Standard Checkered Plastic Grip Panel Set", "PART", mats["American Walnut"], "BLACK", "100X35X7", "BUY", 0.03, "Molded", "B", False, "EA", "ECO-000500", "RELEASED"),
            ("2AS00000500", nouns["FRAME"], "Complete Lower Frame & Fire Control Assembly", "PRODUCTION SUBASSEMBLY", mats["Alloy Steel 4140"], "BLUED", "140X90X28", "MAKE", 0.55, "Assembly Kit", "C", False, "EA", "ECO-000500", "RELEASED"),
            ("2AS00000501", nouns["SLIDE"], "Complete Upper Slide & Barrel Assembly", "PRODUCTION SUBASSEMBLY", mats["Alloy Steel 4140"], "BLUED", "185X35X30", "MAKE", 0.68, "Assembly Kit", "C", False, "EA", "ECO-000500", "RELEASED"),
            ("3PR00000500", nouns["PISTOL"], "M1911A1 Government Service Model .45 ACP", "PRODUCT", mats["Alloy Steel 4140"], "BLUED", "219X140X33", "MAKE", 1.25, "System Kit", "D", False, "EA", "ECO-000500", "RELEASED")
        ]

        for pn, n_obj, desc, p_type, mat_obj, fin, env, src_t, wt, m_size, dwg_s, is_b, uom_str, eco_n, rel_st in parts_eco000500:
            p = s.query(Part).filter_by(part_number=pn).first()
            if not p:
                p = Part(
                    part_number=pn, noun_id=n_obj.id, description=desc, part_type=p_type,
                    material_id=mat_obj.id if mat_obj else None, finish=fin, envelope=env,
                    source_type=src_t, unit_weight=wt, material_size=m_size, drawing_size=dwg_s,
                    is_bulk=is_b, uom=uom_str, eco_number=eco_n, release_status=rel_st
                )
                s.add(p)
        s.flush()

        # 5. Create New Parts Added Under ECO-000501 (Match Grade Upgrade)
        match_barrel = s.query(Part).filter_by(part_number="1AF00000508").first()
        if not match_barrel:
            match_barrel = Part(
                part_number="1AF00000508", noun_id=nouns["BARREL"].id,
                description="Match Grade Stainless Steel 5-Inch Barrel .45 ACP",
                part_type="PART", material_id=mats["Stainless Steel 416"].id,
                finish="POLISHED", envelope="135X20X20", source_type="MAKE",
                unit_weight=0.19, material_size="Bar Stock Machined", drawing_size="B",
                uom="EA", eco_number="ECO-000501", release_status="PENDING_ECO"
            )
            s.add(match_barrel)

        match_bushing = s.query(Part).filter_by(part_number="1AF00000509").first()
        if not match_bushing:
            match_bushing = Part(
                part_number="1AF00000509", noun_id=nouns["BUSHING"].id,
                description="Match Fit Precision Barrel Bushing",
                part_type="PART", material_id=mats["Stainless Steel 416"].id,
                finish="POLISHED", envelope="20X20X15", source_type="MAKE",
                unit_weight=0.02, material_size="Bar Stock", drawing_size="A",
                uom="EA", eco_number="ECO-000501", release_status="PENDING_ECO"
            )
            s.add(match_bushing)

        # 6. Create Part Modification (Pending Update) on Existing Part via ECO-000501
        pending_mod = s.query(PartPendingUpdate).filter_by(part_number="1AF00000502", eco_number="ECO-000501").first()
        if not pending_mod:
            pending_mod = PartPendingUpdate(
                part_number="1AF00000502", eco_number="ECO-000501",
                new_noun_id=nouns["BARREL"].id,
                new_description="Standard 5-Inch Carbon Steel Barrel .45 ACP (Rev B Tolerance)",
                new_material_id=mats["Alloy Steel 4140"].id,
                new_finish="BLUED", new_envelope="135X20X20",
                new_material_size="Bar Stock", new_drawing_size="B",
                new_condition_code="STD", new_is_bulk=False, new_uom="EA",
                new_is_prototype=False, new_revision="B", status="PENDING_ECO",
                new_source_type="MAKE", new_unit_weight=0.17
            )
            s.add(pending_mod)

        # 7. Create New Parts Under ECO-000503 (Open ECO - Walnut Grips)
        walnut_grips = s.query(Part).filter_by(part_number="1AF00000510").first()
        if not walnut_grips:
            walnut_grips = Part(
                part_number="1AF00000510", noun_id=nouns["GRIP"].id,
                description="Diamond Checkered American Walnut Grip Panels",
                part_type="PART", material_id=mats["American Walnut"].id,
                finish="OILED", envelope="100X35X7", source_type="BUY",
                unit_weight=0.04, material_size="Timber Slab", drawing_size="B",
                uom="EA", eco_number="ECO-000503", release_status="PENDING_ECO"
            )
            s.add(walnut_grips)
        s.flush()

        # 8. Stage BOM Markups and Items
        boms_data = [
            ("2AS00000500", "1AF00000500", 10, 1.0, "STD", "ECO-000500", "RELEASED"),
            ("2AS00000501", "1AF00000501", 10, 1.0, "STD", "ECO-000500", "RELEASED"),
            ("2AS00000501", "1AF00000502", 20, 1.0, "STD", "ECO-000500", "RELEASED"),
            ("3PR00000500", "2AS00000500", 10, 1.0, "STD", "ECO-000500", "RELEASED"),
            ("3PR00000500", "2AS00000501", 20, 1.0, "STD", "ECO-000500", "RELEASED"),
            ("2AS00000501", match_barrel.part_number, 20, 1.0, "MATCH", "ECO-000501", "PENDING_ECO"),
            ("2AS00000501", match_bushing.part_number, 25, 1.0, "MATCH", "ECO-000501", "PENDING_ECO"),
            ("2AS00000500", walnut_grips.part_number, 15, 1.0, "WAL", "ECO-000503", "PENDING_ECO")
        ]

        for parent, child, find_n, qty, cond, eco_n, st in boms_data:
            existing = s.query(BOMItem).filter_by(parent_pn=parent, child_pn=child, eco_number=eco_n).first()
            if not existing:
                bi = BOMItem(
                    parent_pn=parent, child_pn=child, find_number=find_n, quantity=qty,
                    condition_code=cond, supply_class="AVAILABLE", eco_number=eco_n, status=st
                )
                s.add(bi)

        # 9. Register Drawings and Revision History for ECOs
        drawings_data = [
            ("DWG-M1911-FRAME-01", "SINGLE", "1AF00000500", "A", "ECO-000500", "vault/drawings/frame_revA.pdf", "C", 2, True),
            ("DWG-M1911-SLIDE-02", "SINGLE", "1AF00000501", "A", "ECO-000500", "vault/drawings/slide_revA.pdf", "C", 2, True),
            ("DWG-MATCH-BARREL-03", "SINGLE", "1AF00000508", "A", "ECO-000501", "vault/drawings/match_barrel_revA.pdf", "B", 1, True),
            ("DWG-WALNUT-GRIPS-04", "SINGLE", "1AF00000510", "A", "ECO-000503", "vault/drawings/walnut_grips.pdf", "B", 1, False)
        ]

        for d_no, d_type, p_pn, rev, eco_n, path, sheet_sz, sheets, is_curr in drawings_data:
            dwg = s.query(Drawing).filter_by(drawing_number=d_no).first()
            if not dwg:
                dwg = Drawing(
                    drawing_number=d_no, drawing_type=d_type, part_pn=p_pn,
                    revision=rev, eco_number=eco_n, file_path=path,
                    sheet_size=sheet_sz, sheet_count=sheets
                )
                s.add(dwg)
                s.flush()

                rev_hist = DrawingRevisionHistory(
                    drawing_number=d_no, drawing_type=d_type,
                    linked_parts_summary=f"Primary Part: {p_pn}",
                    revision=rev, eco_number=eco_n, file_path=path,
                    sheet_size=sheet_sz, sheet_count=sheets, is_current=is_curr,
                    registered_by="J. Engineer"
                )
                s.add(rev_hist)

                chk = ECODrawingRegistrationItem(
                    eco_number=eco_n, part_pn=p_pn, drawing_number=d_no,
                    drawing_type=d_type, config_label="STD", target_rev=rev,
                    sheet_size=sheet_sz, notes=f"Official registration for {d_no}",
                    is_registered=is_curr
                )
                s.add(chk)

        # 10. Add File Attachments to Open ECO (ECO-000503)
        att = s.query(ECOAttachment).filter_by(eco_number="ECO-000503", file_name="Walnut_Grain_Specification.pdf").first()
        if not att:
            att = ECOAttachment(
                eco_number="ECO-000503",
                file_name="Walnut_Grain_Specification.pdf",
                file_path="vault/eco_attachments/Walnut_Grain_Specification.pdf",
                description="Supplier grade requirement and moisture content spec for American Walnut."
            )
            s.add(att)

        s.commit()
        print("\n" + "="*70)
        print("SUCCESS: Rich ECO Changes Seeded Successfully with Additions, Modifications, BOM Markups & Drawings!")
        print("="*70)

if __name__ == "__main__":
    seed_eco_changes()