#!/bin/bash -e
# pi-gen convention: start this stage from the previous stage's root filesystem.
if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
