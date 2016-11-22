# Copyright (C) 2015 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy


class DictRegistry(object):
    """A simple registry for a mapping of objects."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._items = {}

    def register_item(self, key, item):
        """Add item to the registry."""
        if key in self._items:
            raise ValueError(
                'Item already registered with key {0}'.format(key))
        self._items[key] = item

    def unregister_item(self, key, force=True):
        """Remove item from the registry."""
        if key in self._items:
            del self._items[key]
        elif not force:
            raise KeyError("%s: key not present to unregister" % key)

    @property
    def registered_items(self):
        """All the items that have been registered.

        This cannot be used to modify the contents of the registry.
        """
        return copy.copy(self._items)

# vi: ts=4 expandtab
