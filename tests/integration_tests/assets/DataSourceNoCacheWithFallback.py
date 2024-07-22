import logging
import os

from cloudinit import sources

LOG = logging.getLogger(__name__)


class DataSourceNoCacheWithFallback(sources.DataSource):
    def _get_data(self):
        if os.path.exists("/ci-test-firstboot"):
            LOG.debug("TEST _get_data called")
            return True
        return False

    def check_if_fallback_is_allowed(self):
        return True


datasources = [
    (
        DataSourceNoCacheWithFallback,
        (sources.DEP_FILESYSTEM,),
    ),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
