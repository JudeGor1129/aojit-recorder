#!/usr/bin/env python3
"""Fail-closed check: the catalog must describe exactly the images we built.

`catalog-sync.py` rewrites AOJITSettingsView.swift so the settings page can
report "Matched". That rewrite is only safe if the constants it writes really
are the build-ids of the images in the artifact: a build-id that does not
correspond to the linked image would let the kernel run translations recorded
from a *different* binary, which is precisely what the build-id gate exists to
prevent.

This script is the gate. It fails the build unless, for every catalog entry:

  * an image with the matching module stem exists in the manifest,
  * that image's abi is the expected one (Minis 1.15: 1f3bb5a0),
  * the image's build_id is a 40-hex NT_GNU_BUILD_ID,
  * the patched Swift constant is byte-identical to that build_id.

Images recorded here but not listed in the catalog (gh, rg, ...) are reported
and accepted: they are linked, they are just not shown as a row.

Usage:
  verify-aojit.py --manifest aot-manifest.json --swift AOJITSettingsView.patched.swift \
                  [--versions versions.txt] [--expect-abi 1f3bb5a0]
"""
import argparse
import importlib.util
import json
import re
import sys

HEX40 = re.compile(r"^[0-9a-f]{40}$")


def load_alias(script):
    spec = importlib.util.spec_from_file_location("catalog_sync", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ALIAS


def catalog_entries(text):
    for m in re.finditer(r"AOJITImage\(\s*(.*?)\n\s{4,}?\),", text, re.S):
        block = m.group(1)
        name = re.search(r'name: *"([^"]*)"', block)
        build = re.search(
            r'build:\s*AOJITBuild\(\s*file:\s*"([^"]*)",\s*buildId:\s*"([^"]*)",\s*package:\s*"([^"]*)"',
            block, re.S,
        )
        if name and build:
            yield name.group(1), build.group(1), build.group(2), build.group(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--swift", required=True)
    ap.add_argument("--catalog-sync", default="scripts/catalog-sync.py")
    ap.add_argument("--versions", default="")
    ap.add_argument("--expect-abi", default="1f3bb5a0")
    ap.add_argument("--allow-unlisted", action="store_true", default=True)
    args = ap.parse_args()

    alias = load_alias(args.catalog_sync)
    images = {}
    for item in json.load(open(args.manifest)):
        images[item["file"][len("aot_"):-len(".S")]] = item

    versions = {}
    if args.versions:
        for line in open(args.versions):
            parts = line.split()
            if len(parts) >= 2:
                versions[parts[0]] = parts[1]

    errors = []
    checked = set()

    for stem, img in images.items():
        if img.get("abi") != args.expect_abi:
            errors.append(f"image {img['file']}: abi {img.get('abi')!r} != {args.expect_abi}")

    for name, file, build_id, package in catalog_entries(open(args.swift).read()):
        stem = alias.get(name)
        if not stem:
            errors.append(f"{name}: no image alias in catalog-sync.py")
            continue
        checked.add(stem)
        img = images.get(stem)
        if not img:
            errors.append(f"{name}: catalog entry has no recorded image (aot_{stem}.S missing)")
            continue
        if not HEX40.match(img.get("build_id") or ""):
            errors.append(f"{name}: recorded aot_{stem}.S has no 40-hex build-id "
                          f"({img.get('build_id')!r}), so the gate cannot match it")
        elif build_id != img["build_id"]:
            errors.append(
                f"{name}: catalog buildId {build_id} != recorded {img['build_id']} (aot_{stem}.S)"
            )
        pkg_name, _, want_ver = package.rpartition(" ")
        if versions:
            got = versions.get(pkg_name)
            if not got:
                errors.append(f"{name}: package {pkg_name!r} not found in the guest rootfs")
            elif got != want_ver:
                errors.append(f"{name}: catalog pins {package!r}, rootfs has {pkg_name} {got}")

    unlisted = sorted(set(images) - checked)
    print(f"catalog entries checked : {len(checked)}")
    print(f"images in manifest      : {len(images)}")
    if unlisted:
        print(f"recorded but not in UI  : {', '.join(unlisted)}")
    if errors:
        print("\nFAIL-CLOSED: refusing to publish an inconsistent catalog", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("OK: every catalog constant equals the build-id of its recorded image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
