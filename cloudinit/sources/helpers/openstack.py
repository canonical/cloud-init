# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import abc
import base64
import copy
import functools
import os

from cloudinit import ec2_utils
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

# For reference: http://tinyurl.com/laora4c

LOG = logging.getLogger(__name__)

FILES_V1 = {
    # Path <-> (metadata key name, translator function, default value)
    'etc/network/interfaces': ('network_config', lambda x: x, ''),
    'meta.js': ('meta_js', util.load_json, {}),
    "root/.ssh/authorized_keys": ('authorized_keys', lambda x: x, ''),
}
KEY_COPIES = (
    # Cloud-init metadata names <-> (metadata key, is required)
    ('local-hostname', 'hostname', False),
    ('instance-id', 'uuid', True),
)
OS_LATEST = 'latest'
OS_FOLSOM = '2012-08-10'
OS_GRIZZLY = '2013-04-04'
OS_HAVANA = '2013-10-17'
# keep this in chronological order. new supported versions go at the end.
OS_VERSIONS = (
    OS_FOLSOM,
    OS_GRIZZLY,
    OS_HAVANA,
)


class NonReadable(IOError):
    pass


class BrokenMetadata(IOError):
    pass


class SourceMixin(object):
    def _ec2_name_to_device(self, name):
        if not self.ec2_metadata:
            return None
        bdm = self.ec2_metadata.get('block-device-mapping', {})
        for (ent_name, device) in bdm.items():
            if name == ent_name:
                return device
        return None

    def get_public_ssh_keys(self):
        name = "public_keys"
        if self.version == 1:
            name = "public-keys"
        return sources.normalize_pubkey_data(self.metadata.get(name))

    def _os_name_to_device(self, name):
        device = None
        try:
            criteria = 'LABEL=%s' % (name)
            if name == 'swap':
                criteria = 'TYPE=%s' % (name)
            dev_entries = util.find_devs_with(criteria)
            if dev_entries:
                device = dev_entries[0]
        except util.ProcessExecutionError:
            pass
        return device

    def _validate_device_name(self, device):
        if not device:
            return None
        if not device.startswith("/"):
            device = "/dev/%s" % device
        if os.path.exists(device):
            return device
        # Durn, try adjusting the mapping
        remapped = self._remap_device(os.path.basename(device))
        if remapped:
            LOG.debug("Remapped device name %s => %s", device, remapped)
            return remapped
        return None

    def device_name_to_device(self, name):
        # Translate a 'name' to a 'physical' device
        if not name:
            return None
        # Try the ec2 mapping first
        names = [name]
        if name == 'root':
            names.insert(0, 'ami')
        if name == 'ami':
            names.append('root')
        device = None
        LOG.debug("Using ec2 style lookup to find device %s", names)
        for n in names:
            device = self._ec2_name_to_device(n)
            device = self._validate_device_name(device)
            if device:
                break
        # Try the openstack way second
        if not device:
            LOG.debug("Using openstack style lookup to find device %s", names)
            for n in names:
                device = self._os_name_to_device(n)
                device = self._validate_device_name(device)
                if device:
                    break
        # Ok give up...
        if not device:
            return None
        else:
            LOG.debug("Mapped %s to device %s", name, device)
            return device


class BaseReader(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, base_path):
        self.base_path = base_path

    @abc.abstractmethod
    def _path_join(self, base, *add_ons):
        pass

    @abc.abstractmethod
    def _path_read(self, path):
        pass

    @abc.abstractmethod
    def _fetch_available_versions(self):
        pass

    @abc.abstractmethod
    def _read_ec2_metadata(self):
        pass

    def _find_working_version(self):
        try:
            versions_available = self._fetch_available_versions()
        except Exception as e:
            LOG.debug("Unable to read openstack versions from %s due to: %s",
                      self.base_path, e)
            versions_available = []

        # openstack.OS_VERSIONS is stored in chronological order, so
        # reverse it to check newest first.
        supported = [v for v in reversed(list(OS_VERSIONS))]
        selected_version = OS_LATEST

        for potential_version in supported:
            if potential_version not in versions_available:
                continue
            selected_version = potential_version
            break

        LOG.debug("Selected version '%s' from %s", selected_version,
                  versions_available)
        return selected_version

    def _read_content_path(self, item):
        path = item.get('content_path', '').lstrip("/")
        path_pieces = path.split("/")
        valid_pieces = [p for p in path_pieces if len(p)]
        if not valid_pieces:
            raise BrokenMetadata("Item %s has no valid content path" % (item))
        path = self._path_join(self.base_path, "openstack", *path_pieces)
        return self._path_read(path)

    def read_v2(self):
        """Reads a version 2 formatted location.

        Return a dict with metadata, userdata, ec2-metadata, dsmode,
        network_config, files and version (2).

        If not a valid location, raise a NonReadable exception.
        """

        load_json_anytype = functools.partial(
            util.load_json, root_types=(dict, basestring, list))

        def datafiles(version):
            files = {}
            files['metadata'] = (
                # File path to read
                self._path_join("openstack", version, 'meta_data.json'),
                # Is it required?
                True,
                # Translator function (applied after loading)
                util.load_json,
            )
            files['userdata'] = (
                self._path_join("openstack", version, 'user_data'),
                False,
                lambda x: x,
            )
            files['vendordata'] = (
                self._path_join("openstack", version, 'vendor_data.json'),
                False,
                load_json_anytype,
            )
            return files

        results = {
            'userdata': '',
            'version': 2,
        }
        data = datafiles(self._find_working_version())
        for (name, (path, required, translator)) in data.iteritems():
            path = self._path_join(self.base_path, path)
            data = None
            found = False
            try:
                data = self._path_read(path)
            except IOError as e:
                if not required:
                    LOG.debug("Failed reading optional path %s due"
                              " to: %s", path, e)
                else:
                    LOG.debug("Failed reading mandatory path %s due"
                              " to: %s", path, e)
            else:
                found = True
            if required and not found:
                raise NonReadable("Missing mandatory path: %s" % path)
            if found and translator:
                try:
                    data = translator(data)
                except Exception as e:
                    raise BrokenMetadata("Failed to process "
                                         "path %s: %s" % (path, e))
            if found:
                results[name] = data

        metadata = results['metadata']
        if 'random_seed' in metadata:
            random_seed = metadata['random_seed']
            try:
                metadata['random_seed'] = base64.b64decode(random_seed)
            except (ValueError, TypeError) as e:
                raise BrokenMetadata("Badly formatted metadata"
                                     " random_seed entry: %s" % e)

        # load any files that were provided
        files = {}
        metadata_files = metadata.get('files', [])
        for item in metadata_files:
            if 'path' not in item:
                continue
            path = item['path']
            try:
                files[path] = self._read_content_path(item)
            except Exception as e:
                raise BrokenMetadata("Failed to read provided "
                                     "file %s: %s" % (path, e))
        results['files'] = files

        # The 'network_config' item in metadata is a content pointer
        # to the network config that should be applied. It is just a
        # ubuntu/debian '/etc/network/interfaces' file.
        net_item = metadata.get("network_config", None)
        if net_item:
            try:
                results['network_config'] = self._read_content_path(net_item)
            except IOError as e:
                raise BrokenMetadata("Failed to read network"
                                     " configuration: %s" % (e))

        # To openstack, user can specify meta ('nova boot --meta=key=value')
        # and those will appear under metadata['meta'].
        # if they specify 'dsmode' they're indicating the mode that they intend
        # for this datasource to operate in.
        try:
            results['dsmode'] = metadata['meta']['dsmode']
        except KeyError:
            pass

        # Read any ec2-metadata (if applicable)
        results['ec2-metadata'] = self._read_ec2_metadata()

        # Perform some misc. metadata key renames...
        for (target_key, source_key, is_required) in KEY_COPIES:
            if is_required and source_key not in metadata:
                raise BrokenMetadata("No '%s' entry in metadata" % source_key)
            if source_key in metadata:
                metadata[target_key] = metadata.get(source_key)
        return results


class ConfigDriveReader(BaseReader):
    def __init__(self, base_path):
        super(ConfigDriveReader, self).__init__(base_path)
        self._versions = None

    def _path_join(self, base, *add_ons):
        components = [base] + list(add_ons)
        return os.path.join(*components)

    def _path_read(self, path):
        return util.load_file(path)

    def _fetch_available_versions(self):
        if self._versions is None:
            path = self._path_join(self.base_path, 'openstack')
            found = [d for d in os.listdir(path)
                     if os.path.isdir(os.path.join(path))]
            self._versions = found
        return self._versions

    def _read_ec2_metadata(self):
        path = self._path_join(self.base_path,
                               'ec2', 'latest', 'meta-data.json')
        if not os.path.exists(path):
            return {}
        else:
            try:
                return util.load_json(self._path_read(path))
            except Exception as e:
                raise BrokenMetadata("Failed to process "
                                     "path %s: %s" % (path, e))

    def read_v1(self):
        """Reads a version 1 formatted location.

        Return a dict with metadata, userdata, dsmode, files and version (1).

        If not a valid path, raise a NonReadable exception.
        """

        found = {}
        for name in FILES_V1.keys():
            path = self._path_join(self.base_path, name)
            if os.path.exists(path):
                found[name] = path
        if len(found) == 0:
            raise NonReadable("%s: no files found" % (self.base_path))

        md = {}
        for (name, (key, translator, default)) in FILES_V1.iteritems():
            if name in found:
                path = found[name]
                try:
                    contents = self._path_read(path)
                except IOError:
                    raise BrokenMetadata("Failed to read: %s" % path)
                try:
                    md[key] = translator(contents)
                except Exception as e:
                    raise BrokenMetadata("Failed to process "
                                         "path %s: %s" % (path, e))
            else:
                md[key] = copy.deepcopy(default)

        keydata = md['authorized_keys']
        meta_js = md['meta_js']

        # keydata in meta_js is preferred over "injected"
        keydata = meta_js.get('public-keys', keydata)
        if keydata:
            lines = keydata.splitlines()
            md['public-keys'] = [l for l in lines
                                 if len(l) and not l.startswith("#")]

        # config-drive-v1 has no way for openstack to provide the instance-id
        # so we copy that into metadata from the user input
        if 'instance-id' in meta_js:
            md['instance-id'] = meta_js['instance-id']

        results = {
            'version': 1,
            'metadata': md,
        }

        # allow the user to specify 'dsmode' in a meta tag
        if 'dsmode' in meta_js:
            results['dsmode'] = meta_js['dsmode']

        # config-drive-v1 has no way of specifying user-data, so the user has
        # to cheat and stuff it in a meta tag also.
        results['userdata'] = meta_js.get('user-data', '')

        # this implementation does not support files other than
        # network/interfaces and authorized_keys...
        results['files'] = {}

        return results


class MetadataReader(BaseReader):
    def __init__(self, base_url, ssl_details=None, timeout=5, retries=5):
        super(MetadataReader, self).__init__(base_url)
        self.ssl_details = ssl_details
        self.timeout = float(timeout)
        self.retries = int(retries)
        self._versions = None

    def _fetch_available_versions(self):
        # <baseurl>/openstack/ returns a newline separated list of versions
        if self._versions is not None:
            return self._versions
        found = []
        version_path = self._path_join(self.base_path, "openstack")
        content = self._path_read(version_path)
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            found.append(line)
        self._versions = found
        return self._versions

    def _path_read(self, path):

        def should_retry_cb(_request_args, cause):
            try:
                code = int(cause.code)
                if code >= 400:
                    return False
            except (TypeError, ValueError):
                # Older versions of requests didn't have a code.
                pass
            return True

        response = url_helper.readurl(path,
                                      retries=self.retries,
                                      ssl_details=self.ssl_details,
                                      timeout=self.timeout,
                                      exception_cb=should_retry_cb)
        return response.contents

    def _path_join(self, base, *add_ons):
        return url_helper.combine_url(base, *add_ons)

    def _read_ec2_metadata(self):
        return ec2_utils.get_instance_metadata(ssl_details=self.ssl_details,
                                               timeout=self.timeout,
                                               retries=self.retries)


def convert_vendordata_json(data, recurse=True):
    """ data: a loaded json *object* (strings, arrays, dicts).
    return something suitable for cloudinit vendordata_raw.

    if data is:
       None: return None
       string: return string
       list: return data
             the list is then processed in UserDataProcessor
       dict: return convert_vendordata_json(data.get('cloud-init'))
    """
    if not data:
        return None
    if isinstance(data, (str, unicode, basestring)):
        return data
    if isinstance(data, list):
        return copy.deepcopy(data)
    if isinstance(data, dict):
        if recurse is True:
            return convert_vendordata_json(data.get('cloud-init'),
                                           recurse=False)
        raise ValueError("vendordata['cloud-init'] cannot be dict")
    raise ValueError("Unknown data type for vendordata: %s" % type(data))
