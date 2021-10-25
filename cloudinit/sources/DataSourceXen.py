# Cloud-Init DataSource for Xen
#
# Author: Kalpesh Gade <gadekalpesh19@gmail.com>
#

'''Cloud-Init Datasource for Xen

This module provides cloud-init datasource for Open Source Xen Platform system and fetches data 
from xenstore

'''

import collections
import copy
from distutils.spawn import find_executable
import ipaddress
import json
import os
import socket
import time

from cloudinit import dmi, log as logging
from cloudinit import sources
from cloudinit import util
from cloudinit.sources.DataSourceVMware import advertise_local_ip_addrs, load_json_or_yaml, process_metadata, wait_on_network
from cloudinit.subp import subp, ProcessExecutionError

import netifaces

PRODUCT_UUID_FILE_PATH = "/sys/class/dmi/id/product_uuid"
LOG = logging.getLogger(__name__)
NODATA = "xenstore-read: couldn't read path vm-data/"

XENSTORE_READ = find_executable("xenstore-read")
XENSTORE_WRITE = find_executable("xenstore-write")


LOCAL_IPV4 = "local-ipv4"
LOCAL_IPV6 = "local-ipv6"
WAIT_ON_NETWORK = "wait-on-network"
WAIT_ON_NETWORK_IPV4 = "ipv4"
WAIT_ON_NETWORK_IPV6 = "ipv6"

class DataSourceXen(sources.DataSource):

    """
    Setting the hostname:
        The hostname is set by way of the metadata key "local-hostname".

    Setting the instance ID:
        The instance ID may be set by way of the metadata key "instance-id".
        However, if this value is absent then the instance ID is read
        from the file /sys/class/dmi/id/product_uuid.

    Configuring the network:
        The network is configured by setting the metadata key "network"
        with a value consistent with Network Config Versions 1 or 2,
        depending on the Linux distro's version of cloud-init:

            Network Config Version 1 - http://bit.ly/cloudinit-net-conf-v1
            Network Config Version 2 - http://bit.ly/cloudinit-net-conf-v2

    """

    dsname = "Xen"
    def __init__(self, sys_cfg, distro: Distro, paths, ud_proc=None):
        sources.DataSource.__init__(sys_cfg, distro, paths, ud_proc=ud_proc)

        self.data_access_method = None
        self.xenstore_read = XENSTORE_READ
        self.xenstore_write = XENSTORE_WRITE

    def _get_data(self):
        if not self.data_access_method:
            system_type = dmi.read_dmi_data("system-product-name")
            if system_type is None:
                LOG.debug("No system-product-name found")
                return False
            if "xen" not in system_type.lower():
                LOG.debug("Not a Xen platform")
                return False

        if not self.data_access_method:
            if self.xenstore_read:
                metadata = xenstoredata("metadata", self.xenstore_read)
                userdata = xenstoredata("userdata", self.xenstore_read)
                vendordata = xenstoredata("vendordata", self.xenstore_read)

                if metadata or userdata or vendordata:
                    self.data_access_method =  True

        if not self.data_access_method:
            LOG.error("Failed to find data on xenstore-data")
            return False

        LOG.info("Using xenstore data for metadata, userdata and vendordata")

        # Access metadata from xenstore vm-data/metadata
        self.metadata = process_metadata(load_json_or_yaml(metadata))

        # Access Userdata from xenstore vm-data/userdata 
        self.userdata_raw = userdata

        # Access Vendordata from xenstore vm-data/vendordata
        self.vendordata_raw = vendordata

        if self.metadata or self.userdata_raw or self.vendordata_raw:
            return True
        else:
            return False

    def setup(self, is_new_instance):
        """setup(is_new_instance)

        This is called before user-data and vendor-data have been processed.

        Unless the datasource has set mode to 'local', then networking
        per 'fallback' or per 'network_config' will have been written and
        brought up the OS at this point.
        """


        host_info = wait_on_network(self.metadata)
        LOG.info("got host-info: %s", host_info)

        advertise_local_ip_addrs(host_info)

        self.metadata = util.mergemanydict([self.metadata, host_info])
        self.persist_instance_data()

    def _get_subplatform(self):
        get_key_name_func = None
        if self.data_access_method == True:
            get_key_name_func = get_xenstore_key_name
        else:
            return sources.METADATA_UNKNOWN
        return "%s (%s)" % (
            self.data_access_method,
            get_key_name_func("metadata"),
        )    

    @property
    def network_config(self):
        if "network" in self.metadata:
            LOG.debug("using metadata network config")
        else:
            LOG.debug("using failback network config")
            self.metadata["network"] = {
                "config": self.distro.generate_fallback_config(),
            }    
        return self.metadata["network"]["config"]

    def get_instance_id(self):
        if self.metadata and "instance-id" in self.metadata:
            return self.metadata["instance-id"]
        with open(PRODUCT_UUID_FILE_PATH, "r") as uuid_file:
            self.metadata["instance-id"] = str(uuid_file.read()).rstrip().lower()
            return self.metadata["instance-id"]

    def get_public_ssh_keys(self):
        for key_name in (
            "public-keys-data",
            "public_keys_data",
            "public-keys",
            "public_keys",
        ):
            if key_name in self.metadata:
                return sources.normalize_pubkey_data(self.metadata[key_name])
        return []

def decode(key, enc_type, data):
    LOG.debug("Getting encoded data for key=%s, enc=%s", key, enc_type)
    raw_data = None

    if enc_type in ["gzip+base64", "gz+b64"]:
        LOG.debug("Decoding %s type of %s", enc_type, key)
        raw_data = util.decomp_gzip(util.b64d(data))
    elif enc_type in ["base64", "b64"]:
        LOG.debug("Decoding %s type of %s", enc_type, key) 
        raw_data = util.b64d(data)
    else:
        LOG.debug("Plain-text data %s", key)
        raw_data = data
    return util.decode_binary(raw_data)

def get_none_if_empty_val(val):
    val = util.decode_binary(val)
    val = val.rstrip()

    if len(val) == 0:
        return None
    return val

def advertise_local_ip_address(host_info):
    if not host_info:
        return

    local_ipv4 = host_info.get(LOCAL_IPV4)
    if local_ipv4:
        xenstore_set_value(LOCAL_IPV4, local_ipv4)
        LOG.info("advertised local ipv4 address %s in xenstore", local_ipv4)

    local_ipv6 = host_info.get(LOCAL_IPV6)
    if local_ipv6:
        xenstore_set_value(LOCAL_IPV6, local_ipv6)
        LOG.info("advertised local ipv6 address %s in xenstore", local_ipv6)

def handled_returned_xenstore_val(key,val):
    val = get_none_if_empty_val(val)
    if val:
        return val
    LOG.debug("Value not found for key %s", key)
    return None

def get_xenstore_key_name(key):
    return key


def xenstoredata(key, xenstore_read=XENSTORE_READ):
    """
    guestinfo returns the guestinfo value for the provided key, decoding
    the value when required
    """
    val = xenstore_get_value(key, xenstore_read)
    if not val:
        return None
    enc_type = xenstore_get_value(key + "/encoding", xenstore_read)
    return decode(get_xenstore_key_name(key), enc_type, val)

def xenstore_get_value(key, xenstore_read=XENSTORE_READ):
    LOG.debug("Getting xenstore value for key %s", key)

    try:
        (stdout, stderr) = subp(
            [
                xenstore_read,
                "vm-data/" + get_xenstore_key_name(key),
            ]
        )
        if stderr == NODATA:
            LOG.debug("Couldn't find value for %s in xenstore", key)
        elif not stdout:
            LOG.debug("Failed to find value for %s in xenstore", key)
        return handled_returned_xenstore_val(key, stdout)    
    except ProcessExecutionError as error:
        if error.stderr == NODATA:
            LOG.debug("Couldn't find value for key %s in xenstore", key)
        else:
            util.logexc(
                LOG,
                "Couldn't find value for %s in xenstore: %s",
                key,
                error,
            )
    except Exception:
        util.logexc(
            LOG,
            "Unexpected value while trying to get "
            + "xenstore value for key %s",
            key,
        )
    return None

def xenstore_set_value(key, value, xenstore_write=XENSTORE_WRITE):
    if value == "":
        value = " "
    LOG.debug("Setting xenstore value for key %s to %s", key,value)

    try:
        subp(
            [
                    xenstore_write,
                    ("vm-data/%s" %(key)),
                    ("%s" %(value))
            ]
        )
        return True

    except ProcessExecutionError as error:
        util.logexc(
            LOG,
            "Failed to set xenstore value %s for key %s: %s",
            value,
            key,
            error,
        )
    except Exception:
        util.logexc(
            LOG,
            "Unexpected error while trying to set "
            + "xenstore key=%s to value=%s",
            key,
            value,
        )
    return None


def load_json_or_yaml(data):
    if not data:
        return {}
    try:
        return util.load_json(data)
    except (json.JSONDecodeError, TypeError):
        return util.load_yaml(data)

def process_metadata(data):
    network = None
    if "network" in data:
        network = data["network"]
        del data["network"]

    network_enc = None
    if "network.encoding" in data:
        network_enc = data["network.encoding"]
        del data["network.encoding"]

    if network:
        if isinstance(network, collections.abc.Mapping):
            LOG.debug("network data copied to 'config' key")
            network = {"config": copy.deepcopy(network)}
        else:
            LOG.debug("network data to be decoded %s", network)
            dec_net = decode("metadata.network", network_enc, network)
            network = {
                "config": load_json_or_yaml(dec_net),
            }    

        LOG.debug("network data %s", network)
        data["network"] = network
    return data

datasources = [
    (DataSourceXen, (sources.DEP_FILESYSTEM,)),  # Run at init-local
    (DataSourceXen, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]    

def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

def get_default_ip_address():
    gateways = netifaces.gateways()
    if "default" not in gateways:
        return None, None

    default_gateway = gateways["default"]

    if (
        netifaces.AF_INET not in default_gateway
        and netifaces.AF_INET6 not in default_gateway
    ):
        return None, None

    ipv4 = None
    ipv6 = None

    gateway4 = default_gateway.get(netifaces.AF_INET)
    if gateway4:
        _, dev4 = gateway4
        address4_fams = netifaces.ifaddresses(dev4)
        if address4_fams:
            af_inet4 = address4_fams.get(netifaces.AF_INET)
            if af_inet4:
                if len(af_inet4) > 1:
                    LOG.warning(
                        "device %s has more than one ipv4 address: %s",
                        dev4,
                        af_inet4,
                    )
                elif "addr" in af_inet4[0]:
                    ipv4 = af_inet4[0]["addr"]

    gateway6 = default_gateway.get(netifaces.AF_INET6)
    if gateway6:
        _, dev6 = gateway6
        address6_fams = netifaces.ifaddresses(dev6)
        if address6_fams:
            af_inet6 = address6_fams.get(netifaces.AF_INET6)
            if af_inet6:
                if len(af_inet6) > 1:
                    LOG.warning(
                        "device %s has more than one ipv6 address: %s",
                        dev6,
                        af_inet6,
                    )
                elif "addr" in af_inet6[0]:
                    ipv6 = af_inet6[0]["addr"]

    if ipv4 and not ipv6:
        af_inet6 = address4_fams.get(netifaces.AF_INET6)
        if af_inet6:
            if len(af_inet6) > 1:
                LOG.warning(
                   "device %s has more than one ipv6 address: %s",
                   dev4,
                   af_inet6, 
                )
            elif "addr" in af_inet6[0]:
                ipv6 = af_inet6[0]["addr"]

    if not ipv4 and ipv6:
        af_inet4 = address6_fams.get(netifaces.AF_INET)
        if af_inet4:
            if len(af_inet4) > 1:
                LOG.warning(
                    "device %s has more than one ipv4 address: %s",
                    dev6,
                    af_inet4,
                )
            elif "addr" in af_inet4[0]:
                ipv4 = af_inet4[0]["addr"]
    
    return ipv4, ipv6

def getfqdn(name=""):
    name = name.strip()
    if not name or name == "0.0.0.0":
        name = util.get_hostname()
    try:
        address = socket.getaddrinfo(
            name, None, 0, socket.SOCK_DGRAM, 0, socket.AI_CANONNAME
        )
    except socket.error:
        pass
    else:
        for addr in address:
            if addr[3]:
                name = addr[3]
                break
    return name

def is_valid_ip_address(value):
    """
    Returns false if the address is loopback, link local or unspecified;
    otherwise true is returned.
    """
    # TODO(extend cloudinit.net.is_ip_addr exclude link_local/loopback etc)
    # TODO(migrate to use cloudinit.net.is_ip_addr)#

    addr = None
    try:
        addr = ipaddress.ip_address(value)
    except ipaddress.AddressValueError:
        addr = ipaddress.ip_address(str(value))
    except Exception:
        return None

    if addr.is_link_local or addr.is_loopback or addr.is_unspecified:
        return False
    return True    

def get_host_info():
    """
    Returns host information such as the host name and network interfaces.
    """
    # TODO(look to promote netifices use up in cloud-init netinfo funcs)
    host_info = {
        "network": {
            "interfaces": {
                "by-mac": collections.OrderedDict(),
                "by-ipv4": collections.OrderedDict(),
                "by-ipv6": collections.OrderedDict(),
            },
        },
    }
    hostname = getfqdn(util.get_hostname())
    if hostname:
        host_info["hostname"] = hostname
        host_info["local-hostname"] = hostname
        host_info["local_hostname"] = hostname

    default_ipv4, default_ipv6 = get_default_ip_address()
    if default_ipv4:
        host_info[LOCAL_IPV4] = default_ipv4
    if default_ipv6:
        host_info[LOCAL_IPV6] = default_ipv6

    by_mac = host_info["network"]["interfaces"]["by-mac"]
    by_ipv4 = host_info["network"]["interfaces"]["by-ipv4"]
    by_ipv6 = host_info["network"]["interfaces"]["by-ipv6"]

    ifaces = netifaces.interfaces()
    for dev_name in ifaces:
        address_fams = netifaces.ifaddresses(dev_name)
        af_link = address_fams.get(netifaces.AF_LINK)
        af_inet4 = address_fams.get(netifaces.AF_INET)
        af_inet6 = address_fams.get(netifaces.AF_INET6)

        mac = None
        if af_link and "addr" in af_link[0]:
            mac = af_link[0]["addr"]

        # Do not bother recording localhost
        if mac == "00:00:00:00:00:00":
            continue

        if mac and (af_inet4 or af_inet6):
            key = mac
            val = {}
            if af_inet4:
                af_inet4_vals = []
                for ip_info in af_inet4:
                    if not is_valid_ip_address(ip_info["addr"]):
                        continue
                    af_inet4_vals.append(ip_info)
                val["ipv4"] = af_inet4_vals
            if af_inet6:
                af_inet6_vals = []
                for ip_info in af_inet6:
                    if not is_valid_ip_address(ip_info["addr"]):
                        continue
                    af_inet6_vals.append(ip_info)
                val["ipv6"] = af_inet6_vals
            by_mac[key] = val

        if af_inet4:
            for ip_info in af_inet4:
                key = ip_info["addr"]
                if not is_valid_ip_address(key):
                    continue
                val = copy.deepcopy(ip_info)
                del val["addr"]
                if mac:
                    val["mac"] = mac
                by_ipv4[key] = val

        if af_inet6:
            for ip_info in af_inet6:
                key = ip_info["addr"]
                if not is_valid_ip_address(key):
                    continue
                val = copy.deepcopy(ip_info)
                del val["addr"]
                if mac:
                    val["mac"] = mac
                by_ipv6[key] = val

    return host_info

def wait_on_network(metadata):
    # Determine whether we need to wait on the network coming online.
    wait_on_ipv4 = False
    wait_on_ipv6 = False
    if WAIT_ON_NETWORK in metadata:
        wait_on_network = metadata[WAIT_ON_NETWORK]
        if WAIT_ON_NETWORK_IPV4 in wait_on_network:
            wait_on_ipv4_val = wait_on_network[WAIT_ON_NETWORK_IPV4]
            if isinstance(wait_on_ipv4_val, bool):
                wait_on_ipv4 = wait_on_ipv4_val
            else:
                wait_on_ipv4 = util.translate_bool(wait_on_ipv4_val)
        if WAIT_ON_NETWORK_IPV6 in wait_on_network:
            wait_on_ipv6_val = wait_on_network[WAIT_ON_NETWORK_IPV6]
            if isinstance(wait_on_ipv6_val, bool):
                wait_on_ipv6 = wait_on_ipv6_val
            else:
                wait_on_ipv6 = util.translate_bool(wait_on_ipv6_val)

    # Get information about the host.
    host_info = None
    while host_info is None:
        # This loop + sleep results in two logs every second while waiting
        # for either ipv4 or ipv6 up. Do we really need to log each iteration
        # or can we log once and log on successful exit?
        host_info = get_host_info()

        network = host_info.get("network") or {}
        interfaces = network.get("interfaces") or {}
        by_ipv4 = interfaces.get("by-ipv4") or {}
        by_ipv6 = interfaces.get("by-ipv6") or {}

        if wait_on_ipv4:
            ipv4_ready = len(by_ipv4) > 0 if by_ipv4 else False
            if not ipv4_ready:
                host_info = None

        if wait_on_ipv6:
            ipv6_ready = len(by_ipv6) > 0 if by_ipv6 else False
            if not ipv6_ready:
                host_info = None

        if host_info is None:
            LOG.debug(
                "waiting on network: wait4=%s, ready4=%s, wait6=%s, ready6=%s",
                wait_on_ipv4,
                ipv4_ready,
                wait_on_ipv6,
                ipv6_ready,
            )
            time.sleep(1)

    LOG.debug("waiting on network complete")
    return host_info


def main():
    """
    Executed when this file is used as a program.
    """
    try:
        logging.setupBasicLogging()
    except Exception:
        pass
    metadata = {
        "wait-on-network": {"ipv4": True, "ipv6": "false"},
        "network": {"config": {"dhcp": True}},
    }
    host_info = wait_on_network(metadata)
    metadata = util.mergemanydict([metadata, host_info])
    print(util.json_dumps(metadata))


if __name__ == "__main__":
    main()



