from unittest import TestCase

from cloudinit.util import mergedict

class TestMergeDict(TestCase):
    def test_simple_merge(self):
        source = {"key1": "value1"}
        candidate = {"key2": "value2"}
        result = mergedict(source, candidate)
        self.assertEqual({"key1": "value1", "key2": "value2"}, result)

    def test_nested_merge(self):
        source = {"key1": {"key1.1": "value1.1"}}
        candidate = {"key1": {"key1.2": "value1.2"}}
        result = mergedict(source, candidate)
        self.assertEqual(
            {"key1": {"key1.1": "value1.1", "key1.2": "value1.2"}}, result)

    def test_merge_does_not_override(self):
        source = {"key1": "value1", "key2": "value2"}
        candidate = {"key2": "value2", "key2": "NEW VALUE"}
        result = mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_empty_candidate(self):
        source = {"key": "value"}
        candidate = {}
        result = mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_empty_source(self):
        source = {}
        candidate = {"key": "value"}
        result = mergedict(source, candidate)
        self.assertEqual(candidate, result)

    def test_non_dict_candidate(self):
        source = {"key": "value"}
        candidate = "not a dict"
        result = mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_non_dict_source(self):
        source = "not a dict"
        candidate = {"key": "value"}
        result = mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_neither_dict(self):
        source = "source"
        candidate = "candidate"
        result = mergedict(source, candidate)
        self.assertEqual(source, result)
