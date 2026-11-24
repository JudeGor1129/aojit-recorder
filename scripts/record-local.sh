#!/bin/bash
# Record OpenMinis AOJIT images on a local or rented Apple Silicon Mac.
# Same pipeline as .github/workflows/record-aojit.yml, no CI required.
#
#   ./scripts/record-local.sh [ref] [modules...]
#   ./scripts/record-local.sh 1.15 musl busybox python
#
# Needs: macOS on Apple Silicon, Xcode, Homebrew, ~12 GB free.
set -euo pipefail

REF="${1:-1.15}"
shift || true
MODULES=("$@")
[ ${#MODULES[@]} -gt 0 ] || MODULES=(musl busybox python)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$HERE/src"
ISH="$SRC/deps/ish/build-arm64-jit/ish"
R="$SRC/deps/resources/alpine-rootfs"
JSON="$SRC/deps/ish/benchmark/aojit/images.json"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "macOS required."
[ "$(uname -m)" = "arm64" ] || die "Apple Silicon required (this is $(uname -m))."
command -v xcodebuild >/dev/null || die "Xcode command line tools required."
command -v brew >/dev/null || die "Homebrew required."
[ "$(df -g "$HERE" | awk 'NR==2 {print $4}')" -ge 12 ] || die "Need about 12 GB free."

say "Installing build tools"
brew list meson >/dev/null 2>&1 || brew install meson
brew list ninja >/dev/null 2>&1 || brew install ninja
brew list libarchive >/dev/null 2>&1 || brew install libarchive
python3 -m pip install --user --quiet tqdm 2>/dev/null \
  || python3 -m pip install --user --quiet --break-system-packages tqdm

say "Cloning OpenMinis $REF"
rm -rf "$SRC"
git clone --depth 1 --branch "$REF" \
  --recurse-submodules --shallow-submodules \
  https://github.com/OpenMinis/OpenMinis.git "$SRC"
git -C "$SRC" submodule status

say "Building the CLI iSH (JIT, run-time translation)"
(
  cd "$SRC/deps/ish"
  meson setup build-arm64-jit \
    --buildtype=release \
    -Dlog="" -Dkernel=ish -Dengine=asbestos \
    -Dguest_arch=arm64 -Djit=true -Djit_emit=true
  ninja -C build-arm64-jit
)

say "Preparing the Alpine rootfs"
(cd "$SRC" && ./deps/prepare_alpine_rootfs.sh 3.21)

say "Recording abi"
ABI=$(ISH_JIT_PIC=1 "$ISH" -r "$R" /bin/cat /proc/ish/jit | grep -o 'abi [0-9a-f]*' | cut -d' ' -f2)
echo "abi: $ABI  (Minis 1.15 expects 1f3bb5a0)"
[ "$ABI" = "1f3bb5a0" ] || echo "WARNING: abi mismatch, the app will reject these images."

say "Installing the guest packages"
# No -u: musl/busybox stay at the minirootfs versions the app ships with.
MSTR="${MODULES[*]}"
PKGS=$(cd "$SRC" && MSTR="$MSTR" python3 -c 'import json,os;d=json.load(open("deps/ish/benchmark/aojit/images.json"))["packages"]["apk"];m=os.environ["MSTR"].split();s=set();s.add("github-cli") if "gh" not in m else None;s.add("ripgrep") if "rg" not in m else None;print(" ".join(p for p in d if p not in s))')
"$ISH" -r "$R" /sbin/apk add $PKGS
"$ISH" -r "$R" /usr/bin/pip install --break-system-packages python-pptx

say "Installing the AOJIT workloads"
(cd "$SRC" && ./deps/ish/benchmark/aojit/install.sh "$ISH" "$R")

say "Recording: ${MODULES[*]}"
mkdir -p "$SRC/out"
(cd "$SRC" && IOS=1 JOBS="${JOBS:-2}" \
  ./deps/ish/benchmark/aojit/record_images.sh "$ISH" "$R" "$SRC/out" "${MODULES[@]}")

say "Result"
ls -lh "$SRC/out"
for f in "$SRC"/out/aot_*.S; do
  [ -e "$f" ] || continue
  echo "== $(basename "$f")"
  python3 "$SRC/deps/aot/tools/image_info.py" "$f" || true
done

cat <<EOF

Images are in: $SRC/out          (abi $ABI, ish $(git -C "$SRC/deps/ish" rev-parse --short HEAD))
Next: copy out/*.S into deps/aot/ of your OpenMinis checkout, then
      ./deps/build_ish.sh   (calls build_aot.sh, archives libish_aot.a)
      and build the app in Xcode.
EOF
