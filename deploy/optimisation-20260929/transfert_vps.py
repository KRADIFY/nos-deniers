"""Resumable, verified local relay between the two Nos Deniers VPS hosts.

Only the existing client SSH identities are used. No server receives a new key.
All remote writes stay below /opt/nos-deniers/staging/20260929 on the target.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


SOURCE = "marie@109.199.112.132"
TARGET = "root@5.189.145.254"
STAGING = Path("D:/ChatGPT/docker/budget/reports/migration-vmi3304602-20260929")
LOCAL_MIRRORS = {
    "search/search.sqlite": Path("D:/LexMachine/NosDeniers/search_20260919/search.sqlite"),
    "search/dense.faiss": Path("D:/LexMachine/NosDeniers/search_20260919/dense.faiss"),
    "retrieval-image.tar.gz": Path("D:/ChatGPT/docker/budget/deploy/update-20260924-final/retrieval-image.tar.gz"),
}
DESTINATION = "/opt/nos-deniers/staging/20260929"

OLD_INDEX = "/opt/lexmachine-budget/releases/20260924-final"
FILES = [
    ("data.tar", "/home/marie/nos-deniers-data-20260929-migration.tar", "data.tar", 4738887680,
     "920a5c38b0205d487e5fdec2d96517317ef9a9fee00a84e373cf420d9a3eb05d"),
    ("retrieval-image.tar.gz", "/home/marie/nos-deniers-update-20260924-final/retrieval-image.tar.gz",
     "retrieval-image.tar.gz", 3381399255, "685be272bbb42fe4a9e617e7cb8ffffc438b97601046c6ac4560433586018a53"),
    ("search.sqlite", f"{OLD_INDEX}/search/search.sqlite", "search/search.sqlite", 25879855104,
     "17015a96351d9460e37d1756922f40a83bd8bb23d8b74d27a054ae53a7a28cbc"),
    ("dense.faiss", f"{OLD_INDEX}/search/dense.faiss", "search/dense.faiss", 4185289728,
     "db5d369b29d4294b639743f6c5b272f45e3e94007a107ca8b3c2048f492aaecf"),
    ("search.sqlite", f"{OLD_INDEX}/search-supplement/search.sqlite", "search-supplement/search.sqlite", 26697728,
     "426ec04de8044408a529c851579d8c83cdcb2865d145545d3dd8efe9a7825e86"),
    ("dense.faiss", f"{OLD_INDEX}/search-supplement/dense.faiss", "search-supplement/dense.faiss", 11405106,
     "d0297767605c6a22ad3819612e08b037214cbc304a3dc162dd6f64563f97865b"),
    ("search.sqlite", f"{OLD_INDEX}/search-supplement2/search.sqlite", "search-supplement2/search.sqlite", 612409344,
     "8aa4fab9ce77e261a91bf69b04d4b4706a043f58f0118f341b6fe657a355eca9"),
    ("dense.faiss", f"{OLD_INDEX}/search-supplement2/dense.faiss", "search-supplement2/dense.faiss", 141679248,
     "a0a5f7fe0a5074977fb1303783928277d8716e4ef3989d41a352081d7cbc7903"),
    ("manifest.json", f"{OLD_INDEX}/search/manifest.json", "search/manifest.json", 802,
     "d8389e7ed25737ad03480724a21a9decece2c3eeebc9a3058d29f0a190c0f076"),
    ("manifest.json", f"{OLD_INDEX}/search-supplement/manifest.json", "search-supplement/manifest.json", 15523,
     "205fc398e9a343eb29adee7c9bbfd738403a52ed0e42e5ebf5dd5fe51857f60a"),
    ("manifest.json", f"{OLD_INDEX}/search-supplement2/manifest.json", "search-supplement2/manifest.json", 887,
     "6b16ba666d81ec6e70597d3ad8570fdb9dde9b9694417eb1ec4020a809bb7b08"),
]


def say(message: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote(command: str, *, missing_ok: bool = False) -> str | None:
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", TARGET, command],
                            capture_output=True, text=True)
    if result.returncode:
        if missing_ok and result.returncode == 1:
            return None
        raise RuntimeError(f"Remote check failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def sftp(host: str, command: str, local_dir: Path = STAGING) -> None:
    batch = STAGING / "transfer.sftp"
    batch.write_text(f'lcd "{local_dir.as_posix()}"\n{command}\n', encoding="ascii")
    subprocess.run(["sftp", "-o", "BatchMode=yes", "-b", str(batch), host], check=True)


def set_status(relative: str, step: str, **details: object) -> None:
    report = {"file": relative, "step": step, "updated": time.strftime("%Y-%m-%d %H:%M:%S"), **details}
    (STAGING / "status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def transfer(entry: tuple[str, str, str, int, str]) -> None:
    _, source, relative, size, expected_hash = entry
    local = LOCAL_MIRRORS.get(relative, STAGING / relative.replace("/", "-"))
    if relative in LOCAL_MIRRORS and not local.exists():
        raise RuntimeError(f"Expected local mirror is absent: {local}")
    partial = Path(str(local) + ".part")
    destination = f"{DESTINATION}/{relative}"
    if local.exists() and (local.stat().st_size != size or sha256(local) != expected_hash):
        raise RuntimeError(f"Existing verified-name file does not match manifest: {local}")
    if not local.exists():
        if partial.exists() and partial.stat().st_size > size:
            raise RuntimeError(f"Partial local file is larger than expected: {partial}")
        say(f"Download {relative} ({size:,} bytes)")
        set_status(relative, "download", bytes_local=partial.stat().st_size if partial.exists() else 0, total=size)
        sftp(SOURCE, f"reget {source} {partial.name}")
        if partial.stat().st_size != size or sha256(partial) != expected_hash:
            raise RuntimeError(f"Downloaded file did not match SHA-256 manifest: {relative}")
        partial.replace(local)
    say(f"Local SHA-256 checked: {relative}")
    set_status(relative, "upload", bytes_local=size, total=size)
    remote_size_text = remote(f"stat -c %s {destination}", missing_ok=True)
    remote_size = int(remote_size_text) if remote_size_text is not None else None
    if remote_size is not None and remote_size > size:
        raise RuntimeError(f"Remote file is larger than expected: {destination}")
    if remote_size != size:
        command = "put" if remote_size is None else "reput"
        say(f"Upload {relative} ({remote_size or 0:,}/{size:,} bytes present)")
        sftp(TARGET, f"{command} {local.name} {destination}", local.parent)
    remote_size_text = remote(f"stat -c %s {destination}")
    if int(remote_size_text) != size:
        raise RuntimeError(f"Remote file size differs: {destination}")
    remote_hash = remote(f"sha256sum {destination}").split()[0]
    if remote_hash != expected_hash:
        raise RuntimeError(f"Remote SHA-256 differs: {destination}")
    say(f"Remote SHA-256 checked: {relative}")
    set_status(relative, "verified", bytes_local=size, bytes_remote=size, sha256=remote_hash)


def main() -> int:
    STAGING.mkdir(parents=True, exist_ok=True)
    for entry in FILES:
        transfer(entry)
    set_status("all", "complete", files=len(FILES), total_bytes=sum(entry[3] for entry in FILES))
    say("All files copied and verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        say(f"TRANSFER STOPPED: {exc}")
        raise
