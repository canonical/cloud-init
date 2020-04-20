# Copyright (C) 2015 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


def compose_udev_equality(key, value):
    """Return a udev comparison clause, like `ACTION=="add"`."""
    assert key == key.upper()
    return '%s=="%s"' % (key, value)


def compose_udev_attr_equality(attribute, value):
    """Return a udev attribute comparison clause, like `ATTR{type}=="1"`."""
    assert attribute == attribute.lower()
    return 'ATTR{%s}=="%s"' % (attribute, value)


def compose_udev_setting(key, value):
    """Return a udev assignment clause, like `NAME="eth0"`."""
    assert key == key.upper()
    return '%s="%s"' % (key, value)


def generate_udev_rule(interface, mac, driver=None):
    """Return a udev rule to set the name of network interface with `mac`.

    The rule ends up as a single line looking something like:

    SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*",
    ATTR{address}="ff:ee:dd:cc:bb:aa", NAME="eth0"
    """
    if not driver:
        driver = '?*'

    rule = ', '.join([
        compose_udev_equality('SUBSYSTEM', 'net'),
        compose_udev_equality('ACTION', 'add'),
        compose_udev_equality('DRIVERS', driver),
        compose_udev_attr_equality('address', mac),
        compose_udev_setting('NAME', interface),
    ])
    return '%s\n' % rule

# vi: ts=4 expandtab syntax=python
