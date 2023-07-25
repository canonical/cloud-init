import pytest

from cloudinit.importer import match_case_insensitive_module_name


@pytest.mark.parametrize(
    "m_name,m_match",
    (
        pytest.param(
            "nocloud-net",
            "DataSourceNoCloud",
            id="nocloud-net is a special case, make sure it works",
        ),
        pytest.param(
            "nocloud",
            "DataSourceNoCloud",
            id="nocloud is a special case, make sure it works",
        ),
        pytest.param("DataSourceGCE", "DataSourceGCE", id="gce, full name"),
        pytest.param("gce", "DataSourceGCE", id="gce, name match"),
    ),
)
def test_importer(m_name, m_match):
    assert m_match == match_case_insensitive_module_name(m_name)
