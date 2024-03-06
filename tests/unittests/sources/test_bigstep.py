import json
import os

import pytest
import responses

from cloudinit import helpers
from cloudinit.sources import DataSourceBigstep as bigstep
from tests.unittests.helpers import mock

M_PATH = "cloudinit.sources.DataSourceBigstep."

IMDS_URL = "http://bigstep.com"
METADATA_BODY = json.dumps(
    {
        "metadata": "metadata",
        "vendordata_raw": "vendordata_raw",
        "userdata_raw": "userdata_raw",
    }
)


class TestBigstep:
    @pytest.mark.parametrize("custom_paths", [False, True])
    @mock.patch(M_PATH + "util.load_text_file", return_value=IMDS_URL)
    @responses.activate
    def test_get_data_honor_cloud_dir(self, m_load_file, custom_paths, tmpdir):
        responses.add(responses.GET, IMDS_URL, body=METADATA_BODY)

        paths = {}
        url_file = "/var/lib/cloud/data/seed/bigstep/url"
        if custom_paths:
            paths = {
                "cloud_dir": tmpdir.join("cloud"),
                "run_dir": tmpdir,
                "templates_dir": tmpdir,
            }
            url_file = os.path.join(
                paths["cloud_dir"], "data", "seed", "bigstep", "url"
            )

        ds = bigstep.DataSourceBigstep(
            sys_cfg={}, distro=mock.Mock(), paths=helpers.Paths(paths)
        )
        assert ds._get_data()
        assert [mock.call(url_file)] == m_load_file.call_args_list
