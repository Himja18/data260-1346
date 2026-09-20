import hashlib, json, os, sys

corpus_dir = sys.argv[1] if len(sys.argv) > 1 else "."
files = sorted([f for f in os.listdir(corpus_dir) if f.endswith('.txt')])
manifest = {
    "domain_id": 2, "domain_name": "Municipal Transit Incidents", "sid4": 1346,
    "prefix": "s1346", "corpus_finalized": "2026-09-19",
    "total_files": len(files), "total_bytes": 0, "files": []
}
for f in files:
    with open(os.path.join(corpus_dir, f), 'rb') as fh:
        data = fh.read()
    manifest["total_bytes"] += len(data)
    manifest["files"].append({"filename": f, "byte_size": len(data), "sha256": hashlib.sha256(data).hexdigest()})

with open(os.path.join(corpus_dir, "CORPUS_MANIFEST.json"), 'w') as out:
    json.dump(manifest, out, indent=2)

print(f"{len(files)} files, {manifest['total_bytes']} bytes total")