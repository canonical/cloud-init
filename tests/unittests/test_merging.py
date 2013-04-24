from tests.unittests import helpers

from cloudinit.handlers import cloud_config
from cloudinit.handlers import (CONTENT_START, CONTENT_END)

from cloudinit import helpers as c_helpers
from cloudinit import util

import collections
import glob
import os
import re


class TestSimpleRun(helpers.ResourceUsingTestCase):
    def _load_merge_files(self, data_dir):
        merge_root = self.resourceLocation(data_dir)
        tests = []
        source_ids = collections.defaultdict(list)
        expected_files = {}
        for fn in glob.glob(os.path.join(merge_root, "source*.*yaml")):
            base_fn = os.path.basename(fn)
            file_id = re.match(r"source(\d+)\-(\d+)[.]yaml", base_fn)
            if not file_id:
                raise IOError("File %s does not have a numeric identifier"
                              % (fn))
            file_id = int(file_id.group(1))
            source_ids[file_id].append(fn)
            expected_fn = os.path.join(merge_root,
                                       "expected%s.yaml" % (file_id))
            if not os.path.isfile(expected_fn):
                raise IOError("No expected file found at %s" % (expected_fn))
            expected_files[file_id] = expected_fn
        for id in sorted(source_ids.keys()):
            source_file_contents = []
            for fn in sorted(source_ids[id]):
                source_file_contents.append(util.load_file(fn))
            expected = util.load_yaml(util.load_file(expected_files[id]))
            tests.append((source_file_contents, expected))
        return tests

    def test_merge_samples(self):
        tests = self._load_merge_files('merge_sources')
        paths = c_helpers.Paths({})
        cc_handler = cloud_config.CloudConfigPartHandler(paths)
        cc_handler.cloud_fn = None
        for (payloads, expected_merge) in tests:
            cc_handler.handle_part(None, CONTENT_START, None,
                                   None, None, None)
            for (i, p) in enumerate(payloads):
                cc_handler.handle_part(None, None, "t-%s.yaml" % (i + 1),
                                       p, None, {})
            merged_buf = cc_handler.cloud_buf
            cc_handler.handle_part(None, CONTENT_END, None,
                                   None, None, None)
            self.assertEquals(expected_merge, merged_buf)
