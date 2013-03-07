from tests.unittests import helpers

from cloudinit import mergers


class TestSimpleRun(helpers.MockerTestCase):
    def test_basic_merge(self):
        source = {
            'Blah': ['blah2'],
            'Blah3': 'c',
        }
        merge_with = {
            'Blah2': ['blah3'],
            'Blah3': 'b',
            'Blah': ['123'],
        }
        # Basic merge should not do thing special
        merge_how = "list()+dict()+str()"
        merger_set = mergers.string_extract_mergers(merge_how)
        self.assertEquals(3, len(merger_set))
        merger = mergers.construct(merger_set)
        merged = merger.merge(source, merge_with)
        self.assertEquals(merged['Blah'], ['blah2'])
        self.assertEquals(merged['Blah2'], ['blah3'])
        self.assertEquals(merged['Blah3'], 'c')

    def test_dict_overwrite(self):
        source = {
            'Blah': ['blah2'],
        }
        merge_with = {
            'Blah': ['123'],
        }
        # Now lets try a dict overwrite
        merge_how = "list()+dict(overwrite)+str()"
        merger_set = mergers.string_extract_mergers(merge_how)
        self.assertEquals(3, len(merger_set))
        merger = mergers.construct(merger_set)
        merged = merger.merge(source, merge_with)
        self.assertEquals(merged['Blah'], ['123'])

    def test_string_append(self):
        source = {
            'Blah': 'blah2',
        }
        merge_with = {
            'Blah': '345',
        }
        merge_how = "list()+dict()+str(append)"
        merger_set = mergers.string_extract_mergers(merge_how)
        self.assertEquals(3, len(merger_set))
        merger = mergers.construct(merger_set)
        merged = merger.merge(source, merge_with)
        self.assertEquals(merged['Blah'], 'blah2345')

    def test_list_extend(self):
        source = ['abc']
        merge_with = ['123']
        merge_how = "list(extend)+dict()+str()"
        merger_set = mergers.string_extract_mergers(merge_how)
        self.assertEquals(3, len(merger_set))
        merger = mergers.construct(merger_set)
        merged = merger.merge(source, merge_with)
        self.assertEquals(merged, ['abc', '123'])

    def test_deep_merge(self):
        source = {
            'a': [1, 'b', 2],
            'b': 'blahblah',
            'c': {
                'e': [1, 2, 3],
                'f': 'bigblobof',
                'iamadict': {
                    'ok': 'ok',
                }
            },
            'run': [
                'runme',
                'runme2',
            ],
            'runmereally': [
                'e', ['a'], 'd',
            ],
        }
        merge_with = {
            'a': ['e', 'f', 'g'],
            'b': 'more',
            'c': {
                'a': 'b',
                'f': 'stuff',
            },
            'run': [
                'morecmd',
                'moremoremore',
            ],
            'runmereally': [
                'blah', ['b'], 'e',
            ],
        }
        merge_how = "list(extend)+dict()+str(append)"
        merger_set = mergers.string_extract_mergers(merge_how)
        self.assertEquals(3, len(merger_set))
        merger = mergers.construct(merger_set)
        merged = merger.merge(source, merge_with)
        self.assertEquals(merged['a'], [1, 'b', 2, 'e', 'f', 'g'])
        self.assertEquals(merged['b'], 'blahblahmore')
        self.assertEquals(merged['c']['f'], 'bigblobofstuff')
        self.assertEquals(merged['run'], ['runme', 'runme2', 'morecmd',
                                          'moremoremore'])
        self.assertEquals(merged['runmereally'], ['e', ['a'], 'd', 'blah',
                                                  ['b'], 'e'])

    def test_dict_overwrite_layered(self):
        source = {
            'Blah3': {
                'f': '3',
                'g': {
                    'a': 'b',
                }
            }
        }
        merge_with = {
            'Blah3': {
                'e': '2',
                'g': {
                    'e': 'f',
                }
            }
        }
        merge_how = "list()+dict()+str()"
        merger_set = mergers.string_extract_mergers(merge_how)
        self.assertEquals(3, len(merger_set))
        merger = mergers.construct(merger_set)
        merged = merger.merge(source, merge_with)
        self.assertEquals(merged['Blah3'], {
                'e': '2',
                'f': '3',
                'g': {
                    'a': 'b',
                    'e': 'f',
                }
        })

