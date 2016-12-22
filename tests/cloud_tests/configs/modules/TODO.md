# TODO

The following lists complete or partially misisng modules. If a module is
listed with nothing below it indicates that no work is completed on that
module. If there is a list below the module name that is the remainig
identified work.

## apt_configure

  * apt_get_wrapper
    * What does this do? How to use it?
  * apt_get_command
    * To specify a different 'apt-get' command, set 'apt_get_command'.
    This must be a list, and the subcommand (update, upgrade) is appended to it.
    * Modify default and verify the options got passed correctly.
  * preserve sources
    * TBD

## chef
2016-11-17: Tests took > 60 seconds and test framework times out currently.

## disable EC2 metadata

## disk setup

## emit upstart

## fan

## growpart

## grub dpkg

## landscape
2016-11-17: Module is not working

## lxd
2016-11-17: Need a zfs backed test written

## mcollective

## migrator

## mounts

## phone home

## power state change

## puppet
2016-11-17: Tests took > 60 seconds and test framework times out currently.

## resizefs

## resolv conf
2016-11-17: Issues with changing resolv.conf and lxc backend.

## redhat subscription
2016-11-17: Need RH support in test framework.

## rightscale userdata
2016-11-17: Specific to RightScale cloud enviornment.

## rsyslog

## scripts per boot
Not applicable to write a test for this as it specifies when something should be run.

## scripts per instance
Not applicable to write a test for this as it specifies when something should be run.

## scripts per once
Not applicable to write a test for this as it specifies when something should be run.

## scripts user
Not applicable to write a test for this as it specifies when something should be run.

## scripts vendor
Not applicable to write a test for this as it specifies when something should be run.

## snappy
2016-11-17: Need test to install snaps from store

## snap-config
2016-11-17: Need to investigate

## spacewalk

## ssh authkey fingerprints
The authkey_hash key does not appear to work. In fact the default claims to be md5, however syslog only shows sha256

## ubuntu init switch

## update etc hosts
2016-11-17: Issues with changing /etc/hosts and lxc backend.

## yum add repo
2016-11-17: Need RH support in test framework.

# vi: ts=4 expandtab
