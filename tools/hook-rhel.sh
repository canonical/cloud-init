#!/bin/sh
# Current versions of RHEL and CentOS do not honor the directory
# /etc/dhcp/dhclient-exit-hooks.d so this file can be placed in
# /etc/dhcp/dhclient.d instead

hook-rhel_config(){
    cloud-init dhclient-hook up "$interface"
}

hook-rhel_restore(){
    cloud-init dhclient-hook down "$interface"
}
