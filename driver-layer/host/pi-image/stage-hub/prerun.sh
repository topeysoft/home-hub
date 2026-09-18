#!/bin/bash -e
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
# pi-gen convention: start this stage from the previous stage's root filesystem.
if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
