#!/usr/bin/sh
set -ex
if [ -z "${AUTOPKGTEST_REBOOT_MARK}" ]; then
    cloud-init status --format yaml
    # Setup cloud-init clean to ensure no cache present due to test image setup
    cloud-init clean -c all
    /tmp/autopkgtest-reboot a-non-empty-marker-value
else
    cloud-init status --wait
    cloud-init status --format yaml
    cloud-init status --format json
fi
