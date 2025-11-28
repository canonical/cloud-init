# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit.registry import DictRegistry


class TestDictRegistry:
    def test_added_item_included_in_output(self):
        registry = DictRegistry()
        item_key, item_to_register = "test_key", mock.Mock()
        registry.register_item(item_key, item_to_register)
        assert {item_key: item_to_register} == registry.registered_items

    def test_registry_starts_out_empty(self):
        assert {} == DictRegistry().registered_items

    def test_modifying_registered_items_isnt_exposed_to_other_callers(self):
        registry = DictRegistry()
        registry.registered_items["test_item"] = mock.Mock()
        assert {} == registry.registered_items

    def test_keys_cannot_be_replaced(self):
        registry = DictRegistry()
        item_key = "test_key"
        registry.register_item(item_key, mock.Mock())

        with pytest.raises(ValueError):
            registry.register_item(item_key, mock.Mock())
