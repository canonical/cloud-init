# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import skipUnlessJsonSchema


@skipUnlessJsonSchema()
class TestCCNetplanNmPatch:
    def test_schema_validation(self):
        pass
