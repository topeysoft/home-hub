#!/usr/bin/env bash
# The hub's first boot, for a box that was flashed rather than installed: the Home Hub image for a
# Pi, or any machine where someone dropped this unit in. Runs once (home-hub-firstboot.service),
# leaves a mark, and never runs again. Everything Pi-specific lives here, not in install.sh, so the
# install script stays the same on a NUC, a VM, or any Debian or Fedora box.
#
#   1. On a Pi 5: bring the bootloader current and make sure PCIe is on, so an NVMe on any base works.
#   2. On a Pi 5 that booted from SD with an empty NVMe attached: copy itself to the NVMe and reboot
#      from it (HUB_AUTO_NVME=0 in /etc/home-hub.conf turns this off).
#   3. Run install.sh, which does everything a hand install would.
set -euo pipefail
MARK=/var/lib/home-hub/firstboot.done
DIR="${HOME_HUB_DIR:-/opt/home-hub}"
[ -f /etc/home-hub.conf ] && . /etc/home-hub.conf
[ -f "$MARK" ] && exit 0
mkdir -p "$(dirname "$MARK")"
log() { printf '[home-hub] %s\n' "$*"; }

is_pi5() { grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; }
booted_from_sd() { findmnt -no SOURCE / | grep -q mmcblk; }
nvme_empty() { [ -b /dev/nvme0n1 ] && [ -z "$(lsblk -no NAME /dev/nvme0n1 | tail -n +2)" ]; }

if is_pi5; then
  log "Raspberry Pi 5: bootloader and PCIe"
  rpi-eeprom-update -a >/dev/null 2>&1 || true
  CFG=/boot/firmware/config.txt
  if [ -f "$CFG" ] && ! grep -q '^dtparam=pciex1' "$CFG" && [ ! -d /proc/device-tree/hat ]; then
    printf '\n# home-hub: NVMe on a base without a HAT EEPROM\ndtparam=pciex1\n' >> "$CFG"    # harmless with nothing attached
    log "enabled PCIe in config.txt (takes effect on the next boot)"
  fi
  if [ "${HUB_AUTO_NVME:-1}" = "1" ] && booted_from_sd && nvme_empty; then
    log "empty NVMe found while running from SD: copying the system across, then rebooting from it"
    if ! command -v rpi-clone >/dev/null 2>&1; then
      curl -fsSL https://raw.githubusercontent.com/geerlingguy/rpi-clone/master/install | bash >/dev/null 2>&1 || true
    fi
    if command -v rpi-clone >/dev/null 2>&1 && rpi-clone -U nvme0n1 >/dev/null 2>&1; then
      touch "$MARK"                     # this SD is done; the NVMe copy has no mark yet and finishes the job
      log "copied; rebooting from the NVMe"
      reboot; exit 0
    fi
    log "could not copy to the NVMe; carrying on from the SD card"
  fi
fi

log "installing the hub"
if [ -x "$DIR/install.sh" ]; then
  HOME_HUB_DIR="$DIR" "$DIR/install.sh"
else
  curl -fsSL https://raw.githubusercontent.com/topeysoft/home-hub/main/install.sh | HOME_HUB_DIR="$DIR" bash
fi
touch "$MARK"
log "done"
