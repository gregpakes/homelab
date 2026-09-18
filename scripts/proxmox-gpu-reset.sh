#!/usr/bin/env bash
#
# Proxmox hookscript: force a clean reset of a passed-through Intel Arc GPU
# before the VM starts.
#
# Why this exists
# ---------------
# The Arc A310 does not reliably return to a usable state when a VM that has
# already initialised it is restarted. The card holds its previous state across
# the QEMU process exiting, so the next guest's i915 finds local memory already
# claimed and bails out:
#
#   i915 0000:01:00.0: [drm] *ERROR* LMEM not initialized by firmware
#   i915 0000:01:00.0: Device initialization failed (-19)
#
# or, when the card is wedged harder, stops responding on the bus entirely:
#
#   i915 0000:01:00.0: [drm] *ERROR* Device is non-operational; MMIO access returns 0xFFFFFFFF!
#   i915 0000:01:00.0: Device initialization failed (-5)
#
# The guest then has no /dev/dri, which breaks any workload mounting it
# (tdarr-node, plex). Confirmed to survive both `qm reboot` and a full
# `qm stop` + `qm start`, so a fresh QEMU process is not enough on its own.
#
# The reset method matters (2026-09-18)
# -------------------------------------
# An earlier version of this script triggered the device's default reset, which
# for these cards is FLR (function-level reset), and then removed/rescanned the
# PCI bus. That is NOT sufficient: all three A310s were found wedged with the
# errors above despite this script having been installed since 2026-08-09.
# Arc cards do not honour FLR - the kernel reports success while the card's
# firmware never re-runs its init.
#
# Writing "bus" to the device's reset_method first forces a secondary bus reset
# (SBR), which does recover the card. Verified on k3s-04 (VM 204): a wedged card
# returning MMIO 0xFFFFFFFF came back with card0 + renderD128 and
# "GT0: HuC: authenticated for all workloads" after a bus reset.
#
# The kernel only advertises "bus" in reset_method when the device is alone on
# its parent bus, so this cannot disturb a neighbouring device. Where it is not
# offered, the script silently falls back to the default method.
#
# reset_method does not persist: removing and rescanning the device recreates
# the sysfs node with the default. That is precisely why this belongs in the
# pre-start hook rather than being set once by hand.
#
# Install
# -------
#   scp scripts/proxmox-gpu-reset.sh root@proxmox-0X.local:/var/lib/vz/snippets/gpu-reset.sh
#   chmod +x /var/lib/vz/snippets/gpu-reset.sh
#   qm set <vmid> --hookscript local:snippets/gpu-reset.sh
#
# /var/lib/vz/snippets is local to each host, so install on all three. Copy by IP:
# DNS resolves the k3s guests but not the hypervisors, and their mDNS .local
# names stall from a workstation. Root ssh is password auth.
#
#   host         mgmt IP         GPU VM   guest    GPU slot (host-side)
#   proxmox-01   172.16.250.10   204      k3s-04   0000:0a:00
#   proxmox-02   172.16.250.11   205      k3s-05   0000:0a:00
#   proxmox-03   172.16.250.12   206      k3s-06   0000:0b:00.0
#
# The GPU's PCI address differs per host, so this script does NOT hardcode one.
# It finds display-class devices (PCI class 0x03xxxx) that are bound to
# vfio-pci - i.e. cards set aside for passthrough - and resets every function of
# those slots. Anything the host itself is using is never touched, so a wrong
# address cannot take out a NIC or a storage controller.
#
# Override with GPU_SLOTS only if autodetection picks the wrong card:
#   GPU_SLOTS="0000:04:00" qm start <vmid>

set -euo pipefail

VMID="$1"
PHASE="$2"

log() { echo "[gpu-reset][vm ${VMID}] $*"; }

# Echoes the slot address (no function suffix) of every display device bound to
# vfio-pci, deduplicated.
detect_gpu_slots() {
  local dev class driver
  for dev in /sys/bus/pci/devices/*; do
    [[ -r "${dev}/class" ]] || continue
    class="$(cat "${dev}/class")"
    # 0x03xxxx == display controller (VGA, 3D, other display)
    [[ "${class}" == 0x03* ]] || continue
    driver="$(basename "$(readlink -f "${dev}/driver" 2>/dev/null || echo none)")"
    [[ "${driver}" == "vfio-pci" ]] || continue
    basename "${dev}" | sed 's/\.[0-9a-f]*$//'
  done | sort -u
}

# Prefer a secondary bus reset over the default FLR - see the header. Returns
# non-zero when the kernel does not offer "bus" for this device, in which case
# the caller just uses whatever the default is.
prefer_bus_reset() {
  local dev="$1"
  local method_file="/sys/bus/pci/devices/${dev}/reset_method"

  [[ -w "${method_file}" ]] || return 1
  grep -qw bus "${method_file}" || return 1
  echo bus > "${method_file}" 2>/dev/null || return 1
}

reset_gpu() {
  local slot dev present=() slots=()

  if [[ -n "${GPU_SLOTS:-}" ]]; then
    read -r -a slots <<< "${GPU_SLOTS}"
    log "using GPU_SLOTS override: ${slots[*]}"
  else
    mapfile -t slots < <(detect_gpu_slots)
  fi

  if [[ ${#slots[@]} -eq 0 ]]; then
    log "ERROR no display device bound to vfio-pci found - is the GPU still bound? check 'lspci -nnk | grep -A3 -i vga'"
    return 0
  fi

  for slot in "${slots[@]}"; do
    for dev in /sys/bus/pci/devices/"${slot}".*; do
      [[ -e "${dev}" ]] || continue
      present+=("$(basename "${dev}")")
    done
  done

  if [[ ${#present[@]} -eq 0 ]]; then
    log "ERROR no PCI functions found for slots: ${slots[*]}"
    return 0
  fi

  log "resetting ${#present[@]} function(s) of ${slots[*]}: ${present[*]}"

  # Try an in-place reset first. This is enough when the card is merely dirty
  # rather than wedged, and avoids disturbing the bus.
  for dev in "${present[@]}"; do
    if [[ -w "/sys/bus/pci/devices/${dev}/reset" ]]; then
      if prefer_bus_reset "${dev}"; then
        log "reset_method for ${dev} set to bus"
      else
        log "WARNING bus reset unavailable for ${dev} - falling back to the default method, which Arc cards may ignore"
      fi
      if echo 1 > "/sys/bus/pci/devices/${dev}/reset" 2>/dev/null; then
        log "reset ${dev}"
      else
        log "reset of ${dev} refused (likely in use) - falling back to remove/rescan"
      fi
    fi
  done

  # Remove and re-enumerate. The vfio-pci ids= binding in
  # /etc/modprobe.d/vfio.conf reclaims the device on rescan.
  for dev in "${present[@]}"; do
    log "removing ${dev} from the PCI bus"
    echo 1 > "/sys/bus/pci/devices/${dev}/remove"
  done

  sleep 1
  log "rescanning PCI bus"
  echo 1 > /sys/bus/pci/rescan
  sleep 2

  for dev in "${present[@]}"; do
    if [[ -e "/sys/bus/pci/devices/${dev}" ]]; then
      log "${dev} back on the bus, driver: $(basename "$(readlink -f "/sys/bus/pci/devices/${dev}/driver" 2>/dev/null || echo none)")"
    else
      log "ERROR ${dev} did not come back after rescan"
    fi
  done
}

case "${PHASE}" in
  pre-start)
    reset_gpu
    ;;
  post-start | pre-stop | post-stop)
    :
    ;;
  *)
    log "unknown phase ${PHASE}"
    exit 1
    ;;
esac
