# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.registry import DictRegistry

from cloudinit.tests.helpers import (mock, TestCase)


class TestDictRegistry(TestCase):

    def test_added_item_included_in_output(self):
        registry = DictRegistry()
        item_key, item_to_register = 'test_key', mock.Mock()
        registry.register_item(item_key, item_to_register)
        self.assertEqual({item_key: item_to_register},
                         registry.registered_items)

    def test_registry_starts_out_empty(self):
        self.assertEqual({}, DictRegistry().registered_items)

    def test_modifying_registered_items_isnt_exposed_to_other_callers(self):
        registry = DictRegistry()
        registry.registered_items['test_item'] = mock.Mock()
        self.assertEqual({}, registry.registered_items)

    def test_keys_cannot_be_replaced(self):
        registry = DictRegistry()
        item_key = 'test_key'
        registry.register_item(item_key, mock.Mock())
        self.assertRaises(ValueError,
                          registry.register_item, item_key, mock.Mock())

# vi: ts=4 expandtab
