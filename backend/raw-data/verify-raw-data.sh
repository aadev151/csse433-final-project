#!/usr/bin/env bash

set -e

echo "Verifying that all raw Data files are Correct"

command sha256sum -c ETHUSD-trades-2026-10-09.zip.CHECKSUM >/dev/null 2>&1
command sha256sum -c ETHUSD-trades-2026-10-10.zip.CHECKSUM >/dev/null 2>&1
command sha256sum -c ETHUSD-trades-2026-10-11.zip.CHECKSUM >/dev/null 2>&1
command sha256sum -c ETHUSD-trades-2026-10-12.zip.CHECKSUM >/dev/null 2>&1
command sha256sum -c ETHUSD-trades-2026-10-13.zip.CHECKSUM >/dev/null 2>&1
command sha256sum -c ETHUSD-trades-2026-10-14.zip.CHECKSUM >/dev/null 2>&1
command sha256sum -c ETHUSD-trades-2026-10-15.zip.CHECKSUM >/dev/null 2>&1