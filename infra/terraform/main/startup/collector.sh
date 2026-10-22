#!/bin/bash
# GCE startup script for the collector VM: runs as root at every boot.
# Keeps the vendor library's telemetry and ads host unreachable. PyPI quarantined vnstock and
# vnai on 2026-09-24; read in their source, they report usage to this host every 300 s. The
# licence host (vnstocks.com) is left alone. Idempotent: the line is added once.
set -euo pipefail
line='0.0.0.0 hq.vnstocks.com'
grep -qxF "$line" /etc/hosts || printf '%s\n' "$line" >> /etc/hosts
