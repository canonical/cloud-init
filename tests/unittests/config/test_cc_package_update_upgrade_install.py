import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestPackageUpdateUpgradeSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # packages list with single entry (2 required)
            ({"packages": ["p1", ["p2"]]}, ""),
            # packages list with three entries (2 required)
            ({"packages": ["p1", ["p2", "p3", "p4"]]}, ""),
            # empty packages list
            ({"packages": []}, "is too short"),
            (
                {"apt_update": False},
                (
                    "deprecations: apt_update: DEPRECATED."
                    " Dropped after April 2027. Use ``package_update``."
                    " Default: ``false``"
                ),
            ),
            (
                {"apt_upgrade": False},
                (
                    "deprecations: apt_upgrade: DEPRECATED."
                    " Dropped after April 2027. Use ``package_upgrade``."
                    " Default: ``false``"
                ),
            ),
            (
                {"apt_reboot_if_required": False},
                (
                    "deprecations: apt_reboot_if_required: DEPRECATED."
                    " Dropped after April 2027."
                    " Use ``package_reboot_if_required``. Default: ``false``"
                ),
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
