"""
Rich HTML Interactive Help Manual & Overall Process Flowchart Data (`help_data.py`)
Matches exact 12-tab layout of hBOM Engineering BOM & ECO Manager.
"""

import re

DEFAULT_COLORS = {
    "bg_primary": "#0F172A",
    "bg_surface": "#1E293B",
    "fg_primary": "#F8FAFC",
    "fg_secondary": "#94A3B8",
    "accent_primary": "#38BDF8",
    "accent_success": "#22C55E",
    "accent_warning": "#F59E0B",
}

# 6-Stage Master End-to-End Engineering Process Pipeline
MASTER_PROCESS_STAGES = [
    ("1. SIGN IN & GOV", "Login / Settings / RBAC", "Tabs 11 & 12"),
    ("2. ECO / ECR INIT", "Pull ECO or Submit ECR", "Tab 5 (Start)"),
    ("3. ITEM AUTHORING", "Create / Modify Items", "Tabs 1, 2 & 3"),
    ("4. BOM & VAULT", "Stage BOM & Reg Dwgs", "Tabs 4 & 6"),
    ("5. VERIFY & AUDIT", "Lookup / Trace / Diff", "Tabs 7, 8, 9 & 10"),
    ("6. APPROVE & REL", "Gate Check & Release", "Tab 5 (Workflow)"),
]

HELP_FLOWCHARTS = {
    "00. System Overview & Login Security": {
        "master_active_indices": [0, 1, 2, 3, 4, 5],
        "master_focus_note": "Full End-to-End Lifecycle Overview — All 6 Master Process Stages Active",
    },
    "01. Tab 1: Product Setup (3PR)": {
        "master_active_indices": [2],
        "master_focus_note": "Overall Process Tie-In: Stage 3 (Item Authoring) — Top-Level Shippable Product (3PR) Definition",
    },
    "02. Tab 2: Prod Subassembly (2AS)": {
        "master_active_indices": [2],
        "master_focus_note": "Overall Process Tie-In: Stage 3 (Item Authoring) — Intermediate Production Subassemblies (2AS)",
    },
    "03. Tab 3: Part Setup (1AF Piece Parts & Bulk)": {
        "master_active_indices": [2],
        "master_focus_note": "Overall Process Tie-In: Stage 3 (Item Authoring) — Piece Parts & Bulk Consumables (1AF)",
    },
    "04. Tab 4: BOM Builder (Markup Staging)": {
        "master_active_indices": [3],
        "master_focus_note": "Overall Process Tie-In: Stage 4 (BOM & Vault) — Building Parent-Child Assembly Structures",
    },
    "05. Tab 5: ECO Manager & Graphical Approval Center": {
        "master_active_indices": [1, 5],
        "master_focus_note": "Overall Process Tie-In: Stage 2 (ECO Initiation) & Stage 6 (Workflow Approval & Production Release)",
    },
    "06. Tab 6: Drawing Registration (Vault Check-In)": {
        "master_active_indices": [3],
        "master_focus_note": "Overall Process Tie-In: Stage 4 (BOM & Vault) — Controlled CAD PDF Check-In & ECO Gate 3",
    },
    "07. Tab 7: BOM Lookup (Multi-Level Indented Tree)": {
        "master_active_indices": [4],
        "master_focus_note": "Overall Process Tie-In: Stage 5 (Verify & Audit) — Indented Multi-Level Tree & Weight Rollup",
    },
    "08. Tab 8: Where-Used (Upward Impact Analysis)": {
        "master_active_indices": [4],
        "master_focus_note": "Overall Process Tie-In: Stage 5 (Verify & Audit) — Bottom-Up Parent Impact Traceability",
    },
    "09. Tab 9: Compare BOMs (Side-by-Side Redline Diff)": {
        "master_active_indices": [4],
        "master_focus_note": "Overall Process Tie-In: Stage 5 (Verify & Audit) — Multi-Assembly Side-by-Side BOM Diff",
    },
    "10. Tab 10: Drawing Viewer (Vault Search & History)": {
        "master_active_indices": [4],
        "master_focus_note": "Overall Process Tie-In: Stage 5 (Verify & Audit) — Controlled Vault Drawing & Revision Retrieval",
    },
    "11. Tab 11: Settings (Nouns, Materials, UOMs & Themes)": {
        "master_active_indices": [0],
        "master_focus_note": "Overall Process Tie-In: Stage 1 (Sign In & Governance) — Engineering Standards & UI Theme Config",
    },
    "12. Tab 12: Administration (User Accounts & RBAC)": {
        "master_active_indices": [0],
        "master_focus_note": "Overall Process Tie-In: Stage 1 (Sign In & Governance) — User Accounts & Security Role Management",
    },
}

HTML_STYLE = """
<style>
    body {
        background-color: #1E293B;
        color: #F8FAFC;
        font-family: "Segoe UI", "Ubuntu", sans-serif;
        font-size: 10pt;
        line-height: 1.5;
        margin: 8px;
    }
    h1 {
        color: #38BDF8;
        font-size: 15pt;
        font-weight: bold;
        border-bottom: 2px solid #334155;
        padding-bottom: 6px;
        margin-top: 4px;
        margin-bottom: 10px;
    }
    h2 {
        color: #22C55E;
        font-size: 12pt;
        font-weight: bold;
        margin-top: 16px;
        margin-bottom: 6px;
    }
    h3 {
        color: #FBBF24;
        font-size: 10.5pt;
        font-weight: bold;
        margin-top: 12px;
        margin-bottom: 4px;
    }
    p {
        margin-top: 4px;
        margin-bottom: 8px;
        color: #E2E8F0;
    }
    a {
        color: #38BDF8;
        font-weight: bold;
        text-decoration: underline;
    }
    .intro-box {
        background-color: #0F172A;
        border-left: 4px solid #38BDF8;
        padding: 10px 14px;
        margin-bottom: 14px;
        color: #E2E8F0;
    }
    .tip-box {
        background-color: #0F172A;
        border-left: 4px solid #F59E0B;
        padding: 10px 14px;
        margin-top: 12px;
        margin-bottom: 12px;
        color: #FDE68A;
    }
    .step-num {
        color: #4ADE80;
        font-weight: bold;
    }
    .btn-blue {
        background-color: #2563EB;
        color: #FFFFFF;
        font-weight: bold;
        padding: 1px 6px;
    }
    .btn-green {
        background-color: #059669;
        color: #FFFFFF;
        font-weight: bold;
        padding: 1px 6px;
    }
    .btn-purple {
        background-color: #7C3AED;
        color: #FFFFFF;
        font-weight: bold;
        padding: 1px 6px;
    }
    .btn-slate {
        background-color: #334155;
        color: #F8FAFC;
        font-weight: bold;
        padding: 1px 6px;
    }
    .code-pill {
        background-color: #0F172A;
        color: #38BDF8;
        font-family: "Consolas", monospace;
        font-weight: bold;
        padding: 1px 5px;
    }
    table.ref-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        margin-bottom: 14px;
        background-color: #0F172A;
    }
    table.ref-table th {
        background-color: #263349;
        color: #38BDF8;
        font-weight: bold;
        text-align: left;
        padding: 7px 10px;
        border: 1px solid #334155;
    }
    table.ref-table td {
        padding: 7px 10px;
        border: 1px solid #334155;
        color: #E2E8F0;
        vertical-align: top;
    }
    .field-name {
        color: #FBBF24;
        font-weight: bold;
        white-space: nowrap;
    }
</style>
"""

HELP_TOPICS_HTML = {
    "00. System Overview & Login Security": """
<h1>00. Welcome to hBOM — Architecture, Philosophy &amp; Login Security</h1>
<div class="intro-box">
    <b>Why hBOM Exists:</b> Spreadsheets are great for grocery lists, but they are a minefield for manufacturing.
    One accidental copy-paste in Excel and suddenly the weld shop is burning 200 brackets out of the wrong plate thickness.
    <b>hBOM</b> gives you strict, audit-ready
    <a href="https://en.wikipedia.org/wiki/Product_data_management">Product Data Management (PDM)</a> and
    <a href="https://en.wikipedia.org/wiki/Configuration_management">Configuration Management</a> without the bloated
    six-figure enterprise headache.
</div>

<h2>1. The Three-Tier Part Numbering Architecture</h2>
<p>
    hBOM enforces a clean, semi-intelligent sequential numbering scheme where the <b>Part Number</b> is strictly isolated
    from its <b>Revision</b> (in accordance with <a href="https://en.wikipedia.org/wiki/ASME_Y14.100">ASME Y14.100 Engineering Drawing Practices</a>):
</p>
<ul>
    <li><span class="code-pill">3PR00000000</span> — <b>Top-Level Products (Tab 1):</b> Shippable end-items, complete tractor implements, or packaged kits.</li>
    <li><span class="code-pill">2AS00000000</span> — <b>Production Subassemblies (Tab 2):</b> Intermediate welded/assembled modules and configurable 3-digit Condition Code option groups.</li>
    <li><span class="code-pill">1AF00000000</span> — <b>Piece Parts &amp; Bulk Consumables (Tab 3):</b> Individual fabricated plates, machined shafts, purchased hydraulics, fasteners, and shop consumables.</li>
</ul>

<h2>2. Golden Rule of Change Control: Nothing Changes Without an ECO</h2>
<p>
    In hBOM, released production data is sacred. You cannot ninja-edit a released part or slip a rogue bolt into a released
    <a href="https://en.wikipedia.org/wiki/Bill_of_materials">Bill of Materials (BOM)</a>. Every new item, part revision,
    BOM markup, and drawing check-in must be tied to an active <b>OPEN</b>
    <a href="https://en.wikipedia.org/wiki/Engineering_change_order">Engineering Change Order (ECO)</a>.
    Until that ECO passes all pre-flight gates and is officially <b>RELEASED</b> in Tab 5, your edits remain safely staged
    as <span class="code-pill">PENDING_ECO</span>.
</p>

<h2>3. Role-Based Access Control (RBAC) &amp; Button Color Coding</h2>
<p>
    hBOM uses <a href="https://en.wikipedia.org/wiki/Role-based_access_control">Role-Based Access Control (RBAC)</a>.
    Throughout the entire interface, buttons are color-coded by the minimum security role required to press them:
</p>
<table class="ref-table">
    <tr>
        <th width="22%">Security Role</th>
        <th width="20%">Button Color</th>
        <th>Authority &amp; Capabilities</th>
    </tr>
    <tr>
        <td class="field-name">VIEWER (Read-Only)</td>
        <td><span class="btn-slate">Slate Gray</span></td>
        <td>Can search catalogs, explode indented BOMs (Tab 7), run Where-Used traces (Tab 8), compare BOMs (Tab 9), view vault PDFs (Tab 10), and export CSV/PDF reports.</td>
    </tr>
    <tr>
        <td class="field-name">DESIGNER (Create/Modify)</td>
        <td><span class="btn-blue">Royal Blue</span></td>
        <td>All Viewer permissions <b>PLUS</b> authority to create/modify 3PR, 2AS, and 1AF items, stage BOM markups (Tab 4), submit ECR requests, attach ECO files, and register CAD drawings (Tab 6).</td>
    </tr>
    <tr>
        <td class="field-name">APPROVER (Sign-Off)</td>
        <td><span class="btn-green">Emerald Green</span></td>
        <td>All Designer permissions <b>PLUS</b> authority to pull official Open ECOs directly, approve ECR requests, approve Pending ECOs, reject ECOs back to Open, and release ECOs to production.</td>
    </tr>
    <tr>
        <td class="field-name">ADMIN (Full Access)</td>
        <td><span class="btn-purple">Royal Purple</span></td>
        <td>Unrestricted system control across all 12 tabs, including <b>Tab 11 (Settings)</b> and <b>Tab 12 (User Administration)</b>.</td>
    </tr>
</table>

<h2>4. Global Header Bar Controls</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Header Control</th>
        <th>What It Does</th>
    </tr>
    <tr>
        <td class="field-name">Active User Badge</td>
        <td>Displays your currently authenticated Full Name and active RBAC Role (e.g., <span class="code-pill">Active User: System Administrator [ADMIN]</span>).</td>
    </tr>
    <tr>
        <td class="field-name">[Refresh All Data]</td>
        <td>Instantly reloads all dropdown metadata (Nouns, Materials, Open ECOs) and refreshes the active ECO workspace without dumping your search tables.</td>
    </tr>
    <tr>
        <td class="field-name">[Switch User / Logout]</td>
        <td>Opens the authentication login dialog so you can switch accounts on the fly (handy for testing Designer vs. Approver workflows!).</td>
    </tr>
    <tr>
        <td class="field-name">[? Help &amp; Process Flowchart]</td>
        <td>Opens this interactive manual directly to the chapter for the tab you are currently viewing.</td>
    </tr>
</table>
""",

    "01. Tab 1: Product Setup (3PR)": """
<h1>01. Tab 1: Product Setup (Top-Level 3PR Configurations)</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 3 (Item Authoring)</b>. A <span class="code-pill">3PR</span>
    record represents the top of the food chain—a complete, shippable product, machine, or attachment kit that goes out the door
    to a customer.
</div>

<h2>Step-by-Step Directions: Creating or Modifying a 3PR Product</h2>
<ol>
    <li><span class="step-num">Step 1 — Pick Your Mode:</span> In Panel 1, select <b>Add New</b> to mint a brand-new <span class="code-pill">3PR</span> number, select <b>Modify Existing</b> to stage a revision on an existing product, or click <span class="btn-blue">Clone Existing...</span> to copy specs from a similar product into Add New mode.</li>
    <li><span class="step-num">Step 2 — Check Your Number Seed:</span> When adding a new product, verify the <b>Starting Code Seed</b> (defaults to <span class="code-pill">3PR00000000</span>). The green <b>Next PN</b> label previews the exact number that will be assigned.</li>
    <li><span class="step-num">Step 3 — Assign Standardized Nomenclature:</span> Select an approved root noun from the <b>Noun, Description</b> dropdown (or click <span class="btn-blue">Noun DB...</span> to register a new one) and type the specific product description after the comma (e.g., <span class="code-pill">LOADER ATTACHMENT, 8-Foot Compact Tractor Backhoe Kit</span>).</li>
    <li><span class="step-num">Step 4 — Set Physical &amp; Lifecycle Specs:</span> In Panel 2, select <b>Finish</b>, <b>Dwg Size</b>, <b>Envelope (LXWXH)</b>, <b>Wt</b> (Unit Weight), <b>Src</b> (<span class="code-pill">MAKE</span> or <span class="code-pill">BUY</span>), and <b>Rev</b>. Check <b>Prototype</b> if this is an experimental numeric-revision build (<span class="code-pill">Rev 1, 2...</span>).</li>
    <li><span class="step-num">Step 5 — Tie to an Open ECO &amp; Save:</span> Select your governing Open ECO in <b>Tied to Open ECO</b> (or click <span class="btn-blue">Pull ECO #...</span> if you need one) and click <span class="btn-blue">Save New Product (Pending ECO)</span>.</li>
</ol>

<div class="tip-box">
    <b>💡 Fast-Edit Shortcut:</b> Don't waste time typing part numbers into the Modify box! Search the bottom
    <b>PRODUCT Catalog</b> table and <b>double-click any row</b>—hBOM automatically switches to <i>Modify Existing</i> mode
    and loads every field for that product into the top form.
</div>

<h2>Complete Field &amp; Button Reference (Tab 1)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th width="16%">Panel</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Workflow Mode (Add / Modify)</td>
        <td>Panel 1 (Left)</td>
        <td>Toggles the form between creating a new <span class="code-pill">3PR</span> number and staging a <span class="code-pill">PartPendingUpdate</span> revision on an existing product.</td>
    </tr>
    <tr>
        <td class="field-name">[Clone Existing...]</td>
        <td>Panel 1 (Left)</td>
        <td>Opens the Wildcard Search popup so you can pick an existing product and copy all of its attributes into a new <span class="code-pill">3PR</span> setup form.</td>
    </tr>
    <tr>
        <td class="field-name">Starting Code Seed &amp; Next PN</td>
        <td>Panel 1 (Left)</td>
        <td>Defines the prefix and digit length (default <span class="code-pill">3PR00000000</span>). Live preview shows the next sequential number available in the database.</td>
    </tr>
    <tr>
        <td class="field-name">Target Number (Modify) &amp; [Find...]</td>
        <td>Panel 1 (Left)</td>
        <td>Active only in <i>Modify Existing</i> mode. Enter a <span class="code-pill">3PR</span> number and press <span class="code-pill">Enter</span>, or click <span class="btn-slate">Find...</span> to search.</td>
    </tr>
    <tr>
        <td class="field-name">Noun, Description &amp; [Noun DB...]</td>
        <td>Panel 1 (Left)</td>
        <td>Enforces military/industrial catalog naming (<a href="https://en.wikipedia.org/wiki/NATO_Stock_Number#Item_name">APPROVED NOUN, Modifier Description</a>). Click <span class="btn-blue">Noun DB...</span> to manage the Master Noun Dictionary.</td>
    </tr>
    <tr>
        <td class="field-name">Material [Optional] &amp; [Mat DB...]</td>
        <td>Panel 1 (Left)</td>
        <td>Optional for top-level <span class="code-pill">3PR</span> products (since material is typically specified on piece parts). Click <span class="btn-blue">Mat DB...</span> to open the Master Materials Database.</td>
    </tr>
    <tr>
        <td class="field-name">Material Size (Stock)</td>
        <td>Panel 1 (Left)</td>
        <td>Optional stock or kit description for the top-level product (e.g., <span class="code-pill">System Kit</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Finish &amp; Dwg Size</td>
        <td>Panel 2 (Right)</td>
        <td>Select surface coat (<span class="code-pill">PAINTED</span>, <span class="code-pill">RAW</span>, <span class="code-pill">PLATED</span>, <span class="code-pill">N/A</span>) and <a href="https://en.wikipedia.org/wiki/Engineering_drawing#Size">drawing sheet format</a> (<span class="code-pill">A0–A4</span>, <span class="code-pill">A–E</span>, or <span class="code-pill">NONE</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Envelope (LXWXH), Wt &amp; Src</td>
        <td>Panel 2 (Right)</td>
        <td>Overall bounding box dimensions (e.g., <span class="code-pill">2300X1600X1800</span>), unit mass, and procurement source (<span class="code-pill">MAKE</span>, <span class="code-pill">BUY</span>, or <span class="code-pill">PHANTOM</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Unit of Measure</td>
        <td>Panel 2 (Right)</td>
        <td>Permanently locked to <span class="code-pill">1 EA</span> for top-level products and subassemblies.</td>
    </tr>
    <tr>
        <td class="field-name">Lifecycle &amp; Revision</td>
        <td>Panel 2 (Right)</td>
        <td>Leave <b>Prototype</b> unchecked for production alpha revisions (<span class="code-pill">A, B, C</span>); check it for prototype numeric revisions (<span class="code-pill">1, 2, 3</span>) per <a href="https://en.wikipedia.org/wiki/Engineering_drawing">ASME Y14.35</a>.</td>
    </tr>
    <tr>
        <td class="field-name">Tied to Open ECO &amp; [Pull ECO #...]</td>
        <td>Panel 2 (Right)</td>
        <td>Selects the authorizing <span class="code-pill">OPEN</span> ECO. Click <span class="btn-blue">Pull ECO #...</span> to request or pull a new ECO without leaving Tab 1.</td>
    </tr>
    <tr>
        <td class="field-name">[Save New Product / Modification]</td>
        <td>Panel 2 (Right)</td>
        <td>Validates all inputs and commits the new product (or staged revision) to the database under <span class="code-pill">PENDING_ECO</span> status.</td>
    </tr>
    <tr>
        <td class="field-name">Wildcard Search, [Search], [Show All], [Clear], [Export CSV...]</td>
        <td>Bottom Catalog</td>
        <td>Filter the <span class="code-pill">3PR</span> catalog using <span class="code-pill">*</span> or <span class="code-pill">?</span> wildcards, display all products, clear the table, or export the grid to CSV.</td>
    </tr>
</table>
""",

    "02. Tab 2: Prod Subassembly (2AS)": """
<h1>02. Tab 2: Production Subassembly Setup (2AS Modules &amp; Options)</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 3 (Item Authoring)</b>. <span class="code-pill">2AS</span>
    Production Subassemblies are the middleweight champions of your BOM—welded sub-frames, hydraulic valve packages, and
    configurable option modules that plug into top-level <span class="code-pill">3PR</span> products.
</div>

<h2>Understanding Phantom Subassemblies &amp; 3-Digit Condition Codes</h2>
<p>
    Tab 2 introduces two powerhouse manufacturing concepts that keep your top-level BOMs clean and modular:
</p>
<ul>
    <li>
        <b><a href="https://en.wikipedia.org/wiki/Materials_management">Phantom Assemblies</a> (<span class="code-pill">Src = PHANTOM</span>):</b>
        A logical grouping of parts (like a <i>Final Assembly Hardware &amp; Service Group</i>) that engineering manages as a reusable
        bundle, even though the shop floor installs those bolts directly onto the main machine without stocking a separate sub-kit on the shelf.
    </li>
    <li>
        <b><a href="https://en.wikipedia.org/wiki/Modular_bill_of_materials">3-Digit Condition Codes</a> (<span class="code-pill">3-Digit Cond</span>):</b>
        A 3-character alphanumeric tag (such as <span class="code-pill">B01</span> for a 12-Inch Bucket, <span class="code-pill">B04</span> for a 24-Inch Bucket,
        <span class="code-pill">V03</span> for a 4-Spool Joystick Valve, or <span class="code-pill">P02</span> for 425 Kuro Metallic Black Trim).
        When you explode or compare BOMs in Tabs 7 and 9, you can filter by Condition Code to isolate a specific machine configuration!
    </li>
</ul>

<h2>Step-by-Step Directions: Creating or Modifying a 2AS Subassembly</h2>
<ol>
    <li><span class="step-num">Step 1 — Choose Workflow Mode:</span> Select <b>Add New</b>, <b>Modify Existing</b>, or click <span class="btn-blue">Clone Existing...</span>. Verify the <span class="code-pill">2AS00000000</span> seed.</li>
    <li><span class="step-num">Step 2 — Enter Noun &amp; Description:</span> Select an approved Noun (e.g., <span class="code-pill">SUBASSEMBLY</span> or <span class="code-pill">WELDMENT</span>) and enter the specific module description after the comma.</li>
    <li><span class="step-num">Step 3 — Assign 3-Digit Condition Code:</span> In Panel 2 next to <b>Dwg Size</b>, enter a 3-character <b>3-Digit Cond</b> code (e.g., <span class="code-pill">B01</span>, <span class="code-pill">M03</span>, <span class="code-pill">F01</span>) if this subassembly represents a configurable module.</li>
    <li><span class="step-num">Step 4 — Set Source &amp; Specs:</span> Choose <span class="code-pill">PHANTOM</span>, <span class="code-pill">MAKE</span>, or <span class="code-pill">BUY</span> in <b>Src</b>, enter <b>Envelope (LXWXH)</b> and <b>Wt</b>, and pick your <b>Tied to Open ECO</b>.</li>
    <li><span class="step-num">Step 5 — Save Subassembly:</span> Click <span class="btn-blue">Save New Production Subassembly (Pending ECO)</span>. Next, head to <b>Tab 4 (BOM Builder)</b> to hang child parts on your new <span class="code-pill">2AS</span> module!</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 2)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th width="16%">Panel</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Workflow Mode &amp; [Clone Existing...]</td>
        <td>Panel 1 (Left)</td>
        <td>Switch between creating a new <span class="code-pill">2AS</span> subassembly, modifying an existing one, or cloning an existing module.</td>
    </tr>
    <tr>
        <td class="field-name">Starting Code Seed</td>
        <td>Panel 1 (Left)</td>
        <td>Defaults to <span class="code-pill">2AS00000000</span> with real-time <span class="code-pill">Next PN</span> sequence preview.</td>
    </tr>
    <tr>
        <td class="field-name">3-Digit Cond</td>
        <td>Panel 2 (Right)</td>
        <td><b>Unique to Tab 2:</b> 3-character option/group identifier (e.g., <span class="code-pill">B01</span>, <span class="code-pill">V01</span>, <span class="code-pill">P02</span>, <span class="code-pill">K01</span>) used for variant BOM filtering.</td>
    </tr>
    <tr>
        <td class="field-name">Src (MAKE / BUY / PHANTOM)</td>
        <td>Panel 2 (Right)</td>
        <td>Defaults to <span class="code-pill">PHANTOM</span> on Tab 2. Switch to <span class="code-pill">MAKE</span> for stocked in-house subassemblies or <span class="code-pill">BUY</span> for turnkey vendor assemblies.</td>
    </tr>
    <tr>
        <td class="field-name">All Other Fields &amp; Catalog Controls</td>
        <td>Both Panels</td>
        <td>Identical to Tab 1 (<span class="btn-blue">Noun DB...</span>, <span class="btn-blue">Mat DB...</span>, <span class="btn-blue">Pull ECO #...</span>, Wildcard Search, double-click row to modify, and <span class="btn-slate">Export CSV...</span>).</td>
    </tr>
</table>
""",

    "03. Tab 3: Part Setup (1AF Piece Parts & Bulk)": """
<h1>03. Tab 3: Part Setup (1AF Piece Parts &amp; Bulk Consumables)</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 3 (Item Authoring)</b>. <span class="code-pill">1AF</span>
    is where the rubber (and AR400 wear plate) meets the road. Every laser-cut bracket, machined 4140 pivot pin, hydraulic cylinder,
    Grade 10.9 fastener, and shop consumable lives here.
</div>

<h2>Discrete Piece Parts vs. Bulk Consumables</h2>
<ul>
    <li>
        <b>Discrete Piece Parts (Bulk Unchecked):</b> Counted in whole or integer quantities with Unit of Measure locked to
        <span class="code-pill">EA</span> (Each).
    </li>
    <li>
        <b>Bulk Consumables (Bulk Checked):</b> Items like hydraulic oil, Loctite threadlocker, lithium grease, spiral hose wrap,
        or wire loom that are consumed in fractional or continuous units of measure (<a href="https://en.wikipedia.org/wiki/Unit_of_measurement">UOM</a>):
        <span class="code-pill">ML</span>, <span class="code-pill">L</span>, <span class="code-pill">OZ</span>, <span class="code-pill">GAL</span>,
        <span class="code-pill">MM</span>, <span class="code-pill">M</span>, <span class="code-pill">IN</span>, <span class="code-pill">FT</span>,
        <span class="code-pill">G</span>, <span class="code-pill">KG</span>, <span class="code-pill">LB</span>, or <span class="code-pill">AR</span> (As Required).
    </li>
</ul>

<h2>Step-by-Step Directions: Creating or Modifying a 1AF Part</h2>
<ol>
    <li><span class="step-num">Step 1 — Select Mode &amp; Seed:</span> Choose <b>Add New</b>, <b>Modify Existing</b>, or <span class="btn-blue">Clone Existing...</span>. Verify the <span class="code-pill">1AF00000000</span> starting seed.</li>
    <li><span class="step-num">Step 2 — Enter Noun, Description:</span> Pick an approved Noun (e.g., <span class="code-pill">PIN</span>, <span class="code-pill">PLATE</span>, <span class="code-pill">CYLINDER</span>, <span class="code-pill">SCREW</span>) and type the detailed part description after the comma.</li>
    <li><span class="step-num">Step 3 — Select Material &amp; Stock Size (Required!):</span> Unlike assemblies, <b>Material (Required)</b> is mandatory for <span class="code-pill">1AF</span> parts. Pick an approved material from the dropdown (or click <span class="btn-blue">Mat DB...</span> to add one) and enter the raw cut/purchase dimensions in <b>Material Size (Stock)</b> (e.g., <span class="code-pill">40mm Dia 4140 Bar</span>).</li>
    <li><span class="step-num">Step 4 — Configure Finish, Envelope, Weight &amp; UOM:</span> In Panel 2, set <b>Finish</b>, <b>Dwg Size</b>, <b>Envelope (LXWXH)</b>, <b>Wt</b>, and <b>Src</b> (<span class="code-pill">MAKE</span> or <span class="code-pill">BUY</span>). If registering a fluid, adhesive, or bulk item, check <b>Bulk item (Oil, Loctite, Tape)</b> and choose its UOM.</li>
    <li><span class="step-num">Step 5 — Select Open ECO &amp; Save:</span> Choose your active Open ECO and click <span class="btn-blue">Save New Part (Pending ECO)</span>.</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 3)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th width="16%">Panel</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Material (Required) &amp; [Mat DB...]</td>
        <td>Panel 1 (Left)</td>
        <td><b>Strictly required for 1AF parts.</b> Links the part to a governed material specification (e.g., <span class="code-pill">Steel Grade 50 / ASTM A572 Gr 50</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Material Size (Stock)</td>
        <td>Panel 1 (Left)</td>
        <td>Specifies raw stock dimensions or vendor package size (e.g., <span class="code-pill">12x150x230mm Gr50</span> or <span class="code-pill">50mL Bottle</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Bulk item Checkbox &amp; UOM</td>
        <td>Panel 2 (Right)</td>
        <td><b>Unique to Tab 3:</b> Unlocks the UOM dropdown so bulk consumables can be measured in <span class="code-pill">ML</span>, <span class="code-pill">L</span>, <span class="code-pill">OZ</span>, <span class="code-pill">GAL</span>, <span class="code-pill">FT</span>, <span class="code-pill">M</span>, <span class="code-pill">KG</span>, <span class="code-pill">LB</span>, etc. (Filtered by your Metric/Inch preference in Tab 11).</td>
    </tr>
    <tr>
        <td class="field-name">[Noun DB...] &amp; [Mat DB...] Popups</td>
        <td>Panel 1 (Left)</td>
        <td>Both database popups let you search existing dictionary entries, export them to CSV, register new approved Nouns/Materials, or <b>double-click any row</b> to insert it straight into your form.</td>
    </tr>
</table>
""",

    "04. Tab 4: BOM Builder (Markup Staging)": """
<h1>04. Tab 4: BOM Builder &amp; Markup Manager</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 4 (BOM &amp; Vault)</b>. Now that your <span class="code-pill">3PR</span>
    products, <span class="code-pill">2AS</span> subassemblies, and <span class="code-pill">1AF</span> piece parts exist, Tab 4 is where
    you bolt them together into a single-level parent-child <a href="https://en.wikipedia.org/wiki/Bill_of_materials">Bill of Materials</a>.
</div>

<h2>Built-In BOM Architecture Guardrails</h2>
<ul>
    <li><b>No Piece-Part Parents:</b> A <span class="code-pill">1AF</span> piece part cannot be a Parent Assembly. Only <span class="code-pill">3PR</span> and <span class="code-pill">2AS</span> items can have child BOM rows.</li>
    <li><b>No Self-Referencing Loops:</b> An assembly is blocked from containing itself as a child component.</li>
    <li><b>Smart Duplicate Incrementing:</b> Double-clicking a part in the left catalog that is <i>already</i> in the right BOM table automatically increments its quantity by <span class="code-pill">+1.0</span> instead of creating a messy duplicate row!</li>
</ul>

<h2>Step-by-Step Directions: Staging a BOM Markup</h2>
<ol>
    <li><span class="step-num">Step 1 — Load the Parent Assembly:</span> On the right side, type a <span class="code-pill">3PR</span> or <span class="code-pill">2AS</span> number into <b>Parent Assembly PN</b> (or click <span class="btn-slate">Find...</span>) and click <span class="btn-slate">Load BOM</span>.</li>
    <li><span class="step-num">Step 2 — Search &amp; Add Child Components:</span> On the left side (<b>Master Part Catalog</b>), enter a wildcard query (e.g., <span class="code-pill">1AF*</span> or <span class="code-pill">*BOLT*</span>) and click <span class="btn-slate">Search</span>. <b>Double-click any catalog row</b> to add it to the Active Assembly BOM on the right.</li>
    <li><span class="step-num">Step 3 — Edit Find #, Quantity, Condition &amp; Supply Class:</span> In the right-hand <b>Active Assembly BOM Structure</b> table, <b>double-click any BOM line item</b> to open the <i>Edit BOM Line Item</i> popup. Adjust the drawing balloon <b>Find Number</b> (10, 20, 30...), <b>Quantity</b>, <b>Condition Code</b>, or <b>Supply Class</b> and click <span class="btn-blue">Apply</span>.</li>
    <li><span class="step-num">Step 4 — Sequence or Prune Rows:</span> Highlight any row and use <span class="btn-blue">Move Up</span>, <span class="btn-blue">Move Down</span>, or <span class="btn-blue">Remove Selected Child</span>.</li>
    <li><span class="step-num">Step 5 — Commit Markups to an Open ECO:</span> At the bottom-right, choose your governing Open ECO in <b>Select Open ECO</b> and click <span class="btn-blue">SAVE BOM MARKUPS TO ECO</span>.</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 4)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th width="16%">Panel</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Master Part Catalog Search Bar</td>
        <td>Left Panel</td>
        <td>Search parts/subassemblies via <span class="btn-slate">Search</span>, <span class="btn-slate">Show All</span>, or <span class="btn-slate">Clear</span>. Double-click any row to insert it into the active BOM.</td>
    </tr>
    <tr>
        <td class="field-name">Parent Assembly PN, [Find...], [Load BOM]</td>
        <td>Right Panel (Top)</td>
        <td>Loads the current BOM structure for a <span class="code-pill">3PR</span> or <span class="code-pill">2AS</span> parent (automatically loading staged <span class="code-pill">PENDING_ECO</span> rows if an active markup already exists).</td>
    </tr>
    <tr>
        <td class="field-name">Active Assembly BOM Structure Table</td>
        <td>Right Panel</td>
        <td>Displays <b>Find #</b>, <b>Child PN</b>, <b>Description</b>, <b>Qty</b>, <b>UOM</b>, <b>Cond</b>, <b>Supply Class</b> (<span class="code-pill">AVAILABLE</span> vs. <span class="code-pill">NOT AVAILABLE</span> for welded sub-details), and <b>BOM Status</b>. Double-click any row to edit.</td>
    </tr>
    <tr>
        <td class="field-name">[Remove Selected Child], [Move Up], [Move Down]</td>
        <td>Right Panel</td>
        <td>Removes a component line or reorders lines in the working BOM table prior to saving.</td>
    </tr>
    <tr>
        <td class="field-name">Select Open ECO &amp; [SAVE BOM MARKUPS TO ECO]</td>
        <td>Right Panel (Bottom)</td>
        <td>Stages the entire working BOM table under the chosen Open ECO. When that ECO is later released in Tab 5, these staged rows supersede the old released BOM.</td>
    </tr>
</table>
""",

    "05. Tab 5: ECO Manager & Graphical Approval Center": """
<h1>05. Tab 5: ECO Manager &amp; Graphical Approval Center</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> Tab 5 is Mission Control! It anchors <b>Stage 2 (ECO / ECR Initiation)</b> when starting
    a change, and <b>Stage 6 (Workflow Approval &amp; Release)</b> when promoting staged work to production. Better yet, its
    <a href="https://en.wikipedia.org/wiki/Engineering_change_order">Engineering Change Order</a> Master Log auto-loads at startup.
</div>

<h2>Step-by-Step Directions: Running an ECO from Start to Release</h2>
<ol>
    <li><span class="step-num">Step 1 — Pull or Request an ECO:</span> In Panel 2 (bottom-left), pick <span class="code-pill">PRODUCTION</span> or <span class="code-pill">PROTOTYPE</span> and click <span class="btn-blue">1. Pull / Request ECO</span>.
        <ul>
            <li>If you are signed in as an <b>APPROVER</b> or <b>ADMIN</b>, hBOM immediately issues an editable <span class="code-pill">OPEN</span> ECO number (<span class="code-pill">ECO-xxxxxx</span> or <span class="code-pill">PECO-xxxxxx</span>).</li>
            <li>If you are signed in as a <b>DESIGNER</b>, hBOM logs an Engineering Change Request (<span class="code-pill">ECR-xxxxxx</span>) in <span class="code-pill">REQUESTED</span> status awaiting Approver sign-off.</li>
        </ul>
    </li>
    <li><span class="step-num">Step 2 — Document Title &amp; Engineering Reason:</span> Enter a clear headline in <b>Active ECO &amp; Title</b>, type the detailed justification in <b>Detailed Change Info &amp; Engineering Reason</b>, and click <span class="btn-blue">Save Info</span>.</li>
    <li><span class="step-num">Step 3 — Curate Deliverables (Right Column):</span> Use the <b>Deliverables View</b> switcher bar on the right:
        <ul>
            <li>Click <span class="btn-slate">📋 1. Smart Drawing Checklist</span> to see drawings auto-detected from your part and BOM markups. Click column 1 to toggle <span class="code-pill">[✓]</span> and click <span class="btn-blue">Apply Checked [✓] Drawings to ECO</span>.</li>
            <li>Click <span class="btn-blue">📎 2. Registered Drawings &amp; Attachments</span> to attach supporting PDFs/calculations or double-click a required drawing row to jump straight to <b>Tab 6</b> for vault registration.</li>
        </ul>
    </li>
    <li><span class="step-num">Step 4 — Open the Graphical Workflow &amp; Approval Center:</span> Double-click any row in the top <b>Master Log</b> (or click <span class="btn-blue">❖ Manage Workflow / Approvals...</span>). Inspect the 5-stage visual flowchart and the 3 Pre-Flight Gates:
        <ul>
            <li><b>Gate 1:</b> Title &amp; Engineering Reason populated.</li>
            <li><b>Gate 2:</b> Staged Engineering Changes (New Parts, Modified Parts, BOM Markups, Attachments).</li>
            <li><b>Gate 3:</b> Required Drawings registered in Tab 6 (<span class="code-pill">X/X Registered</span>).</li>
        </ul>
    </li>
    <li><span class="step-num">Step 5 — Transition &amp; Release:</span> Use the role-filtered action buttons at the bottom of the Flowchart Center to <b>Approve Request</b>, <b>Submit ECO for Approval</b>, <b>Approve ECO</b> (or <b>Reject / Return to Open</b>), and finally <b>Release Approved ECO to Production</b>!</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 5)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th width="18%">Location</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">ECO Master Log Table</td>
        <td>Panel 1 (Top Full-Width)</td>
        <td>Displays all ECOs/ECRs with live counts of <b>New #s</b>, <b>Mod #s</b>, <b>BOM Rows</b>, and <b>Dwg Reg List</b> progress. Click once to load into the lower workspace; <b>double-click</b> to launch the Graphical Workflow Flowchart.</td>
    </tr>
    <tr>
        <td class="field-name">[Export PDF...] &amp; [Export CSV...]</td>
        <td>Panel 1 (Top Bar)</td>
        <td>Generates a formatted multi-table PDF Engineering Change Traveler package or exports the Master Log grid to CSV.</td>
    </tr>
    <tr>
        <td class="field-name">Pull New ECO, Seed &amp; [1. Pull / Request ECO]</td>
        <td>Panel 2 (Bottom-Left)</td>
        <td>Selects <span class="code-pill">PRODUCTION</span> (<span class="code-pill">ECO-000000</span>) or <span class="code-pill">PROTOTYPE</span> (<span class="code-pill">PECO-000000</span>) sequence and issues a new change record.</td>
    </tr>
    <tr>
        <td class="field-name">[Save Info] &amp; [Summary Report / PDF...]</td>
        <td>Panel 2 (Bottom-Left)</td>
        <td>Saves Title/Reason edits or opens the standalone full-screen color-coded ECO Summary Report modal.</td>
    </tr>
    <tr>
        <td class="field-name">[❖ Manage Workflow / Approvals...] &amp; Status Badge</td>
        <td>Panel 2 (Bottom-Left)</td>
        <td>Launches the Graphical ECO Workflow &amp; Approval Center dialog and displays a live color-coded status badge (<span class="code-pill">● ECO-xxxxxx: STATUS</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Live ECO Summary Report Preview</td>
        <td>Panel 3 (Lower-Left)</td>
        <td>Real-time redline diff preview highlighting added items in <span style="color:#4ADE80;font-weight:bold;">green (+)</span>, removed items in <span style="color:#F87171;font-weight:bold;">red (-)</span>, and modified fields in <span style="color:#60A5FA;font-weight:bold;">blue (~)</span>.</td>
    </tr>
    <tr>
        <td class="field-name">Deliverables View Switcher ([📋 1], [📎 2], [⊞ Split])</td>
        <td>Right Column Header</td>
        <td>Switches the right-hand workspace between the <b>Smart Drawing Checklist</b>, <b>Registered Drawings &amp; Attachments</b>, or a stacked <b>Split View</b> of both.</td>
    </tr>
    <tr>
        <td class="field-name">[Browse...], [Attach], [Remove File], [Open File / Go to Dwg Reg]</td>
        <td>Right Column (Attachments)</td>
        <td>Attaches reference documents (with SHA-256 hashing) to an Open ECO, removes attachments, opens attached files externally, or jumps to Tab 6 with a required drawing pre-loaded.</td>
    </tr>
</table>
""",

    "06. Tab 6: Drawing Registration (Vault Check-In)": """
<h1>06. Tab 6: Drawing Registration Vault</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 4 (BOM &amp; Vault)</b>. Before an ECO with required drawings can pass
    <b>Gate 3</b> and be released to production, its controlled PDF engineering drawings must be checked into the vault here.
</div>

<h2>Three Engineering Drawing Modes (<a href="https://en.wikipedia.org/wiki/ASME_Y14.24">ASME Y14.24</a>)</h2>
<ul>
    <li><span class="code-pill">SINGLE</span> — Standard mono-detail or assembly drawing governing one primary Part Number (<span class="code-pill">STD</span>).</li>
    <li><span class="code-pill">LH/RH PAIR</span> — Symmetrical opposite-hand drawing governing both a Left-Hand (<span class="code-pill">LH</span>) part number and a Right-Hand (<span class="code-pill">RH</span>) part number on the same sheet.</li>
    <li><span class="code-pill">TABULATED</span> — Family/tabulated drawing (such as multi-color painted shields or shim packs) where a single drawing governs multiple part numbers via a configuration table.</li>
</ul>

<h2>Step-by-Step Directions: Registering a Drawing</h2>
<ol>
    <li><span class="step-num">Step 1 — Pre-Fill from the Checklist (Fastest Way!):</span> In the bottom <b>ECO Drawing Registration Checklist</b>, click <span class="btn-slate">Show All</span> (or search by ECO #) and <b>double-click any <span style="color:#F59E0B;">PENDING REGISTRATION</span> row</b>. That automatically populates the Drawing Number, Mode, Governing ECO #, and Primary Part # in the top form!</li>
    <li><span class="step-num">Step 2 — Verify Drawing Mode &amp; Linked Parts:</span> If registering manually, enter <b>Drawing Number</b>, choose <b>Drawing Mode</b> (<span class="code-pill">SINGLE</span>, <span class="code-pill">LH/RH PAIR</span>, or <span class="code-pill">TABULATED</span>), select <b>Governing ECO #</b>, and enter <b>Linked Part # 1</b> (plus <b>Linked Part # 2</b> if <span class="code-pill">LH/RH PAIR</span>).</li>
    <li><span class="step-num">Step 3 — Select the PDF Drawing File:</span> Click <span class="btn-blue">Browse...</span> and pick your exported CAD PDF file. hBOM automatically inspects the PDF header to count the number of sheets.</li>
    <li><span class="step-num">Step 4 — Check Into the Vault:</span> Click <span class="btn-blue">Register Drawing</span>. hBOM copies the file into the managed vault directory, computes an immutable <a href="https://en.wikipedia.org/wiki/SHA-2">SHA-256 cryptographic checksum</a>, logs the revision history, and flips the ECO checklist item to <span style="color:#4ADE80;font-weight:bold;">REGISTERED</span>!</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 6)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th width="16%">Panel</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Drawing Number &amp; Drawing Mode</td>
        <td>Top Panel</td>
        <td>Identifier for the drawing (e.g., <span class="code-pill">DWG-LHRH-EAR-01</span>) and mode (<span class="code-pill">SINGLE</span>, <span class="code-pill">LH/RH PAIR</span>, <span class="code-pill">TABULATED</span>). Selecting <span class="code-pill">LH/RH PAIR</span> dynamically reveals the second Linked Part # field.</td>
    </tr>
    <tr>
        <td class="field-name">Governing ECO #</td>
        <td>Top Panel</td>
        <td>Selects the active <span class="code-pill">OPEN</span> ECO authorizing this drawing registration.</td>
    </tr>
    <tr>
        <td class="field-name">Linked Part # 1 &amp; Linked Part # 2 + [Find...]</td>
        <td>Top Panel</td>
        <td>Maps the drawing to the governed part record(s) in the database.</td>
    </tr>
    <tr>
        <td class="field-name">Drawing File Path (PDF), [Browse...], [Register Drawing]</td>
        <td>Top Panel</td>
        <td>Selects the local PDF file, auto-detects page count, archives it into the vault, and satisfies ECO Gate 3.</td>
    </tr>
    <tr>
        <td class="field-name">ECO Drawing Registration Checklist</td>
        <td>Bottom Panel</td>
        <td>Searchable table of all required ECO drawings showing <span style="color:#4ADE80;font-weight:bold;">REGISTERED</span> vs. <span style="color:#F59E0B;font-weight:bold;">PENDING REGISTRATION</span> status. Double-click any row to load it into the top form.</td>
    </tr>
</table>
""",

    "07. Tab 7: BOM Lookup (Multi-Level Indented Tree)": """
<h1>07. Tab 7: Indented BOM Lookup Explorer</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 5 (Verify &amp; Audit)</b>. Tab 7 explodes any top-level
    <span class="code-pill">3PR</span> product or <span class="code-pill">2AS</span> subassembly into a complete
    <a href="https://en.wikipedia.org/wiki/Bill_of_materials#Indented_bill_of_materials">Multi-Level Indented BOM</a> with
    extended quantity and mass rollups.
</div>

<h2>Step-by-Step Directions: Exploding a BOM Tree</h2>
<ol>
    <li><span class="step-num">Step 1 — Select Root Assembly:</span> Enter a <span class="code-pill">3PR</span> or <span class="code-pill">2AS</span> part number (wildcards like <span class="code-pill">3PR*5</span> are supported!) or click <span class="btn-slate">Find...</span>.</li>
    <li><span class="step-num">Step 2 — Choose Explosion Depth:</span> Select <b>Full Multi-Level</b> to recursively drill down through every subassembly tier (<span class="code-pill">Level 0 &rarr; Level 1 &rarr; Level 2...</span>), or <b>Single-Level Only</b> to view only immediate children.</li>
    <li><span class="step-num">Step 3 — Set Pending ECO &amp; Condition Filters:</span>
        <ul>
            <li>Check <b>Pending ECOs</b> if you want to preview how uncommitted <span class="code-pill">PENDING_ECO</span> markups will look once released.</li>
            <li>Enter a 3-digit code in <b>Cond Filter</b> (e.g., <span class="code-pill">B04</span> or <span class="code-pill">V02</span>) to filter configurable subassemblies.</li>
        </ul>
    </li>
    <li><span class="step-num">Step 4 — Explode &amp; Export:</span> Click <span class="btn-slate">Explode BOM Tree</span> to populate the hierarchy table, and click <span class="btn-slate">Export CSV...</span> to save a purchasing/manufacturing packet.</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 7)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Part / Assembly PN &amp; [Find...]</td>
        <td>Target parent assembly to explode. Entering a wildcard pattern automatically opens the Part Search dialog if multiple matches exist.</td>
    </tr>
    <tr>
        <td class="field-name">Full Multi-Level / Single-Level Only</td>
        <td>Radio buttons controlling whether the BOM explosion stops at Level 1 or recurses all the way down to raw piece parts.</td>
    </tr>
    <tr>
        <td class="field-name">Pending ECOs (Checkbox)</td>
        <td>Toggles instantly between the official <b>RELEASED</b> production baseline and a redline preview that includes staged <b>PENDING_ECO</b> BOM markups.</td>
    </tr>
    <tr>
        <td class="field-name">Cond Filter</td>
        <td>Filters Level-1 option modules by their 3-digit Condition Code (while always retaining core <span class="code-pill">F01</span>/<span class="code-pill">K01</span> base frame/hardware groups).</td>
    </tr>
    <tr>
        <td class="field-name">[Explode BOM Tree] &amp; [Export CSV...]</td>
        <td>Computes tree hierarchy, <b>Ext Qty</b> (Parent Qty &times; Child Qty), <b>Unit Wt</b>, and <b>Ext Wt</b>, and exports the full indented structure to CSV.</td>
    </tr>
</table>
""",

    "08. Tab 8: Where-Used (Upward Impact Analysis)": """
<h1>08. Tab 8: Where-Used Inquiry Trace</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 5 (Verify &amp; Audit)</b>. Before you thicken a bracket or swap a
    hydraulic fitting thread, you need to know what else it might break! Tab 8 performs a bottom-up
    <a href="https://en.wikipedia.org/wiki/Traceability">Where-Used Impact Trace</a> to find every parent subassembly and top-level
    product that consumes a given component.
</div>

<h2>Step-by-Step Directions: Tracing Component Impact</h2>
<ol>
    <li><span class="step-num">Step 1 — Enter Component PN:</span> Type a <span class="code-pill">1AF</span> piece part or <span class="code-pill">2AS</span> subassembly number into <b>Component PN</b> (or click <span class="btn-slate">Find...</span>).</li>
    <li><span class="step-num">Step 2 — Select Upward Depth:</span> Choose <b>Full Multi-Level Up</b> to trace from the piece part through intermediate <span class="code-pill">2AS</span> subassemblies all the way to the top-level <span class="code-pill">3PR</span> products, or <b>Single-Level Up</b> to see only immediate parents.</li>
    <li><span class="step-num">Step 3 — Run Trace &amp; Export:</span> Click <span class="btn-slate">Trace Where-Used</span> to inspect every parent assembly, its Condition Code, Supply Class, and Quantity Per, or click <span class="btn-slate">Export CSV...</span>.</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 8)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Component PN &amp; [Find...]</td>
        <td>The child component (<span class="code-pill">1AF</span> or <span class="code-pill">2AS</span>) you want to trace upward through the product tree.</td>
    </tr>
    <tr>
        <td class="field-name">Full Multi-Level Up / Single-Level Up</td>
        <td>Controls whether the upward search stops at the immediate parent assembly or climbs all the way to top-level <span class="code-pill">3PR</span> products.</td>
    </tr>
    <tr>
        <td class="field-name">[Trace Where-Used] &amp; [Export CSV...]</td>
        <td>Populates the upward hierarchy table and exports the impact list to CSV for ECO scope planning.</td>
    </tr>
</table>
""",

    "09. Tab 9: Compare BOMs (Side-by-Side Redline Diff)": """
<h1>09. Tab 9: Multi-BOM Comparison Matrix</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 5 (Verify &amp; Audit)</b>. Need to know the exact bill-of-material
    differences between an 8-Foot Backhoe and a 10-Foot Heavy-Duty Backhoe—or between four different couplers? Tab 9 aligns
    <b>2 to 4 assemblies side by side</b> and highlights every single quantity delta.
</div>

<h2>Step-by-Step Directions: Comparing 2 to 4 Assemblies</h2>
<ol>
    <li><span class="step-num">Step 1 — Enter 2 to 4 Assembly PNs:</span> Type 2, 3, or 4 parent part numbers separated by commas into <b>Assembly PNs</b> (e.g., <span class="code-pill">3PR00000001, 3PR00000002, 3PR00000003</span>).</li>
    <li><span class="step-num">Step 2 — Optional Filters:</span> Check <b>Pending ECOs</b> to include staged markups, or enter a 3-digit code in <b>Cond Filter</b>.</li>
    <li><span class="step-num">Step 3 — Compare &amp; Inspect Deltas:</span> Click <span class="btn-slate">Compare BOMs</span>. Rows where quantities match across all compared assemblies highlight in <span style="color:#22C55E;font-weight:bold;">green (SAME)</span>; rows where a component is unique or has different quantities highlight in <span style="color:#F59E0B;font-weight:bold;">amber (DIFF)</span>!</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 9)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Assembly PNs (2 to 4, comma-separated)</td>
        <td>Accepts 2 to 4 <span class="code-pill">3PR</span> or <span class="code-pill">2AS</span> part numbers separated by commas.</td>
    </tr>
    <tr>
        <td class="field-name">Pending ECOs &amp; Cond Filter</td>
        <td>Includes uncommitted ECO BOM markups or filters compared assemblies by Condition Code.</td>
    </tr>
    <tr>
        <td class="field-name">[Compare BOMs] &amp; [Export CSV...]</td>
        <td>Dynamically re-labels the quantity columns with your exact Assembly PNs, color-codes <span class="code-pill">DIFF</span> vs. <span class="code-pill">SAME</span> rows, and exports the matrix to CSV.</td>
    </tr>
</table>
""",

    "10. Tab 10: Drawing Viewer (Vault Search & History)": """
<h1>10. Tab 10: Drawing Viewer &amp; Revision Vault</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 5 (Verify &amp; Audit)</b>. Tab 10 is your controlled digital print
    room—giving shop-floor viewers, buyers, and engineers instant access to current and historical drawing revisions plus linked
    vendor/technical specifications.
</div>

<h2>Step-by-Step Directions: Viewing Drawings &amp; Technical Docs</h2>
<ol>
    <li><span class="step-num">Step 1 — Search the Vault:</span> Enter a wildcard query in <b>Wildcard Search</b> (e.g., <span class="code-pill">1AF*79</span> or <span class="code-pill">1AF*</span>) and click <span class="btn-slate">Search</span>, or click <span class="btn-slate">Show All</span>.</li>
    <li><span class="step-num">Step 2 — Inspect Revision History:</span> The top table lists every registered revision. Current production drawings appear in <span style="color:#22C55E;font-weight:bold;">green (ACTIVE LATEST)</span>, while historical superseded revisions appear in <span style="color:#94A3B8;font-weight:bold;">slate (SUPERSEDED PREV REV)</span> for full audit traceability.</li>
    <li><span class="step-num">Step 3 — Open a Controlled Drawing PDF:</span> Highlight any row in the top table and click <span class="btn-slate">Open Highlighted Drawing Revision</span> to launch the PDF in your system viewer.</li>
    <li><span class="step-num">Step 4 — Open Supporting Vendor / Spec Docs:</span> In the bottom table (<b>Attached Supplier Drawings &amp; Supporting Technical Data</b>), <b>double-click any row</b> to open OEM hydraulic schematics, motor torque curves, or ISO load rating specs.</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 10)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Wildcard Search, [Search], [Show All]</td>
        <td>Searches across Drawing Numbers, Linked Part Summaries, and ECO Numbers.</td>
    </tr>
    <tr>
        <td class="field-name">[Open Highlighted Drawing Revision]</td>
        <td>Opens the exact archived PDF file for the selected drawing revision from the managed vault.</td>
    </tr>
    <tr>
        <td class="field-name">Supporting Technical Data Table (Bottom)</td>
        <td>Displays linked <span class="code-pill">SUPPLIER DRAWING</span> and <span class="code-pill">TECHNICAL SPEC</span> files. Double-click any row to open the file externally.</td>
    </tr>
</table>
""",

    "11. Tab 11: Settings (Nouns, Materials, UOMs & Themes)": """
<h1>11. Tab 11: Application Settings — Standards, Units &amp; Theme Studio</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 1 (Sign In &amp; Governance)</b>. Whether your shop runs on
    <a href="https://en.wikipedia.org/wiki/ISO_216">ISO Metric (A0–A4, mm, kg)</a> or
    <a href="https://en.wikipedia.org/wiki/ Engineering_drawing#ANSI/ASME_drawing_sizes">ANSI Inch (A–E, in, lb)</a>—or you want
    to dial in a custom dark slate or Yanmar Red visual theme—Tab 11 lets you customize hBOM live.
</div>

<h2>Step-by-Step Directions: Configuring Engineering Defaults &amp; Colors</h2>
<ol>
    <li><span class="step-num">Step 1 — Choose Drawing Sheet Standard:</span> In Panel 1, select <span class="code-pill">ISO (A4, A3, A2, A1, A0)</span>, <span class="code-pill">ANSI (A, B, C, D, E)</span>, or <span class="code-pill">BOTH (ISO + ANSI)</span>, and pick your <b>Default Drawing Size for New Parts</b>.</li>
    <li><span class="step-num">Step 2 — Set Default Dimensional Units:</span> Select <span class="code-pill">METRIC (mm, kg, mL, L)</span> or <span class="code-pill">INCH (in, lb, oz, gal)</span>. This automatically tailors bulk UOM dropdowns and envelope hints across Tabs 1–3.</li>
    <li><span class="step-num">Step 3 — Configure Managed Vault Root:</span> Verify or update the local/network directory path where controlled drawings and ECO attachments are archived.</li>
    <li><span class="step-num">Step 4 — Customize Your Visual Theme:</span> In Panel 2, pick a built-in <b>Theme Preset</b> or click <span class="btn-purple">Pick Color...</span> next to any of the 9 UI color roles to open the color wheel.</li>
    <li><span class="step-num">Step 5 — Apply Live:</span> Click <span class="btn-purple">Apply &amp; Save Settings</span> to persist your preferences to <span class="code-pill">user_settings.json</span> and repaint the entire application immediately!</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 11)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">Drawing Sheet Size Standard &amp; Default Size</td>
        <td>Filters the available sheet size dropdowns on Tabs 1, 2, and 3 and sets the default size for new items.</td>
    </tr>
    <tr>
        <td class="field-name">Default Dimensional Units</td>
        <td>Configures Metric vs. Inch bulk UOM options (<span class="code-pill">ML/L/MM/M/G/KG</span> vs. <span class="code-pill">OZ/GAL/IN/FT/LB</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Theme Preset &amp; [Pick Color...] Swatches</td>
        <td>Lets you select a preset palette or customize hex codes for Primary/Secondary/Surface backgrounds, text, and status accents.</td>
    </tr>
    <tr>
        <td class="field-name">[Apply &amp; Save Settings] / [Reset to Default]</td>
        <td>Applies and saves your settings immediately, or restores the factory <i>Slate &amp; Steel Blue</i> configuration.</td>
    </tr>
</table>
""",

    "12. Tab 12: Administration (User Accounts & RBAC)": """
<h1>12. Tab 12: User Administration — Accounts, Roles &amp; Security (ADMIN Only)</h1>
<div class="intro-box">
    <b>Where You Are in the Process:</b> You are in <b>Stage 1 (Sign In &amp; Governance)</b>. Tab 12 is strictly visible
    <b>only when signed in with the <span class="code-pill">ADMIN</span> role</b>—when a Viewer, Designer, or Approver logs in,
    hBOM automatically hides this tab to keep account security locked down.
</div>

<h2>Password Hashing &amp; Audit Integrity</h2>
<p>
    hBOM never stores plaintext passwords. Every password entered in Tab 12 is hashed using the
    <a href="https://csrc.nist.gov/projects/hash-functions">NIST FIPS 180-4 SHA-256 cryptographic hash function</a> before being
    written to the <span class="code-pill">users</span> table. Furthermore, each user's <b>Full Name</b> is automatically stamped
    into <span class="code-pill">created_by</span>, <span class="code-pill">approved_by</span>, and <span class="code-pill">released_by</span>
    audit columns whenever they create parts or transition ECOs.
</p>

<h2>Step-by-Step Directions: Creating or Updating a User Account</h2>
<ol>
    <li><span class="step-num">Step 1 — Select an Existing User or Start Fresh:</span> Click any row in the right-hand <b>Registered System Users</b> table to load that user into the left editor, or click <span class="btn-slate">Clear Form</span> to create a new account.</li>
    <li><span class="step-num">Step 2 — Enter Identity Details:</span> Fill in <b>User ID (Login)</b> (e.g., <span class="code-pill">jengineer</span>), <b>Full Name</b>, and <b>E-Mail Address</b>.</li>
    <li><span class="step-num">Step 3 — Assign Permission Role &amp; Status:</span> Choose <span class="code-pill">VIEWER (Read-Only)</span>, <span class="code-pill">DESIGNER (Create/Modify)</span>, <span class="code-pill">APPROVER (Approve/Release)</span>, or <span class="code-pill">ADMIN (Full Access)</span>, and set <b>Account Status</b> to <span class="code-pill">ACTIVE</span> (or <span class="code-pill">INACTIVE</span> to revoke login access without deleting historical audit records).</li>
    <li><span class="step-num">Step 4 — Set or Reset Password:</span> Enter a password in <b>Set / Reset Password</b> (or leave it blank when editing an existing user to keep their current password unchanged).</li>
    <li><span class="step-num">Step 5 — Save Account:</span> Click <span class="btn-purple">Save / Update User</span>.</li>
</ol>

<h2>Complete Field &amp; Button Reference (Tab 12)</h2>
<table class="ref-table">
    <tr>
        <th width="28%">Field / Button</th>
        <th>Engineering Purpose &amp; Behavior</th>
    </tr>
    <tr>
        <td class="field-name">User ID, Full Name, E-Mail Address</td>
        <td>Unique login handle, display name stamped on ECO sign-off blocks, and contact email.</td>
    </tr>
    <tr>
        <td class="field-name">Permission Role &amp; Account Status</td>
        <td>Assigns RBAC authority level and controls whether the user is permitted to sign in (<span class="code-pill">ACTIVE</span> vs. <span class="code-pill">INACTIVE</span>).</td>
    </tr>
    <tr>
        <td class="field-name">Set / Reset Password</td>
        <td>Hashes the new password with SHA-256. Leaving this field blank during an update preserves the user's existing password hash.</td>
    </tr>
    <tr>
        <td class="field-name">[Save / Update User], [Clear Form], [Refresh Users]</td>
        <td>Commits account changes to SQLite, clears the form for a new user entry, or reloads the user directory table.</td>
    </tr>
</table>
"""
}


def render_topic_html(topic_name: str, highlight_term: str = "") -> str:
    body = HELP_TOPICS_HTML.get(topic_name, "")
    if not body:
        return f"<html><head>{HTML_STYLE}</head><body><p>Topic not found.</p></body></html>"
    if highlight_term:
        body = _highlight_html_outside_tags(body, highlight_term)
    return f"<html><head>{HTML_STYLE}</head><body>{body}</body></html>"


def render_combined_html(highlight_term: str = "") -> str:
    combined = "<hr style='border:1px solid #334155; margin: 24px 0;'>".join(HELP_TOPICS_HTML.values())
    if highlight_term:
        combined = _highlight_html_outside_tags(combined, highlight_term)
    return f"<html><head>{HTML_STYLE}</head><body>{combined}</body></html>"


def _highlight_html_outside_tags(html_str: str, term: str) -> str:
    term = term.strip()
    if not term:
        return html_str
    pattern = re.compile(f"({re.escape(term)})", re.IGNORECASE)
    parts = re.split(r"(<[^>]+>)", html_str)
    for i in range(0, len(parts), 2):
        parts[i] = pattern.sub(
            r'<span style="background-color:#F59E0B; color:#000000; font-weight:bold;">\1</span>',
            parts[i]
        )
    return "".join(parts)


def _strip_html(html_str: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_str)
    return re.sub(r"\s+", " ", text).strip()


HELP_TOPICS = {k: _strip_html(v) for k, v in HELP_TOPICS_HTML.items()}
HELP_SECTIONS = HELP_TOPICS
HELP_DATA = HELP_TOPICS
USER_MANUAL = HELP_TOPICS
HELP_TEXT = "\n\n".join(HELP_TOPICS.values())
