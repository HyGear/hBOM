"""
Zero-Dependency Native Landscape PDF Generator for hBOM Tabular ECO Reports.
Renders wide engineering tables in Landscape orientation (792 x 612 pt) with:
- Dark Slate Header Banner & Color Legend
- Shaded Table Header Bars (`| Act | ...`)
- Color-Coded Data Rows:
  * GREEN (`| + |`) for Added Parts & BOM Additions
  * RED   (`| - |`) for Removed BOM Items & Unregistered Drawings
  * BLUE  (`| ~ |`) for Changed BOM Rows & Modified Part BEFORE/AFTER Rows
"""

from typing import List, Tuple


def _pdf_escape(text: str) -> str:
    clean = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in str(text))
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _classify_table_line(line: str) -> str:
    s = line.strip()
    if s.startswith("===") or s.startswith("---"):
        return "DIVIDER"
    if s.startswith("+---") or s.startswith("+==="):
        return "TBL_BORDER"
    if s[:2] in ("1.", "2.", "3.", "4.", "5.") or s.startswith("PARENT ASSEMBLY:"):
        return "SECTION"
    if s.startswith("| Act |") or s.startswith("| St  |"):
        return "TBL_HEADER"
    if s.startswith("| +"):
        return "ADDED"
    if s.startswith("| -"):
        return "REMOVED"
    if s.startswith("| ~") or s.startswith("^--"):
        return "CHANGED"
    return "NORMAL"


def generate_eco_pdf_file(filepath: str, eco_number: str, report_text: str) -> str:
    """Renders the tabular ECO Summary Report into a Landscape Letter PDF (792x612 pt)."""
    styled_lines: List[Tuple[str, str]] = [
        (raw_line, _classify_table_line(raw_line))
        for raw_line in report_text.splitlines()
    ]

    lines_per_page = 38
    pages: List[List[Tuple[str, str]]] = [
        styled_lines[i:i + lines_per_page]
        for i in range(0, max(1, len(styled_lines)), lines_per_page)
    ]

    objects: List[bytes] = []

    def add_obj(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(b"")  # Pages placeholder
    font_helv = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    font_mono = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    font_mono_bold = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")

    page_obj_ids: List[int] = []
    total_pages = len(pages)

    # Landscape dimensions: Width = 792 pt, Height = 612 pt
    for page_idx, chunk in enumerate(pages, start=1):
        cmds: List[str] = []

        # Top Dark Slate Banner
        cmds.append("0.06 0.09 0.16 rg 28 552 736 34 re f")
        cmds.append("0.23 0.51 0.96 rg 28 549 736 3 re f")
        cmds.append("BT /F2 11.5 Tf 1 1 1 rg 38 565 Td")
        cmds.append(f"({_pdf_escape(f'hBOM (v1.0) — TABULAR ENGINEERING CHANGE ORDER REPORT: {eco_number}')}) Tj ET")
        cmds.append("BT /F1 8.5 Tf 0.75 0.82 0.90 rg 695 565 Td")
        cmds.append(f"({_pdf_escape(f'Page {page_idx} of {total_pages}')}) Tj ET")

        # Color Legend Bar
        cmds.append("0.94 0.96 0.98 rg 28 533 736 14 re f")
        cmds.append("BT /F2 7.5 Tf 0.05 0.48 0.20 rg 38 537 Td ([+ GREEN ROW = Added]) Tj ET")
        cmds.append("BT /F2 7.5 Tf 0.76 0.12 0.12 rg 175 537 Td ([- RED ROW = Removed]) Tj ET")
        cmds.append("BT /F2 7.5 Tf 0.08 0.36 0.78 rg 315 537 Td ([~ BLUE ROW = Changed / Before->After]) Tj ET")
        cmds.append("BT /F2 7.5 Tf 0.25 0.30 0.36 rg 525 537 Td ([= GRAY ROW = Unchanged Context]) Tj ET")

        y = 518
        for line_text, style in chunk:
            clipped = line_text[:152]
            if style == "DIVIDER":
                cmds.append(f"0.80 0.84 0.88 RG 0.6 w 30 {y + 3} m 762 {y + 3} l S")
                y -= 8
                continue
            if style == "TBL_BORDER":
                cmds.append(f"0.75 0.80 0.86 RG 0.4 w 30 {y + 3} m 762 {y + 3} l S")
                y -= 6
                continue

            if style == "SECTION":
                cmds.append(f"0.85 0.90 0.96 rg 28 {y - 2} 736 12 re f")
                cmds.append(f"BT /F2 8.2 Tf 0.06 0.12 0.24 rg 34 {y} Td ({_pdf_escape(clipped)}) Tj ET")
                y -= 13
            elif style == "TBL_HEADER":
                cmds.append(f"0.18 0.24 0.34 rg 30 {y - 2} 732 12 re f")
                cmds.append(f"BT /F4 7.2 Tf 1 1 1 rg 34 {y} Td ({_pdf_escape(clipped)}) Tj ET")
                y -= 12.5
            elif style == "ADDED":
                cmds.append(f"0.90 0.98 0.92 rg 30 {y - 2} 732 11.5 re f")
                cmds.append(f"BT /F4 7.2 Tf 0.04 0.46 0.18 rg 34 {y} Td ({_pdf_escape(clipped)}) Tj ET")
                y -= 12
            elif style == "REMOVED":
                cmds.append(f"0.99 0.91 0.91 rg 30 {y - 2} 732 11.5 re f")
                cmds.append(f"BT /F4 7.2 Tf 0.76 0.12 0.12 rg 34 {y} Td ({_pdf_escape(clipped)}) Tj ET")
                y -= 12
            elif style == "CHANGED":
                cmds.append(f"0.90 0.95 1.00 rg 30 {y - 2} 732 11.5 re f")
                cmds.append(f"BT /F4 7.2 Tf 0.08 0.36 0.78 rg 34 {y} Td ({_pdf_escape(clipped)}) Tj ET")
                y -= 12
            else:
                cmds.append(f"BT /F3 7.2 Tf 0.18 0.22 0.28 rg 34 {y} Td ({_pdf_escape(clipped)}) Tj ET")
                y -= 11.5

        cmds.append("0.82 0.86 0.90 RG 0.5 w 28 30 m 764 30 l S")
        cmds.append("BT /F1 7 Tf 0.45 0.50 0.58 rg 32 20 Td (Generated by hBOM (v1.0) — Tabular Engineering Change Order Report) Tj ET")

        stream_bytes = "\n".join(cmds).encode("latin-1", errors="replace")
        content_id = add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii") + stream_bytes + b"\nendstream"
        )
        page_id = add_obj(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 792 612] "
            f"/Resources << /Font << /F1 {font_helv} 0 R /F2 {font_bold} 0 R /F3 {font_mono} 0 R /F4 {font_mono_bold} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode("ascii")
        )
        page_obj_ids.append(page_id)

    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = []
    for idx, obj_bytes in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj_bytes)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )

    with open(filepath, "wb") as f:
        f.write(out)
    return filepath
