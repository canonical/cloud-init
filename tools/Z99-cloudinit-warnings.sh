#!/bin/sh
# This file is part of cloud-init. See LICENSE file for license information.

# Purpose: show user warnings on login.

cloud_init_warnings() {
    local warning="" idir="/var/lib/cloud/instance" n=0
    local warndir="$idir/warnings"
    local ufile="$HOME/.cloud-warnings.skip" sfile="$warndir/.skip"
    [ -d "$warndir" ] || return 0
    [ ! -f "$ufile" ] || return 0
    [ ! -f "$sfile" ] || return 0

    for warning in "$warndir"/*; do
        [ -f "$warning" ] || continue
        cat "$warning"
        n=$((n+1))
    done
    [ $n -eq 0 ] && return 0
    echo ""
    echo "Disable the warnings above by:"
    echo "  touch $ufile"
    echo "or"
    echo "  touch $sfile"
}

cloud_init_warnings 1>&2
unset cloud_init_warnings

# vi: syntax=sh ts=4 expandtab
