"""Copy the image that is actually running on the source VPS, with identity checks."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from transfert_vps import SOURCE, STAGING, TARGET, remote, say, sha256

REF = "lexmachine-budget:20260929-consultation-chaude"
SOURCE_ARCHIVE = "/home/marie/nos-deniers-web-20260929-active.tar"
SOURCE_MANIFEST = "/home/marie/nos-deniers-web-20260929-active.txt"
TARGET_ARCHIVE = "/opt/nos-deniers/staging/20260929/web-active.tar"
FILES = [
    "/app/budget_service/api.py",
    "/app/budget_service/cell_reviews.py",
    "/app/budget_service/consultation.py",
    "/app/budget_service/web.py",
    "/app/public/assets/explorer.js",
    "/app/public/assets/explorer.css",
    "/app/public/explorer.html",
]


def sftp(host: str, command: str, local_dir: Path = STAGING) -> None:
    """Use a private batch file while the large index transfer runs."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=STAGING,
                                     prefix="image-transfer-", suffix=".sftp", delete=False) as stream:
        stream.write(f'lcd "{local_dir.as_posix()}"\n{command}\n')
        batch = Path(stream.name)
    try:
        subprocess.run(["sftp", "-o", "BatchMode=yes", "-b", str(batch), host], check=True)
    finally:
        batch.unlink(missing_ok=True)


def source_text(command: str) -> str:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SOURCE, command],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def main() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    manifest = source_text(f"cat {SOURCE_MANIFEST}")
    fields = dict(line.split("=", 1) for line in manifest.splitlines() if "=" in line)
    if fields.get("compose") != REF or fields.get("running_ref") != REF:
        raise RuntimeError("Source image does not match expected active Compose release")
    expected_id = fields["running_id"]
    expected_size = int(fields["archive_size"])
    expected_sha = fields["archive_sha256"]
    local = STAGING / "web-active.tar"
    partial = STAGING / "web-active.tar.part"
    if local.exists() and (local.stat().st_size != expected_size or sha256(local) != expected_sha):
        raise RuntimeError("Existing local image archive differs from active source")
    if not local.exists():
        say(f"Download exact running web image ({expected_size:,} bytes)")
        sftp(SOURCE, f"reget {SOURCE_ARCHIVE} {partial.name}")
        if partial.stat().st_size != expected_size or sha256(partial) != expected_sha:
            raise RuntimeError("Downloaded web image archive mismatch")
        partial.replace(local)
    present_text = remote(f"stat -c %s {TARGET_ARCHIVE}", missing_ok=True)
    present = int(present_text) if present_text is not None else None
    if present != expected_size:
        say("Upload exact running web image to target")
        sftp(TARGET, f"{'reput' if present is not None else 'put'} {local.name} {TARGET_ARCHIVE}")
    if int(remote(f"stat -c %s {TARGET_ARCHIVE}")) != expected_size:
        raise RuntimeError("Target archive size mismatch")
    if remote(f"sha256sum {TARGET_ARCHIVE}").split()[0] != expected_sha:
        raise RuntimeError("Target archive SHA-256 mismatch")
    say("Image archive SHA-256 matches source on target")
    remote(f"docker load -i {TARGET_ARCHIVE}")
    actual_id = remote(f"docker image inspect {REF} --format '{{{{.Id}}}}'")
    if actual_id != expected_id:
        raise RuntimeError(f"Loaded image ID mismatch: {actual_id} != {expected_id}")
    actual_hashes = remote(f"docker run --rm --entrypoint sha256sum {REF} {' '.join(FILES)}")
    expected_hashes = {line.split()[1]: line.split()[0] for line in manifest.splitlines() if line.startswith(tuple("0123456789abcdef")) and "/app/" in line}
    for line in actual_hashes.splitlines():
        digest, path = line.split()
        if expected_hashes.get(path) != digest:
            raise RuntimeError(f"Image file mismatch: {path}")
    say(f"Exact active web image loaded and checked: {actual_id}")
    (STAGING / "web-active-manifest.txt").write_text(manifest + "\n", encoding="utf-8")
    # The same root-only source export includes the still-valid public TLS
    # certificate. Keep its private key out of the Git tree and local logs.
    tls_size = int(fields["tls_archive_size"])
    tls_sha = fields["tls_archive_sha256"]
    tls_local = STAGING / "tls-active.tar"
    tls_partial = STAGING / "tls-active.tar.part"
    tls_target = "/opt/nos-deniers/staging/20260929/tls-active.tar"
    try:
        if tls_local.exists() and (tls_local.stat().st_size != tls_size or sha256(tls_local) != tls_sha):
            raise RuntimeError("Existing local TLS archive differs from source")
        if not tls_local.exists():
            sftp(SOURCE, f"reget /home/marie/nos-deniers-tls-20260929-active.tar {tls_partial.name}")
            if tls_partial.stat().st_size != tls_size or sha256(tls_partial) != tls_sha:
                raise RuntimeError("Downloaded TLS archive mismatch")
            tls_partial.replace(tls_local)
        present_text = remote(f"stat -c %s {tls_target}", missing_ok=True)
        if present_text is None or int(present_text) != tls_size:
            sftp(TARGET, f"{'reput' if present_text is not None else 'put'} {tls_local.name} {tls_target}")
        if remote(f"sha256sum {tls_target}").split()[0] != tls_sha:
            raise RuntimeError("Target TLS archive SHA-256 mismatch")
        remote(f"chmod 600 {tls_target}")
        say("TLS archive transferred and verified without exposing the key")
    finally:
        tls_local.unlink(missing_ok=True)
        tls_partial.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
