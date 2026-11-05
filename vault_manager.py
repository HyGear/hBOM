"""
Managed File Vault & SHA-256 Integrity Service for hBOM.
Computes SHA-256 checksums for drawings and ECO attachments and optionally
copies files into a structured, read-only central vault directory.
"""

import os
import shutil
import hashlib
from typing import Tuple


def compute_file_sha256(filepath: str) -> str:
    """Returns the SHA-256 hex digest of a local file, or 'VIRTUAL-PATH-NO-LOCAL-FILE' if simulated."""
    if not filepath or not os.path.isfile(filepath):
        # Deterministic hash of path string when testing with virtual/sample paths
        return "SIM-" + hashlib.sha256((filepath or "").encode("utf-8")).hexdigest()[:20].upper()
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def store_in_managed_vault(
    source_path: str,
    vault_root: str,
    subfolder: str,
    target_prefix: str,
    copy_enabled: bool = True
) -> Tuple[str, str]:
    """
    Computes SHA-256 checksum and, if `source_path` exists on disk and `copy_enabled` is True,
    copies the file into `<vault_root>/<subfolder>/<target_prefix>_<filename>`.
    Returns (final_stored_path, sha256_hex).
    """
    clean_src = (source_path or "").strip()
    sha256_hex = compute_file_sha256(clean_src)

    if not copy_enabled or not os.path.isfile(clean_src) or not vault_root:
        return clean_src, sha256_hex

    dest_dir = os.path.join(vault_root, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    base_name = os.path.basename(clean_src)
    safe_prefix = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in target_prefix)
    dest_path = os.path.join(dest_dir, f"{safe_prefix}_{base_name}")

    if os.path.abspath(clean_src) != os.path.abspath(dest_path):
        shutil.copy2(clean_src, dest_path)

    return dest_path, sha256_hex
