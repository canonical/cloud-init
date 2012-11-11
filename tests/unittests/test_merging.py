from mocker import MockerTestCase

from cloudinit import util


class TestMergeDict(MockerTestCase):
    def test_simple_merge(self):
        """Test simple non-conflict merge."""
        source = {"key1": "value1"}
        candidate = {"key2": "value2"}
        result = util.mergedict(source, candidate)
        self.assertEqual({"key1": "value1", "key2": "value2"}, result)

    def test_nested_merge(self):
        """Test nested merge."""
        source = {"key1": {"key1.1": "value1.1"}}
        candidate = {"key1": {"key1.2": "value1.2"}}
        result = util.mergedict(source, candidate)
        self.assertEqual(
            {"key1": {"key1.1": "value1.1", "key1.2": "value1.2"}}, result)

    def test_merge_does_not_override(self):
        """Test that candidate doesn't override source."""
        source = {"key1": "value1", "key2": "value2"}
        candidate = {"key1": "value2", "key2": "NEW VALUE"}
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_empty_candidate(self):
        """Test empty candidate doesn't change source."""
        source = {"key": "value"}
        candidate = {}
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_empty_source(self):
        """Test empty source is replaced by candidate."""
        source = {}
        candidate = {"key": "value"}
        result = util.mergedict(source, candidate)
        self.assertEqual(candidate, result)

    def test_non_dict_candidate(self):
        """Test non-dict candidate is discarded."""
        source = {"key": "value"}
        candidate = "not a dict"
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_non_dict_source(self):
        """Test non-dict source is not modified with a dict candidate."""
        source = "not a dict"
        candidate = {"key": "value"}
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_neither_dict(self):
        """Test if neither candidate or source is dict source wins."""
        source = "source"
        candidate = "candidate"
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)
