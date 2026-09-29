"""Transfer the verified main SQLite index through a resumable zstd archive."""
from __future__ import annotations

import subprocess
from pathlib import Path

from transfert_vps import DESTINATION, STAGING, TARGET, remote, say, sftp, sha256

LOCAL = STAGING / "search.sqlite.zst"
DEST = f"{DESTINATION}/search.sqlite.zst"
RAW = f"{DESTINATION}/search/search.sqlite"
EXPECTED_RAW_SIZE = 25879855104
EXPECTED_RAW_SHA = "17015a96351d9460e37d1756922f40a83bd8bb23d8b74d27a054ae53a7a28cbc"


def main() -> None:
    if not LOCAL.is_file():
        raise RuntimeError(f"Compressed file missing: {LOCAL}")
    size = LOCAL.stat().st_size
    subprocess.run(["zstd", "-t", str(LOCAL)], check=True, capture_output=True)
    compressed_hash = sha256(LOCAL)
    say(f"Compressed index checked: {size:,} bytes, sha256={compressed_hash}")
    size_text = remote(f"stat -c %s {DEST}", missing_ok=True)
    present = int(size_text) if size_text is not None else None
    if present is not None and present > size:
        raise RuntimeError("Remote compressed index is larger than local one")
    if present != size:
        command = "reput" if present is not None else "put"
        say(f"Upload compressed index ({present or 0:,}/{size:,})")
        sftp(TARGET, f"{command} {LOCAL.name} {DEST}")
    if int(remote(f"stat -c %s {DEST}")) != size:
        raise RuntimeError("Compressed index remote size mismatch")
    if remote(f"sha256sum {DEST}").split()[0] != compressed_hash:
        raise RuntimeError("Compressed index remote SHA-256 mismatch")
    say("Compressed index remote SHA-256 checked")
    temporary = RAW + ".new"
    remote(f"zstd -dc -- {DEST} > {temporary}")
    if int(remote(f"stat -c %s {temporary}")) != EXPECTED_RAW_SIZE:
        raise RuntimeError("Decompressed index remote size mismatch")
    if remote(f"sha256sum {temporary}").split()[0] != EXPECTED_RAW_SHA:
        raise RuntimeError("Decompressed index remote SHA-256 mismatch")
    remote(f"mv -f -- {temporary} {RAW}")
    say("Uncompressed main index restored and SHA-256 checked on target")


if __name__ == "__main__":
    main()
