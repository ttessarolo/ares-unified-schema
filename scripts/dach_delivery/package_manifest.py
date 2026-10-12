#!/usr/bin/env python3
"""Hash only the portable delivery package, never local external sources."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
files=[root/'README.md',root/'.gitignore']
for directory in [root/'outputs',root/'scripts/dach_delivery']:
    files.extend(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in {'.DS_Store','manifest.json'})
entries=[]
for path in sorted(files):
    data=path.read_bytes();entries.append({'path':str(path.relative_to(root)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(root/'outputs/manifest.json').write_text(json.dumps({'version':1,'scope':'Reviewed DACH delivery and reproducible source; no real Kafka payloads or external source archives.','files':entries},indent=2)+'\n')
print(f'Wrote {len(entries)} package hashes')
