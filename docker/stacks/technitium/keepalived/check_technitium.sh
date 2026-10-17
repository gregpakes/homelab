#!/bin/sh
# keepalived health check: is the Technitium on this host answering DNS?
#
# Asks for `localhost`, which Technitium answers authoritatively from its own
# built-in zone. That tests this node only - an upstream or internet outage can't
# fail the check on both nodes at once and take the VIP away entirely.

out=$(dig +norecurse +time=1 +tries=1 @127.0.0.1 localhost A 2>/dev/null) || exit 1

printf '%s\n' "$out" | grep -q 'status: NOERROR' || exit 1
printf '%s\n' "$out" | grep -Eq '^;; flags:[^;]* aa[ ;]'
