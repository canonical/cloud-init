# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import urllib

from cloudinit import log as logging
from cloudinit import url_helper as uh
from cloudinit import util

LOG = logging.getLogger(__name__)


# For now take this and fix it...
class LazyLoadMetadata(dict):
    def __init__(self, url, fetch_timeout, num_retries, ssl_details):
        self._url = url
        self._num_retries = num_retries
        self._ssl_details = ssl_details
        self._fetch_timeout = fetch_timeout
        self._leaves = {}
        self._dicts = []
        response = uh.readurl(url, timeout=fetch_timeout,
                              retries=num_retries, ssl_details=ssl_details)
        data = str(response)
        if data:
            fields = data.split('\n')
            for field in fields:
                if field.endswith('/'):
                    key = field[0:-1]
                    self._dicts.append(key)
                else:
                    p = field.find('=')
                    if p > 0:
                        key = field[p + 1:]
                        resource = field[0:p] + '/openssh-key'
                    else:
                        key = resource = field
                    self._leaves[key] = resource
                self[key] = None

    def _materialize(self):
        for key in self:
            self[key]

    def __getitem__(self, key):
        if key not in self:
            # Allow dict to throw the KeyError
            return super(LazyLoadMetadata, self).__getitem__(key)

        # Already loaded
        val = super(LazyLoadMetadata, self).__getitem__(key)
        if val is not None:
            return val

        if key in self._leaves:
            resource = self._leaves[key]
            new_url = self._url + urllib.quote(resource, safe="/:")
            response = uh.readurl(new_url, retries=self._num_retries,
                                  timeout=self._fetch_timeout,
                                  ssl_details=self._ssl_details)
            val = str(response)
            if val and val[0] == '{':
                val = json.loads(val)
            else:
                p = val.find('\n')
                if p > 0:
                    val = val.split('\n')
            self[key] = val
        elif key in self._dicts:
            new_url = self._url + key + '/'
            self[key] = LazyLoadMetadata(new_url,
                                         num_retries=self._num_retries,
                                         fetch_timeout=self._fetch_timeout,
                                         ssl_details=self._ssl_details)

        return super(LazyLoadMetadata, self).__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def values(self):
        self._materialize()
        return super(LazyLoadMetadata, self).values()

    def items(self):
        self._materialize()
        return super(LazyLoadMetadata, self).items()

    def __str__(self):
        self._materialize()
        return super(LazyLoadMetadata, self).__str__()

    def __repr__(self):
        self._materialize()
        return super(LazyLoadMetadata, self).__repr__()


def get_instance_userdata(url, version='latest', ssl_details=None):
    ud_url = '%s/%s/user-data' % (url, version)
    try:
        response = uh.readurl(ud_url, timeout=5,
                              retries=10, ssl_details=ssl_details)
        return str(response)
    except Exception as e:
        util.logexc(LOG, "Failed fetching url %s", ud_url)
        return None


def get_instance_metadata(url, version='latest', ssl_details=None):
    md_url = '%s/%s/meta-data' % (url, version)
    try:
        return LazyLoadMetadata(md_url, timeout=5, 
                                retries=10, ssl_details=ssl_details)
    except Exception as e:
        util.logexc(LOG, "Failed fetching url %s", md_url)
        return None
