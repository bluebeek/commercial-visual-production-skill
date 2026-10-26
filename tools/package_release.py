"""Package only verified Skill sources and public user documentation."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
skill = root / "skills" / "commercial-visual-production-v3-0-0"
files = []
for item in manifest["files"]:
    source = skill / item["path"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
        raise SystemExit("Source checksum mismatch: " + item["path"])
    files.append(source)
for name in ("README.md", "README.en.md", "VALIDATION.md", "CHANGELOG.md", "LICENSE", "requirements.txt", "SOURCE_MANIFEST.json", "validation/round2/REPORT.md"):
    files.append(root / name)
out = root / "dist"
out.mkdir(exist_ok=True)
archive = out / "commercial-visual-production-v3-0-0.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for source in sorted(files):
        info = zipfile.ZipInfo(source.relative_to(root).as_posix(), (2026, 10, 23, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        bundle.writestr(info, source.read_bytes())
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(out / "SHA256SUMS.txt").write_text(checksum + "  " + archive.name + "\n", encoding="utf-8")
print(json.dumps({"files": len(files), "verified_sources": len(manifest["files"]), "sha256": checksum}))
