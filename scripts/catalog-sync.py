#!/usr/bin/env python3
"""Align Minis' AOJIT catalog with the images recorded here.

`AOJITSettingsView.swift` hard-codes, for each of its 25 images, the build-id
and package version that the *official* build was recorded against. The settings
page compares the build-id it reads out of the app's own rootfs with those
constants, so a self-built app only ever shows "Matched" for modules whose
guest binary is byte-identical to the one the official release used.

Recording today gets you the versions Alpine currently ships, which for several
packages (python3, nodejs, openssl, pcre2, openssh) is no longer the pinned one:
Alpine deletes superseded apks. Those modules then show "Family" even though the
recorded image matches the rootfs the app just built perfectly.

This script rewrites the catalog so the page tells the truth for *this* build:

    python3 scripts/catalog-sync.py \
        --manifest aot-manifest.json \
        --swift AOJITSettingsView.swift \
        --versions versions.txt \
        --out AOJITSettingsView.patched.swift

`versions.txt` is the "package version" table the workflow prints after
installing the guest packages (lines like "python3 3.12.16-r0"). Entries with no
recording here are left untouched.
"""
import argparse
import json
import re
import sys

# catalog entry name -> aot_<name>.S recorded by record_images.sh
ALIAS = {
    "musl": "musl",
    "BusyBox": "busybox",
    "Python": "python",
    "Node.js": "node",
    "Pillow": "imaging",
    "libwebp": "webp",
    "libjpeg-turbo": "jpeg",
    "NumPy": "numpy",
    "zlib": "zlib",
    "SQLite": "sqlite",
    "OpenSSL libcrypto": "crypto",
    "OpenSSL libssl": "ssl",
    "PCRE2": "pcre2",
    "OpenSSH ssh": "ssh",
    "OpenSSH scp": "scp",
    "Python json": "pyjson",
    "Python hashlib": "pyhashlib",
    "Python blake2": "pyblake2",
    "Python struct": "pystruct",
    "Python datetime": "pydatetime",
    "Python binascii": "pybinascii",
    "Python math": "pymath",
    "Python zlib": "pyzlib",
    "Python socket": "pysocket",
    "Python select": "pyselect",
}


def load_manifest(path):
    data = json.load(open(path))
    out = {}
    for item in data:
        stem = item["file"][len("aot_"):-len(".S")]
        out[stem] = item
    return out


def load_versions(path):
    versions = {}
    if not path:
        return versions
    for line in open(path):
        parts = line.split()
        if len(parts) >= 2:
            versions[parts[0]] = parts[1]
    return versions


def entries(text):
    """Yield (start, end, block) for each AOJITImage(...) in the catalog."""
    for m in re.finditer(r"AOJITImage\(\s*(.*?)\n\s{4,}?\),", text, re.S):
        yield m.start(1), m.end(1), m.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--swift", required=True)
    ap.add_argument("--versions", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    images = load_manifest(args.manifest)
    versions = load_versions(args.versions)
    text = open(args.swift).read()

    rows = []
    patched = text[:]
    offset = 0
    touched = 0
    for start, end, block in entries(text):
        name = re.search(r'name: *"([^"]*)"', block)
        build = re.search(
            r'build:\s*AOJITBuild\(\s*file:\s*"([^"]*)",\s*buildId:\s*"([^"]*)",\s*package:\s*"([^"]*)"',
            block, re.S,
        )
        if not (name and build):
            continue
        name, old_file, old_bid, old_pkg = name.group(1), build.group(1), build.group(2), build.group(3)
        stem = ALIAS.get(name)
        img = images.get(stem) if stem else None
        new_bid = (img or {}).get("build_id")
        pkg_name = old_pkg.rsplit(" ", 1)[0]
        new_ver = versions.get(pkg_name, "")
        new_pkg = f"{pkg_name} {new_ver}" if new_ver else old_pkg
        verdict = "no image" if not img else ("same" if new_bid == old_bid else "rebind")
        rows.append((name, old_pkg, new_pkg, old_bid, new_bid, verdict))

        # `file` is only a display label and the recorded .S keeps its own name,
        # so it is left alone; only the build-id (and the version label) move.
        if img and new_bid and (new_bid != old_bid or new_pkg != old_pkg):
            nb = block
            nb = nb.replace(f'buildId: "{old_bid}"', f'buildId: "{new_bid}"', 1)
            if new_pkg != old_pkg:
                nb = nb.replace(f'package: "{old_pkg}"', f'package: "{new_pkg}"', 1)
            patched = patched[: start + offset] + nb + patched[end + offset:]
            offset += len(nb) - (end - start)
            touched += 1

    width = max(len(r[0]) for r in rows) + 2
    print(f"{'catalog entry':{width}} {'old package':26} {'new package':26} {'build-id':10}")
    for name, old_pkg, new_pkg, old_bid, new_bid, verdict in rows:
        mark = {"same": "== same", "rebind": "-> rebind", "no image": "-- none"}[verdict]
        print(f"{name:{width}} {old_pkg:26} {new_pkg:26} {mark}")

    print(f"\n{touched} of {len(rows)} entries rewritten; {len(rows) - touched} left as-is "
          f"({sum(1 for r in rows if r[5] == 'no image')} without a recording here).")

    if args.out:
        open(args.out, "w").write(patched)
        print(f"wrote {args.out}")
    if args.report:
        lines = ["| catalog entry | official package | recorded package | build-id |",
                 "|---|---|---|---|"]
        for name, old_pkg, new_pkg, old_bid, new_bid, verdict in rows:
            mark = {"same": "identical", "rebind": "rebound", "no image": "not recorded"}[verdict]
            lines.append(f"| {name} | {old_pkg} | {new_pkg} | {mark} |")
        open(args.report, "w").write("\n".join(lines) + "\n")
        print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
