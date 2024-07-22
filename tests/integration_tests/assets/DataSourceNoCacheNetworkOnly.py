import logging

from cloudinit import sources

LOG = logging.getLogger(__name__)


class DataSourceNoCacheNetworkOnly(sources.DataSource):
    def _get_data(self):
        LOG.debug("TEST _get_data called")
        return True


datasources = [
    (
        DataSourceNoCacheNetworkOnly,
        (sources.DEP_FILESYSTEM, sources.DEP_NETWORK),
    ),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
