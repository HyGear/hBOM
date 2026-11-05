"""Interactive Command-Line Interface Backup (v1.0)."""
import sys
from tabulate import tabulate
from database import init_db, session_scope
from services import BOMService
from pdf_generator import generate_eco_pdf_file


def run_cli():
    init_db()
    while True:
        print(chr(10) + "=== ENGINEERING BOM SYSTEM CLI (v1.0) ===")
        print("1. Pull ECO Number       2. Update ECO Info      3. ECO Summary Report (Text & PDF)")
        print("4. Submit ECO Approval   5. Approve ECO          6. Register Drawing (Single/LH-RH/Tab)")
        print("7. Release Approved ECO  8. BOM Lookup           9. Where-Used   0. Exit")
        ch = input("Select: ").strip()
        try:
            with session_scope() as s:
                svc = BOMService(s)
                if ch == "1":
                    et = input("Type (PRODUCTION/PROTOTYPE) [PRODUCTION]: ").strip().upper() or "PRODUCTION"
                    e = svc.pull_eco_number(et, title=input("Initial Title: "))
                    print(f"[OK] Pulled {e.eco_number} (Status: {e.status})")
                elif ch == "2":
                    svc.update_eco_info(input("ECO #: "), input("Title: "), input("Detailed Reason: "))
                    print("[OK] Updated ECO info.")
                elif ch == "3":
                    eno = input("ECO #: ").strip().upper()
                    rep = svc.generate_eco_summary_report(eno)
                    print(rep)
                    if input("Export PDF report? (y/n) [n]: ").lower() == "y":
                        pdf_path = f"{eno}_Summary_Report.pdf"
                        generate_eco_pdf_file(pdf_path, eno, rep)
                        print(f"[OK] Saved {pdf_path}")
                elif ch == "4":
                    svc.submit_eco_for_approval(input("ECO #: "))
                    print("[OK] Submitted for approval.")
                elif ch == "5":
                    svc.approve_eco(input("ECO #: "))
                    print("[OK] ECO Approved.")
                elif ch == "6":
                    dwg = input("Drawing #: ")
                    dtype = input("Mode (SINGLE / LH/RH PAIR / TABULATED) [SINGLE]: ").strip().upper() or "SINGLE"
                    path = input("File Path: ")
                    links = []
                    while True:
                        p = input("  Add Linked Part PN (Enter to finish): ").strip()
                        if not p:
                            break
                        cfg = input("  Config Label (STD, LH, RH, Color) [STD]: ").strip() or "STD"
                        links.append({"part_pn": p, "config_label": cfg})
                    svc.register_drawing(dwg, path, links, drawing_type=dtype)
                    print("[OK] Drawing Registered.")
                elif ch == "7":
                    svc.release_eco(input("ECO #: "))
                    print("[OK] ECO Released!")
                elif ch == "8":
                    rows = svc.get_indented_bom(input("Part/Assembly PN: "))
                    print(tabulate([[r["level"], r["tree_pn"], r["description"], r["condition_code"], r["supply_class"], r["unit_qty"], r["uom"]] for r in rows], headers=["Lvl", "PN", "Desc", "Cond", "Supply", "Qty", "UOM"]))
                elif ch == "9":
                    rows = svc.where_used(input("Component PN: "))
                    print(tabulate([[r["tier"], r["tree_pn"], r["parent_description"], r["condition_code"], r["qty_per"], r["uom"]] for r in rows], headers=["Tier", "Parent", "Desc", "Cond", "Qty", "UOM"]))
                elif ch == "0":
                    sys.exit(0)
        except Exception as e:
            print(f"[ERROR]: {e}")


if __name__ == "__main__":
    run_cli()
