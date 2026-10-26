"""Compare the file checksums of two dataset manifests.

    python scripts/compare_manifests.py data/starter/manifest.json out/ci/manifest.json

Exits with status 1 and lists the differing files if any checksum or row count differs.
"""

import json
import sys


def main(a: str, b: str) -> int:
    fa = {f["path"]: f for f in json.load(open(a, encoding="utf-8"))["files"]}
    fb = {f["path"]: f for f in json.load(open(b, encoding="utf-8"))["files"]}
    bad = [p for p in sorted(set(fa) | set(fb))
           if p not in fa or p not in fb or fa[p]["sha256"] != fb[p]["sha256"] or fa[p]["rows"] != fb[p]["rows"]]
    print(f"{len(set(fa) | set(fb)) - len(bad)}/{len(set(fa) | set(fb))} files identical")
    for p in bad:
        print(f"  differs: {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
