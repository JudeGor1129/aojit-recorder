#!/bin/sh
# Guest-side workload for libpcre2-8.
#
# benchmark/aojit/images.json has no `pcre2` entry, so record_images.sh never
# records that module even though AOJITSettingsView.swift lists it. record.sh is
# driven directly for it instead (see the workflow), with this script as the
# workload and libpcre2-8.so.0 as the module.
#
# pcre2grep comes from pcre2-tools and is a dynamic client of the same library.
# Every call is wrapped so a non-zero exit (no match) cannot make record.sh
# treat the step as failed.
set -e
cd /tmp/aojit/pcre2

if ! command -v pcre2grep >/dev/null 2>&1; then
    echo "pcre2grep missing: pcre2-tools was not installed"
    exit 1
fi

: > text.txt
i=1
while [ "$i" -le 400 ]; do
    echo "row $i: alpha-$((i * 7)) beta_gamma delta$i url http://example.com/p/$i" >> text.txt
    i=$((i + 1))
done
cat text.txt text.txt text.txt > big.txt

run() { "$@" >/dev/null 2>&1 || true; }

for p in 'alpha-[0-9]+' 'beta_[a-z]+' '(delta[0-9]+)' 'http://[a-z.]+/p/[0-9]+' '^row [0-9]+:' '(?<=row )([0-9]+)' 'alpha-(?=[0-9])'; do
    run pcre2grep -c "$p" big.txt
    run pcre2grep -o "$p" big.txt
    run pcre2grep -i -c 'ALPHA' big.txt
done
run pcre2grep -M 'row [0-9]+:\n' big.txt
run pcre2grep --count --file=/dev/null big.txt

echo "pcre2 workload done"
