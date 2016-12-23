#!/bin/sh
# This file is part of cloud-init. See LICENSE file for license information.

# Current versions of RHEL and CentOS do not honor the directory
# /etc/dhcp/dhclient-exit-hooks.d so this file can be placed in
# /etc/dhcp/dhclient.d instead
is_azure() {
    local dmi_path="/sys/class/dmi/id/board_vendor" vendor=""
    if [ -e "$dmi_path" ] && read vendor < "$dmi_path"; then
        [ "$vendor" = "Microsoft Corporation" ] && return 0
    fi
    return 1
}

is_enabled() {
    # only execute hooks if cloud-init is enabled and on azure
    [ -e /run/cloud-init/enabled ] || return 1
    is_azure
}

hook-rhel_config(){
    is_enabled || return 0
    cloud-init dhclient-hook up "$interface"
}

hook-rhel_restore(){
    is_enabled || return 0
    cloud-init dhclient-hook down "$interface"
}
