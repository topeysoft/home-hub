#!/bin/bash -e
# Runs on the build host with the image's root at ${ROOTFS_DIR}. Bakes in which code the image carries
# (files/home-hub.conf, written by the workflow) so the chroot step can clone exactly that.
if [ ! -f files/home-hub.conf ]; then
	printf 'HOME_HUB_REF=main\nHOME_HUB_REPO=https://github.com/topeysoft/home-hub.git\n' > files/home-hub.conf
fi
install -m 644 files/home-hub.conf "${ROOTFS_DIR}/etc/home-hub.conf"
