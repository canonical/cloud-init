# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.tests import helpers

from cloudinit.handlers import cloud_config
from cloudinit.handlers import (CONTENT_START, CONTENT_END)

from cloudinit import helpers as c_helpers
from cloudinit import util

import collections
import glob
import os
import random
import re
import six
import string

SOURCE_PAT = "source*.*yaml"
EXPECTED_PAT = "expected%s.yaml"
TYPES = [dict, str, list, tuple, None]
TYPES.extend(six.integer_types)


def _old_mergedict(src, cand):
    """
    Merge values from C{cand} into C{src}.
    If C{src} has a key C{cand} will not override.
    Nested dictionaries are merged recursively.
    """
    if isinstance(src, dict) and isinstance(cand, dict):
        for (k, v) in cand.items():
            if k not in src:
                src[k] = v
            else:
                src[k] = _old_mergedict(src[k], v)
    return src


def _old_mergemanydict(*args):
    out = {}
    for a in args:
        out = _old_mergedict(out, a)
    return out


def _random_str(rand):
    base = ''
    for _i in range(rand.randint(1, 2 ** 8)):
        base += rand.choice(string.ascii_letters + string.digits)
    return base


class _NoMoreException(Exception):
    pass


def _make_dict(current_depth, max_depth, rand):
    if current_depth >= max_depth:
        raise _NoMoreException()
    if current_depth == 0:
        t = dict
    else:
        t = rand.choice(TYPES)
    base = None
    if t in [None]:
        return base
    if t in [dict, list, tuple]:
        if t in [dict]:
            amount = rand.randint(0, 5)
            keys = [_random_str(rand) for _i in range(0, amount)]
            base = {}
            for k in keys:
                try:
                    base[k] = _make_dict(current_depth + 1, max_depth, rand)
                except _NoMoreException:
                    pass
        elif t in [list, tuple]:
            base = []
            amount = rand.randint(0, 5)
            for _i in range(0, amount):
                try:
                    base.append(_make_dict(current_depth + 1, max_depth, rand))
                except _NoMoreException:
                    pass
            if t in [tuple]:
                base = tuple(base)
    elif t in six.integer_types:
        base = rand.randint(0, 2 ** 8)
    elif t in [str]:
        base = _random_str(rand)
    return base


def make_dict(max_depth, seed=None):
    max_depth = max(1, max_depth)
    rand = random.Random(seed)
    return _make_dict(0, max_depth, rand)


class TestSimpleRun(helpers.ResourceUsingTestCase):
    def _load_merge_files(self):
        merge_root = helpers.resourceLocation('merge_sources')
        tests = []
        source_ids = collections.defaultdict(list)
        expected_files = {}
        for fn in glob.glob(os.path.join(merge_root, SOURCE_PAT)):
            base_fn = os.path.basename(fn)
            file_id = re.match(r"source(\d+)\-(\d+)[.]yaml", base_fn)
            if not file_id:
                raise IOError("File %s does not have a numeric identifier"
                              % (fn))
            file_id = int(file_id.group(1))
            source_ids[file_id].append(fn)
            expected_fn = os.path.join(merge_root, EXPECTED_PAT % (file_id))
            if not os.path.isfile(expected_fn):
                raise IOError("No expected file found at %s" % (expected_fn))
            expected_files[file_id] = expected_fn
        for i in sorted(source_ids.keys()):
            source_file_contents = []
            for fn in sorted(source_ids[i]):
                source_file_contents.append([fn, util.load_file(fn)])
            expected = util.load_yaml(util.load_file(expected_files[i]))
            entry = [source_file_contents, [expected, expected_files[i]]]
            tests.append(entry)
        return tests

    def test_seed_runs(self):
        test_dicts = []
        for i in range(1, 10):
            base_dicts = []
            for j in range(1, 10):
                base_dicts.append(make_dict(5, i * j))
            test_dicts.append(base_dicts)
        for test in test_dicts:
            c = _old_mergemanydict(*test)
            d = util.mergemanydict(test)
            self.assertEqual(c, d)

    def test_merge_cc_samples(self):
        tests = self._load_merge_files()
        paths = c_helpers.Paths({})
        cc_handler = cloud_config.CloudConfigPartHandler(paths)
        cc_handler.cloud_fn = None
        for (payloads, (expected_merge, expected_fn)) in tests:
            cc_handler.handle_part(None, CONTENT_START, None,
                                   None, None, None)
            merging_fns = []
            for (fn, contents) in payloads:
                cc_handler.handle_part(None, None, "%s.yaml" % (fn),
                                       contents, None, {})
                merging_fns.append(fn)
            merged_buf = cc_handler.cloud_buf
            cc_handler.handle_part(None, CONTENT_END, None,
                                   None, None, None)
            fail_msg = "Equality failure on checking %s with %s: %s != %s"
            fail_msg = fail_msg % (expected_fn,
                                   ",".join(merging_fns), merged_buf,
                                   expected_merge)
            self.assertEqual(expected_merge, merged_buf, msg=fail_msg)

    def test_compat_merges_dict(self):
        a = {
            '1': '2',
            'b': 'c',
        }
        b = {
            'b': 'e',
        }
        c = _old_mergedict(a, b)
        d = util.mergemanydict([a, b])
        self.assertEqual(c, d)

    def test_compat_merges_dict2(self):
        a = {
            'Blah': 1,
            'Blah2': 2,
            'Blah3': 3,
        }
        b = {
            'Blah': 1,
            'Blah2': 2,
            'Blah3': [1],
        }
        c = _old_mergedict(a, b)
        d = util.mergemanydict([a, b])
        self.assertEqual(c, d)

    def test_compat_merges_list(self):
        a = {'b': [1, 2, 3]}
        b = {'b': [4, 5]}
        c = {'b': [6, 7]}
        e = _old_mergemanydict(a, b, c)
        f = util.mergemanydict([a, b, c])
        self.assertEqual(e, f)

    def test_compat_merges_str(self):
        a = {'b': "hi"}
        b = {'b': "howdy"}
        c = {'b': "hallo"}
        e = _old_mergemanydict(a, b, c)
        f = util.mergemanydict([a, b, c])
        self.assertEqual(e, f)

    def test_compat_merge_sub_dict(self):
        a = {
            '1': '2',
            'b': {
                'f': 'g',
                'e': 'c',
                'h': 'd',
                'hh': {
                    '1': 2,
                },
            }
        }
        b = {
            'b': {
                'e': 'c',
                'hh': {
                    '3': 4,
                }
            }
        }
        c = _old_mergedict(a, b)
        d = util.mergemanydict([a, b])
        self.assertEqual(c, d)

    def test_compat_merge_sub_dict2(self):
        a = {
            '1': '2',
            'b': {
                'f': 'g',
            }
        }
        b = {
            'b': {
                'e': 'c',
            }
        }
        c = _old_mergedict(a, b)
        d = util.mergemanydict([a, b])
        self.assertEqual(c, d)

    def test_compat_merge_sub_list(self):
        a = {
            '1': '2',
            'b': {
                'f': ['1'],
            }
        }
        b = {
            'b': {
                'f': [],
            }
        }
        c = _old_mergedict(a, b)
        d = util.mergemanydict([a, b])
        self.assertEqual(c, d)

# vi: ts=4 expandtab
