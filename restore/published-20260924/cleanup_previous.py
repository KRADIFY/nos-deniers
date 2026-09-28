#!/usr/bin/env python3
"""Remove only the immediately previous Budget release after verified publication."""
from pathlib import Path
import hashlib, json, os, shutil, socket, subprocess, urllib.request

HOST = "vmi3274092"
ROOT = Path("/opt/lexmachine-budget")
NEW = ROOT / "releases" / "20260924-final"
OLD = ROOT / "releases" / "20260910-reactivation"
OLD_PACKAGE = Path("/home/marie/nos-deniers-update-20260910-reactivation")
EXPECTED_SHA = "7dfaeae20587bbcd5e0ea67d6b71ecae0f4ede7b9db57a6f4ffaed12a8c3d05f"
OLD_IMAGE = "lexmachine-budget:20260910-reactivation"

def require(condition, message):
    if not condition:
        raise RuntimeError(message)
def read(path):
    return json.loads(path.read_text(encoding="utf-8"))
def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()
def inspect(name):
    return json.loads(subprocess.check_output(["docker","inspect",name],text=True))[0]
def require_tree(path, parent, owner=None):
    require(path.parent == parent and path.is_dir() and not path.is_symlink() and path.resolve() == path,
            "Unexpected deletion target: " + str(path))
    if owner is not None:
        require(path.stat().st_uid == owner, "Unexpected owner: " + str(path))
    for child in path.rglob("*"):
        require(not child.is_symlink(), "Symbolic link in deletion target: " + str(child))

require(os.geteuid() == 0 and socket.gethostname() == HOST, "Run as root on the reviewed VPS")
release = read(NEW / "release.json")
ready = read(Path("/home/marie/nos-deniers-update-20260924-final/READY.json"))
deployment = read(ROOT / "deployment.json")
require(release.get("release") == "20260924-final", "Wrong new release")
require(digest(NEW / "release.json") == EXPECTED_SHA and ready.get("release_sha256") == EXPECTED_SHA,
        "New release hash differs")
require(deployment.get("release") == str(NEW) and deployment.get("state") == "published" and
        deployment.get("release_sha256") == EXPECTED_SHA, "New release not published")
for name in ("data/derived/budget.sqlite","search/search.sqlite",
             "search-supplement/search.sqlite","search-supplement2/search.sqlite"):
    require((NEW / name).is_file(), "New file missing: " + name)
for name in ("lexmachine-budget-public-web-1","lexmachine-budget-public-retrieval-1"):
    container = inspect(name)
    require(container["State"]["Running"] and
            container["Config"]["Labels"].get("com.docker.compose.project.working_dir") == str(NEW),
            "New container not active: " + name)
bootstrap = json.load(urllib.request.urlopen("http://127.0.0.1:8552/api/bootstrap",timeout=30))
search = json.load(urllib.request.urlopen("http://127.0.0.1:8552/api/semantic-search/status",timeout=30))
require(bootstrap["meta"]["fact_count"] == 122970, "Wrong public financial corpus")
require(search.get("available") and search.get("passages") == 4191315 and
        search.get("documents") == 4496, "Wrong public vector corpus")
require_tree(OLD, ROOT / "releases", 0)
require_tree(OLD_PACKAGE, Path("/home/marie"))
print("Nouvelle version et trois index vÃ©rifiÃ©s. Suppression ciblÃ©e de l'ancienne version.",flush=True)
shutil.rmtree(OLD)
shutil.rmtree(OLD_PACKAGE)
used = subprocess.check_output(["docker","ps","-a","--filter","ancestor="+OLD_IMAGE,"-q"],text=True).strip()
if not used:
    subprocess.run(["docker","image","rm",OLD_IMAGE],check=False)
deployment.pop("previous",None)
deployment.pop("rollback",None)
deployment["previous_removed"] = str(OLD)
deployment["rollback_available"] = False
tmp = ROOT / "deployment.json.cleanup-part"
require(not tmp.exists() and not tmp.is_symlink(), "Unexpected deployment temporary file")
tmp.write_text(json.dumps(deployment,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
tmp.chmod(0o644)
os.replace(tmp,ROOT / "deployment.json")
print("Ancienne version supprimÃ©e ; site public et nouvelle base conservÃ©s.",flush=True)

