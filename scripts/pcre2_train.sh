#!/bin/sh
# Guest-side workload for libpcre2-8.
#
# benchmark/aojit/images.json has no `pcre2` entry, so record_images.sh never
# records that module even though AOJITSettingsView.swift lists it. record.sh is
# driven directly for it instead (see the workflow), with this script as the
# workload and /usr/lib/libpcre2-8.so.0 as the module.
#
# grep -P and pcre2grep both execute the same library; whichever the rootfs has
# is used. Every call is wrapped so a non-zero exit (no match) cannot make
# record.sh treat the step as failed.
set -e
cd /tmp/aojit/pcre2

: > text.txt
i=1
while [ "$i" -le 400 ]; do
    echo "row $i: alpha-$((i * 7)) beta_gamma delta$i url http://example.com/p/$i" >> text.txt
    i=$((i + 1))
done
cat text.txt text.txt text.txt > big.txt

run() { "$@" >/dev/null 2>&1 || true; }

if command -v pcre2grep >/dev/null 2>&1; then
    for p in 'alpha-[0-9]+' 'beta_[a-z]+' '(delta[0-9]+)' 'http://[a-z.]+/p/[0-9]+' '^row [0-9]+:' '(?<=row )([0-9]+)' 'alpha-(?=[0-9])'; do
        run pcre2grep -c "$p" big.txt
        run pcre2grep -o "$p" big.txt
        run pcre2grep -i -c 'ALPHA' big.txt
    done
    run pcre2grep -M 'row [0-9]+:\n' big.txt
fi

# GNU grep -P links the same library.
for p in 'alpha-[0-9]+' '(delta[0-9]+)(\s)' '(?<=row )([0-9]+)' '^row [0-9]+:'; do
    run grep -P -c "$p" big.txt
    run grep -P -o "$p" big.txt
done

echo "pcre2 workload done"
