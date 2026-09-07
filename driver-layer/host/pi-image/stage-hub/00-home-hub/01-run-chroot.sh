#!/bin/bash -e
# Runs inside the image. The code, Docker and the first-boot unit go in now; containers are pulled on the
# first boot, when there is a network and a running Docker daemon.
# shellcheck disable=SC1091
. /etc/home-hub.conf
REF="${HOME_HUB_REF:-main}"
REPO="${HOME_HUB_REPO:-https://github.com/topeysoft/home-hub.git}"

git clone --depth 1 --branch "$REF" "$REPO" /opt/home-hub
chmod +x /opt/home-hub/install.sh /opt/home-hub/driver-layer/radios.sh /opt/home-hub/driver-layer/host/firstboot.sh

# get.docker.com ends by starting the daemon, which cannot happen in a chroot; the packages are what matter.
curl -fsSL https://get.docker.com | sh || true
command -v docker >/dev/null || { echo "docker did not install"; exit 1; }

install -m 644 /opt/home-hub/driver-layer/host/home-hub-firstboot.service /etc/systemd/system/home-hub-firstboot.service
systemctl enable docker avahi-daemon home-hub-firstboot
