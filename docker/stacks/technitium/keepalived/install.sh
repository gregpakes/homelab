#!/usr/bin/env bash
#
# Install and configure keepalived for the Technitium DNS pair on this host.
#
#   sudo /opt/homelab/docker/stacks/technitium/keepalived/install.sh \
#     /opt/homelab/docker/hosts/dns1/keepalived.env
#
# Renders keepalived.conf from the template and the host's env file, validates it
# with `keepalived -t`, installs it with the health check, and reloads keepalived
# only when the config changed. Safe to re-run after every `git pull`.
#
# keepalived runs on the host rather than in the Portainer stack on purpose: it
# keeps running when Docker or the Technitium container restarts, so the health
# check fails and the VIP moves cleanly instead of being left on a dead node.
#
# While the env file says VIP_ENABLED=false, keepalived is configured but kept
# stopped. That is the state until cutover, because 172.16.51.67 is still held by
# the Pi-hole LoadBalancer in k3s - see ../README.md.

set -Eeuo pipefail

here=$(cd "$(dirname "$0")" && pwd)
env_file=${1:?usage: $0 <path to docker/hosts/<node>/keepalived.env>}

if [[ $EUID -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$env_file"
: "${NODE_NAME:?missing from $env_file}" "${NODE_IP:?missing from $env_file}" \
  "${PEER_IP:?missing from $env_file}" "${PRIORITY:?missing from $env_file}" \
  "${VIP:?missing from $env_file}" "${VIP_PREFIX:?missing from $env_file}" \
  "${VRID:?missing from $env_file}" "${VIP_ENABLED:?missing from $env_file}"

# The interface carrying NODE_IP. Finding none means this is the wrong env file
# for this host, so stop before configuring anything.
INTERFACE=${INTERFACE:-$(ip -o -4 addr show | awk -v ip="$NODE_IP" '{ split($4, a, "/") } a[1] == ip { print $2; exit }')}
if [[ -z $INTERFACE ]]; then
  echo "$NODE_IP is not configured on this host - wrong env file?" >&2
  exit 1
fi

missing=()
command -v keepalived >/dev/null || missing+=(keepalived)
command -v dig >/dev/null || missing+=(bind9-dnsutils)
if (( ${#missing[@]} )); then
  apt-get update
  apt-get install -y --no-install-recommends "${missing[@]}"
fi

# keepalived runs scripts as this user by default when it exists.
id keepalived_script >/dev/null 2>&1 ||
  useradd --system --no-create-home --shell /usr/sbin/nologin keepalived_script

install -d -m 755 /etc/keepalived
install -m 755 "$here/check_technitium.sh" /etc/keepalived/check_technitium.sh

rendered=$(mktemp)
trap 'rm -f "$rendered"' EXIT
sed -e "s|@NODE_NAME@|$NODE_NAME|g" \
    -e "s|@NODE_IP@|$NODE_IP|g" \
    -e "s|@PEER_IP@|$PEER_IP|g" \
    -e "s|@PRIORITY@|$PRIORITY|g" \
    -e "s|@VIP@|$VIP|g" \
    -e "s|@VIP_PREFIX@|$VIP_PREFIX|g" \
    -e "s|@VRID@|$VRID|g" \
    -e "s|@INTERFACE@|$INTERFACE|g" \
    "$here/keepalived.conf.tmpl" > "$rendered"

if ! keepalived -t -f "$rendered"; then
  echo "Rendered config failed validation; /etc/keepalived/keepalived.conf left as it was." >&2
  exit 1
fi

changed=false
if ! cmp -s "$rendered" /etc/keepalived/keepalived.conf; then
  install -m 644 "$rendered" /etc/keepalived/keepalived.conf
  changed=true
fi

if [[ $VIP_ENABLED == true ]]; then
  systemctl enable keepalived
  if ! systemctl is-active --quiet keepalived; then
    systemctl start keepalived
  elif [[ $changed == true ]]; then
    systemctl reload keepalived
  fi
  echo "keepalived running on $INTERFACE: $NODE_NAME priority $PRIORITY, VIP $VIP."
else
  systemctl disable --now keepalived
  echo "keepalived configured but stopped (VIP_ENABLED=false in $env_file)."
fi
