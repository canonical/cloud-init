# Copyright (C) 2013 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import contextlib
import crypt
from functools import partial
import json
import os
import os.path
import re
from time import time
from xml.dom import minidom
import xml.etree.ElementTree as ET

from cloudinit import log as logging
from cloudinit import net
from cloudinit.event import EventType
from cloudinit.net.dhcp import EphemeralDHCPv4
from cloudinit import sources
from cloudinit.sources.helpers import netlink
from cloudinit.url_helper import UrlError, readurl, retry_on_url_exc
from cloudinit import util
from cloudinit.reporting import events

from cloudinit.sources.helpers.azure import (
    azure_ds_reporter,
    azure_ds_telemetry_reporter,
    get_metadata_from_fabric,
    get_boot_telemetry,
    get_system_info,
    report_diagnostic_event,
    EphemeralDHCPv4WithReporting,
    is_byte_swapped)

LOG = logging.getLogger(__name__)

DS_NAME = 'Azure'
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}
AGENT_START = ['service', 'walinuxagent', 'start']
AGENT_START_BUILTIN = "__builtin__"
BOUNCE_COMMAND_IFUP = [
    'sh', '-xc',
    "i=$interface; x=0; ifdown $i || x=$?; ifup $i || x=$?; exit $x"
]
BOUNCE_COMMAND_FREEBSD = [
    'sh', '-xc',
    ("i=$interface; x=0; ifconfig down $i || x=$?; "
     "ifconfig up $i || x=$?; exit $x")
]

# azure systems will always have a resource disk, and 66-azure-ephemeral.rules
# ensures that it gets linked to this path.
RESOURCE_DISK_PATH = '/dev/disk/cloud/azure_resource'
DEFAULT_PRIMARY_NIC = 'eth0'
LEASE_FILE = '/var/lib/dhcp/dhclient.eth0.leases'
DEFAULT_FS = 'ext4'
# DMI chassis-asset-tag is set static for all azure instances
AZURE_CHASSIS_ASSET_TAG = '7783-7084-3265-9085-8269-3286-77'
REPROVISION_MARKER_FILE = "/var/lib/cloud/data/poll_imds"
REPORTED_READY_MARKER_FILE = "/var/lib/cloud/data/reported_ready"
AGENT_SEED_DIR = '/var/lib/waagent'

# In the event where the IMDS primary server is not
# available, it takes 1s to fallback to the secondary one
IMDS_TIMEOUT_IN_SECONDS = 2
IMDS_URL = "http://169.254.169.254/metadata/"

PLATFORM_ENTROPY_SOURCE = "/sys/firmware/acpi/tables/OEM0"

# List of static scripts and network config artifacts created by
# stock ubuntu suported images.
UBUNTU_EXTENDED_NETWORK_SCRIPTS = [
    '/etc/netplan/90-hotplug-azure.yaml',
    '/usr/local/sbin/ephemeral_eth.sh',
    '/etc/udev/rules.d/10-net-device-added.rules',
    '/run/network/interfaces.ephemeral.d',
]


def find_storvscid_from_sysctl_pnpinfo(sysctl_out, deviceid):
    # extract the 'X' from dev.storvsc.X. if deviceid matches
    """
    dev.storvsc.1.%pnpinfo:
        classid=32412632-86cb-44a2-9b5c-50d1417354f5
        deviceid=00000000-0001-8899-0000-000000000000
    """
    for line in sysctl_out.splitlines():
        if re.search(r"pnpinfo", line):
            fields = line.split()
            if len(fields) >= 3:
                columns = fields[2].split('=')
                if (len(columns) >= 2 and
                        columns[0] == "deviceid" and
                        columns[1].startswith(deviceid)):
                    comps = fields[0].split('.')
                    return comps[2]
    return None


def find_busdev_from_disk(camcontrol_out, disk_drv):
    # find the scbusX from 'camcontrol devlist -b' output
    # if disk_drv matches the specified disk driver, i.e. blkvsc1
    """
    scbus0 on ata0 bus 0
    scbus1 on ata1 bus 0
    scbus2 on blkvsc0 bus 0
    scbus3 on blkvsc1 bus 0
    scbus4 on storvsc2 bus 0
    scbus5 on storvsc3 bus 0
    scbus-1 on xpt0 bus 0
    """
    for line in camcontrol_out.splitlines():
        if re.search(disk_drv, line):
            items = line.split()
            return items[0]
    return None


def find_dev_from_busdev(camcontrol_out, busdev):
    # find the daX from 'camcontrol devlist' output
    # if busdev matches the specified value, i.e. 'scbus2'
    """
    <Msft Virtual CD/ROM 1.0>          at scbus1 target 0 lun 0 (cd0,pass0)
    <Msft Virtual Disk 1.0>            at scbus2 target 0 lun 0 (da0,pass1)
    <Msft Virtual Disk 1.0>            at scbus3 target 1 lun 0 (da1,pass2)
    """
    for line in camcontrol_out.splitlines():
        if re.search(busdev, line):
            items = line.split('(')
            if len(items) == 2:
                dev_pass = items[1].split(',')
                return dev_pass[0]
    return None


def execute_or_debug(cmd, fail_ret=None):
    try:
        return util.subp(cmd)[0]
    except util.ProcessExecutionError:
        LOG.debug("Failed to execute: %s", ' '.join(cmd))
        return fail_ret


def get_dev_storvsc_sysctl():
    return execute_or_debug(["sysctl", "dev.storvsc"], fail_ret="")


def get_camcontrol_dev_bus():
    return execute_or_debug(['camcontrol', 'devlist', '-b'])


def get_camcontrol_dev():
    return execute_or_debug(['camcontrol', 'devlist'])


def get_resource_disk_on_freebsd(port_id):
    g0 = "00000000"
    if port_id > 1:
        g0 = "00000001"
        port_id = port_id - 2
    g1 = "000" + str(port_id)
    g0g1 = "{0}-{1}".format(g0, g1)
    """
    search 'X' from
       'dev.storvsc.X.%pnpinfo:
           classid=32412632-86cb-44a2-9b5c-50d1417354f5
           deviceid=00000000-0001-8899-0000-000000000000'
    """
    sysctl_out = get_dev_storvsc_sysctl()

    storvscid = find_storvscid_from_sysctl_pnpinfo(sysctl_out, g0g1)
    if not storvscid:
        LOG.debug("Fail to find storvsc id from sysctl")
        return None

    camcontrol_b_out = get_camcontrol_dev_bus()
    camcontrol_out = get_camcontrol_dev()
    # try to find /dev/XX from 'blkvsc' device
    blkvsc = "blkvsc{0}".format(storvscid)
    scbusx = find_busdev_from_disk(camcontrol_b_out, blkvsc)
    if scbusx:
        devname = find_dev_from_busdev(camcontrol_out, scbusx)
        if devname is None:
            LOG.debug("Fail to find /dev/daX")
            return None
        return devname
    # try to find /dev/XX from 'storvsc' device
    storvsc = "storvsc{0}".format(storvscid)
    scbusx = find_busdev_from_disk(camcontrol_b_out, storvsc)
    if scbusx:
        devname = find_dev_from_busdev(camcontrol_out, scbusx)
        if devname is None:
            LOG.debug("Fail to find /dev/daX")
            return None
        return devname
    return None


# update the FreeBSD specific information
if util.is_FreeBSD():
    DEFAULT_PRIMARY_NIC = 'hn0'
    LEASE_FILE = '/var/db/dhclient.leases.hn0'
    DEFAULT_FS = 'freebsd-ufs'
    res_disk = get_resource_disk_on_freebsd(1)
    if res_disk is not None:
        LOG.debug("resource disk is not None")
        RESOURCE_DISK_PATH = "/dev/" + res_disk
    else:
        LOG.debug("resource disk is None")
    # TODO Find where platform entropy data is surfaced
    PLATFORM_ENTROPY_SOURCE = None

BUILTIN_DS_CONFIG = {
    'agent_command': AGENT_START_BUILTIN,
    'data_dir': AGENT_SEED_DIR,
    'set_hostname': True,
    'hostname_bounce': {
        'interface': DEFAULT_PRIMARY_NIC,
        'policy': True,
        'command': 'builtin',
        'hostname_command': 'hostname',
    },
    'disk_aliases': {'ephemeral0': RESOURCE_DISK_PATH},
    'dhclient_lease_file': LEASE_FILE,
    'apply_network_config': True,  # Use IMDS published network configuration
}
# RELEASE_BLOCKER: Xenial and earlier apply_network_config default is False

BUILTIN_CLOUD_CONFIG = {
    'disk_setup': {
        'ephemeral0': {'table_type': 'gpt',
                       'layout': [100],
                       'overwrite': True},
    },
    'fs_setup': [{'filesystem': DEFAULT_FS,
                  'device': 'ephemeral0.1'}],
}

DS_CFG_PATH = ['datasource', DS_NAME]
DS_CFG_KEY_PRESERVE_NTFS = 'never_destroy_ntfs'
DEF_EPHEMERAL_LABEL = 'Temporary Storage'

# The redacted password fails to meet password complexity requirements
# so we can safely use this to mask/redact the password in the ovf-env.xml
DEF_PASSWD_REDACTION = 'REDACTED'


def get_hostname(hostname_command='hostname'):
    if not isinstance(hostname_command, (list, tuple)):
        hostname_command = (hostname_command,)
    return util.subp(hostname_command, capture=True)[0].strip()


def set_hostname(hostname, hostname_command='hostname'):
    util.subp([hostname_command, hostname])


@azure_ds_telemetry_reporter
@contextlib.contextmanager
def temporary_hostname(temp_hostname, cfg, hostname_command='hostname'):
    """
    Set a temporary hostname, restoring the previous hostname on exit.

    Will have the value of the previous hostname when used as a context
    manager, or None if the hostname was not changed.
    """
    policy = cfg['hostname_bounce']['policy']
    previous_hostname = get_hostname(hostname_command)
    if (not util.is_true(cfg.get('set_hostname')) or
       util.is_false(policy) or
       (previous_hostname == temp_hostname and policy != 'force')):
        yield None
        return
    set_hostname(temp_hostname, hostname_command)
    try:
        yield previous_hostname
    finally:
        set_hostname(previous_hostname, hostname_command)


class DataSourceAzure(sources.DataSource):

    dsname = 'Azure'
    _negotiated = False
    _metadata_imds = sources.UNSET

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'azure')
        self.cfg = {}
        self.seed = None
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, DS_CFG_PATH, {}),
            BUILTIN_DS_CONFIG])
        self.dhclient_lease_file = self.ds_cfg.get('dhclient_lease_file')
        self._network_config = None
        # Regenerate network config new_instance boot and every boot
        self.update_events['network'].add(EventType.BOOT)
        self._ephemeral_dhcp_ctx = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    @azure_ds_telemetry_reporter
    def bounce_network_with_azure_hostname(self):
        # When using cloud-init to provision, we have to set the hostname from
        # the metadata and "bounce" the network to force DDNS to update via
        # dhclient
        azure_hostname = self.metadata.get('local-hostname')
        LOG.debug("Hostname in metadata is %s", azure_hostname)
        hostname_command = self.ds_cfg['hostname_bounce']['hostname_command']

        with temporary_hostname(azure_hostname, self.ds_cfg,
                                hostname_command=hostname_command) \
                as previous_hn:
            if (previous_hn is not None and
                    util.is_true(self.ds_cfg.get('set_hostname'))):
                cfg = self.ds_cfg['hostname_bounce']

                # "Bouncing" the network
                try:
                    return perform_hostname_bounce(hostname=azure_hostname,
                                                   cfg=cfg,
                                                   prev_hostname=previous_hn)
                except Exception as e:
                    LOG.warning("Failed publishing hostname: %s", e)
                    util.logexc(LOG, "handling set_hostname failed")
        return False

    @azure_ds_telemetry_reporter
    def get_metadata_from_agent(self):
        temp_hostname = self.metadata.get('local-hostname')
        agent_cmd = self.ds_cfg['agent_command']
        LOG.debug("Getting metadata via agent.  hostname=%s cmd=%s",
                  temp_hostname, agent_cmd)

        self.bounce_network_with_azure_hostname()

        try:
            invoke_agent(agent_cmd)
        except util.ProcessExecutionError:
            # claim the datasource even if the command failed
            util.logexc(LOG, "agent command '%s' failed.",
                        self.ds_cfg['agent_command'])

        ddir = self.ds_cfg['data_dir']

        fp_files = []
        key_value = None
        for pk in self.cfg.get('_pubkeys', []):
            if pk.get('value', None):
                key_value = pk['value']
                LOG.debug("SSH authentication: using value from fabric")
            else:
                bname = str(pk['fingerprint'] + ".crt")
                fp_files += [os.path.join(ddir, bname)]
                LOG.debug("SSH authentication: "
                          "using fingerprint from fabric")

        with events.ReportEventStack(
                name="waiting-for-ssh-public-key",
                description="wait for agents to retrieve SSH keys",
                parent=azure_ds_reporter):
            # wait very long for public SSH keys to arrive
            # https://bugs.launchpad.net/cloud-init/+bug/1717611
            missing = util.log_time(logfunc=LOG.debug,
                                    msg="waiting for SSH public key files",
                                    func=util.wait_for_files,
                                    args=(fp_files, 900))
            if len(missing):
                LOG.warning("Did not find files, but going on: %s", missing)

        metadata = {}
        metadata['public-keys'] = key_value or pubkeys_from_crt_files(fp_files)
        return metadata

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        if self.seed.startswith('/dev'):
            subplatform_type = 'config-disk'
        else:
            subplatform_type = 'seed-dir'
        return '%s (%s)' % (subplatform_type, self.seed)

    @azure_ds_telemetry_reporter
    def crawl_metadata(self):
        """Walk all instance metadata sources returning a dict on success.

        @return: A dictionary of any metadata content for this instance.
        @raise: InvalidMetaDataException when the expected metadata service is
            unavailable, broken or disabled.
        """
        crawled_data = {}
        # azure removes/ejects the cdrom containing the ovf-env.xml
        # file on reboot.  So, in order to successfully reboot we
        # need to look in the datadir and consider that valid
        ddir = self.ds_cfg['data_dir']

        candidates = [self.seed_dir]
        if os.path.isfile(REPROVISION_MARKER_FILE):
            candidates.insert(0, "IMDS")
        candidates.extend(list_possible_azure_ds_devs())
        if ddir:
            candidates.append(ddir)

        found = None
        reprovision = False
        for cdev in candidates:
            try:
                if cdev == "IMDS":
                    ret = None
                    reprovision = True
                elif cdev.startswith("/dev/"):
                    if util.is_FreeBSD():
                        ret = util.mount_cb(cdev, load_azure_ds_dir,
                                            mtype="udf")
                    else:
                        ret = util.mount_cb(cdev, load_azure_ds_dir)
                else:
                    ret = load_azure_ds_dir(cdev)

            except NonAzureDataSource:
                report_diagnostic_event(
                    "Did not find Azure data source in %s" % cdev)
                continue
            except BrokenAzureDataSource as exc:
                msg = 'BrokenAzureDataSource: %s' % exc
                report_diagnostic_event(msg)
                raise sources.InvalidMetaDataException(msg)
            except util.MountFailedError:
                msg = '%s was not mountable' % cdev
                report_diagnostic_event(msg)
                LOG.warning(msg)
                continue

            perform_reprovision = reprovision or self._should_reprovision(ret)
            if perform_reprovision:
                if util.is_FreeBSD():
                    msg = "Free BSD is not supported for PPS VMs"
                    LOG.error(msg)
                    report_diagnostic_event(msg)
                    raise sources.InvalidMetaDataException(msg)
                ret = self._reprovision()
            imds_md = get_metadata_from_imds(
                self.fallback_interface, retries=10)
            (md, userdata_raw, cfg, files) = ret
            self.seed = cdev
            crawled_data.update({
                'cfg': cfg,
                'files': files,
                'metadata': util.mergemanydict(
                    [md, {'imds': imds_md}]),
                'userdata_raw': userdata_raw})
            found = cdev

            LOG.debug("found datasource in %s", cdev)
            break

        if not found:
            msg = 'No Azure metadata found'
            report_diagnostic_event(msg)
            raise sources.InvalidMetaDataException(msg)

        if found == ddir:
            LOG.debug("using files cached in %s", ddir)

        seed = _get_random_seed()
        if seed:
            crawled_data['metadata']['random_seed'] = seed
        crawled_data['metadata']['instance-id'] = self._iid()

        if perform_reprovision:
            LOG.info("Reporting ready to Azure after getting ReprovisionData")
            use_cached_ephemeral = (net.is_up(self.fallback_interface) and
                                    getattr(self, '_ephemeral_dhcp_ctx', None))
            if use_cached_ephemeral:
                self._report_ready(lease=self._ephemeral_dhcp_ctx.lease)
                self._ephemeral_dhcp_ctx.clean_network()  # Teardown ephemeral
            else:
                try:
                    with EphemeralDHCPv4WithReporting(
                            azure_ds_reporter) as lease:
                        self._report_ready(lease=lease)
                except Exception as e:
                    report_diagnostic_event(
                        "exception while reporting ready: %s" % e)
                    raise
        return crawled_data

    def _is_platform_viable(self):
        """Check platform environment to report if this datasource may run."""
        return _is_platform_viable(self.seed_dir)

    def clear_cached_attrs(self, attr_defaults=()):
        """Reset any cached class attributes to defaults."""
        super(DataSourceAzure, self).clear_cached_attrs(attr_defaults)
        self._metadata_imds = sources.UNSET

    @azure_ds_telemetry_reporter
    def _get_data(self):
        """Crawl and process datasource metadata caching metadata as attrs.

        @return: True on success, False on error, invalid or disabled
            datasource.
        """
        if not self._is_platform_viable():
            return False
        try:
            get_boot_telemetry()
        except Exception as e:
            LOG.warning("Failed to get boot telemetry: %s", e)

        try:
            get_system_info()
        except Exception as e:
            LOG.warning("Failed to get system information: %s", e)

        try:
            crawled_data = util.log_time(
                        logfunc=LOG.debug, msg='Crawl of metadata service',
                        func=self.crawl_metadata)
        except sources.InvalidMetaDataException as e:
            LOG.warning('Could not crawl Azure metadata: %s', e)
            return False
        if (self.distro and self.distro.name == 'ubuntu' and
                self.ds_cfg.get('apply_network_config')):
            maybe_remove_ubuntu_network_config_scripts()

        # Process crawled data and augment with various config defaults
        self.cfg = util.mergemanydict(
            [crawled_data['cfg'], BUILTIN_CLOUD_CONFIG])
        self._metadata_imds = crawled_data['metadata']['imds']
        self.metadata = util.mergemanydict(
            [crawled_data['metadata'], DEFAULT_METADATA])
        self.userdata_raw = crawled_data['userdata_raw']

        user_ds_cfg = util.get_cfg_by_path(self.cfg, DS_CFG_PATH, {})
        self.ds_cfg = util.mergemanydict([user_ds_cfg, self.ds_cfg])

        # walinux agent writes files world readable, but expects
        # the directory to be protected.
        write_files(
            self.ds_cfg['data_dir'], crawled_data['files'], dirmode=0o700)
        return True

    def device_name_to_device(self, name):
        return self.ds_cfg['disk_aliases'].get(name)

    def get_config_obj(self):
        return self.cfg

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    def _iid(self, previous=None):
        prev_iid_path = os.path.join(
            self.paths.get_cpath('data'), 'instance-id')
        iid = util.read_dmi_data('system-uuid')
        if os.path.exists(prev_iid_path):
            previous = util.load_file(prev_iid_path).strip()
            if is_byte_swapped(previous, iid):
                return previous
        return iid

    @azure_ds_telemetry_reporter
    def setup(self, is_new_instance):
        if self._negotiated is False:
            LOG.debug("negotiating for %s (new_instance=%s)",
                      self.get_instance_id(), is_new_instance)
            fabric_data = self._negotiate()
            LOG.debug("negotiating returned %s", fabric_data)
            if fabric_data:
                self.metadata.update(fabric_data)
            self._negotiated = True
        else:
            LOG.debug("negotiating already done for %s",
                      self.get_instance_id())

    def _poll_imds(self):
        """Poll IMDS for the new provisioning data until we get a valid
        response. Then return the returned JSON object."""
        url = IMDS_URL + "reprovisiondata?api-version=2017-04-02"
        headers = {"Metadata": "true"}
        nl_sock = None
        report_ready = bool(not os.path.isfile(REPORTED_READY_MARKER_FILE))
        self.imds_logging_threshold = 1
        self.imds_poll_counter = 1
        dhcp_attempts = 0
        vnet_switched = False
        return_val = None

        def exc_cb(msg, exception):
            if isinstance(exception, UrlError) and exception.code == 404:
                if self.imds_poll_counter == self.imds_logging_threshold:
                    # Reducing the logging frequency as we are polling IMDS
                    self.imds_logging_threshold *= 2
                    LOG.debug("Call to IMDS with arguments %s failed "
                              "with status code %s after %s retries",
                              msg, exception.code, self.imds_poll_counter)
                    LOG.debug("Backing off logging threshold for the same "
                              "exception to %d", self.imds_logging_threshold)
                self.imds_poll_counter += 1
                return True

            # If we get an exception while trying to call IMDS, we
            # call DHCP and setup the ephemeral network to acquire the new IP.
            LOG.debug("Call to IMDS with arguments %s failed  with "
                      "status code %s", msg, exception.code)
            report_diagnostic_event("polling IMDS failed with exception %s"
                                    % exception.code)
            return False

        LOG.debug("Wait for vnetswitch to happen")
        while True:
            try:
                # Save our EphemeralDHCPv4 context to avoid repeated dhcp
                with events.ReportEventStack(
                        name="obtain-dhcp-lease",
                        description="obtain dhcp lease",
                        parent=azure_ds_reporter):
                    self._ephemeral_dhcp_ctx = EphemeralDHCPv4()
                    lease = self._ephemeral_dhcp_ctx.obtain_lease()

                if vnet_switched:
                    dhcp_attempts += 1
                if report_ready:
                    try:
                        nl_sock = netlink.create_bound_netlink_socket()
                    except netlink.NetlinkCreateSocketError as e:
                        report_diagnostic_event(e)
                        LOG.warning(e)
                        self._ephemeral_dhcp_ctx.clean_network()
                        break

                    path = REPORTED_READY_MARKER_FILE
                    LOG.info(
                        "Creating a marker file to report ready: %s", path)
                    util.write_file(path, "{pid}: {time}\n".format(
                        pid=os.getpid(), time=time()))
                    self._report_ready(lease=lease)
                    report_ready = False

                    with events.ReportEventStack(
                            name="wait-for-media-disconnect-connect",
                            description="wait for vnet switch",
                            parent=azure_ds_reporter):
                        try:
                            netlink.wait_for_media_disconnect_connect(
                                nl_sock, lease['interface'])
                        except AssertionError as error:
                            report_diagnostic_event(error)
                            LOG.error(error)
                            break

                    vnet_switched = True
                    self._ephemeral_dhcp_ctx.clean_network()
                else:
                    with events.ReportEventStack(
                            name="get-reprovision-data-from-imds",
                            description="get reprovision data from imds",
                            parent=azure_ds_reporter):
                        return_val = readurl(url,
                                             timeout=IMDS_TIMEOUT_IN_SECONDS,
                                             headers=headers,
                                             exception_cb=exc_cb,
                                             infinite=True,
                                             log_req_resp=False).contents
                    break
            except UrlError:
                # Teardown our EphemeralDHCPv4 context on failure as we retry
                self._ephemeral_dhcp_ctx.clean_network()
                pass
            finally:
                if nl_sock:
                    nl_sock.close()

        if vnet_switched:
            report_diagnostic_event("attempted dhcp %d times after reuse" %
                                    dhcp_attempts)
            report_diagnostic_event("polled imds %d times after reuse" %
                                    self.imds_poll_counter)

        return return_val

    @azure_ds_telemetry_reporter
    def _report_ready(self, lease):
        """Tells the fabric provisioning has completed """
        try:
            get_metadata_from_fabric(None, lease['unknown-245'])
        except Exception:
            LOG.warning(
                "Error communicating with Azure fabric; You may experience."
                "connectivity issues.", exc_info=True)

    def _should_reprovision(self, ret):
        """Whether or not we should poll IMDS for reprovisioning data.
        Also sets a marker file to poll IMDS.

        The marker file is used for the following scenario: the VM boots into
        this polling loop, which we expect to be proceeding infinitely until
        the VM is picked. If for whatever reason the platform moves us to a
        new host (for instance a hardware issue), we need to keep polling.
        However, since the VM reports ready to the Fabric, we will not attach
        the ISO, thus cloud-init needs to have a way of knowing that it should
        jump back into the polling loop in order to retrieve the ovf_env."""
        if not ret:
            return False
        (_md, _userdata_raw, cfg, _files) = ret
        path = REPROVISION_MARKER_FILE
        if (cfg.get('PreprovisionedVm') is True or
                os.path.isfile(path)):
            if not os.path.isfile(path):
                LOG.info("Creating a marker file to poll imds: %s",
                         path)
                util.write_file(path, "{pid}: {time}\n".format(
                    pid=os.getpid(), time=time()))
            return True
        return False

    def _reprovision(self):
        """Initiate the reprovisioning workflow."""
        contents = self._poll_imds()
        with events.ReportEventStack(
                name="reprovisioning-read-azure-ovf",
                description="read azure ovf during reprovisioning",
                parent=azure_ds_reporter):
            md, ud, cfg = read_azure_ovf(contents)
            return (md, ud, cfg, {'ovf-env.xml': contents})

    @azure_ds_telemetry_reporter
    def _negotiate(self):
        """Negotiate with fabric and return data from it.

           On success, returns a dictionary including 'public_keys'.
           On failure, returns False.
        """

        if self.ds_cfg['agent_command'] == AGENT_START_BUILTIN:
            self.bounce_network_with_azure_hostname()

            pubkey_info = self.cfg.get('_pubkeys', None)
            metadata_func = partial(get_metadata_from_fabric,
                                    fallback_lease_file=self.
                                    dhclient_lease_file,
                                    pubkey_info=pubkey_info)
        else:
            metadata_func = self.get_metadata_from_agent

        LOG.debug("negotiating with fabric via agent command %s",
                  self.ds_cfg['agent_command'])
        try:
            fabric_data = metadata_func()
        except Exception as e:
            report_diagnostic_event(
                "Error communicating with Azure fabric; You may experience "
                "connectivity issues: %s" % e)
            LOG.warning(
                "Error communicating with Azure fabric; You may experience "
                "connectivity issues.", exc_info=True)
            return False

        util.del_file(REPORTED_READY_MARKER_FILE)
        util.del_file(REPROVISION_MARKER_FILE)
        return fabric_data

    @azure_ds_telemetry_reporter
    def activate(self, cfg, is_new_instance):
        address_ephemeral_resize(is_new_instance=is_new_instance,
                                 preserve_ntfs=self.ds_cfg.get(
                                     DS_CFG_KEY_PRESERVE_NTFS, False))
        return

    @property
    def availability_zone(self):
        return self.metadata.get(
            'imds', {}).get('compute', {}).get('platformFaultDomain')

    @property
    def network_config(self):
        """Generate a network config like net.generate_fallback_network() with
           the following exceptions.

           1. Probe the drivers of the net-devices present and inject them in
              the network configuration under params: driver: <driver> value
           2. Generate a fallback network config that does not include any of
              the blacklisted devices.
        """
        if not self._network_config or self._network_config == sources.UNSET:
            if self.ds_cfg.get('apply_network_config'):
                nc_src = self._metadata_imds
            else:
                nc_src = None
            self._network_config = parse_network_config(nc_src)
        return self._network_config

    @property
    def region(self):
        return self.metadata.get('imds', {}).get('compute', {}).get('location')


def _partitions_on_device(devpath, maxnum=16):
    # return a list of tuples (ptnum, path) for each part on devpath
    for suff in ("-part", "p", ""):
        found = []
        for pnum in range(1, maxnum):
            ppath = devpath + suff + str(pnum)
            if os.path.exists(ppath):
                found.append((pnum, os.path.realpath(ppath)))
        if found:
            return found
    return []


@azure_ds_telemetry_reporter
def _has_ntfs_filesystem(devpath):
    ntfs_devices = util.find_devs_with("TYPE=ntfs", no_cache=True)
    LOG.debug('ntfs_devices found = %s', ntfs_devices)
    return os.path.realpath(devpath) in ntfs_devices


@azure_ds_telemetry_reporter
def can_dev_be_reformatted(devpath, preserve_ntfs):
    """Determine if the ephemeral drive at devpath should be reformatted.

    A fresh ephemeral disk is formatted by Azure and will:
      a.) have a partition table (dos or gpt)
      b.) have 1 partition that is ntfs formatted, or
          have 2 partitions with the second partition ntfs formatted.
          (larger instances with >2TB ephemeral disk have gpt, and will
           have a microsoft reserved partition as part 1.  LP: #1686514)
      c.) the ntfs partition will have no files other than possibly
          'dataloss_warning_readme.txt'

    User can indicate that NTFS should never be destroyed by setting
    DS_CFG_KEY_PRESERVE_NTFS in dscfg.
    If data is found on NTFS, user is warned to set DS_CFG_KEY_PRESERVE_NTFS
    to make sure cloud-init does not accidentally wipe their data.
    If cloud-init cannot mount the disk to check for data, destruction
    will be allowed, unless the dscfg key is set."""
    if preserve_ntfs:
        msg = ('config says to never destroy NTFS (%s.%s), skipping checks' %
               (".".join(DS_CFG_PATH), DS_CFG_KEY_PRESERVE_NTFS))
        return False, msg

    if not os.path.exists(devpath):
        return False, 'device %s does not exist' % devpath

    LOG.debug('Resolving realpath of %s -> %s', devpath,
              os.path.realpath(devpath))

    # devpath of /dev/sd[a-z] or /dev/disk/cloud/azure_resource
    # where partitions are "<devpath>1" or "<devpath>-part1" or "<devpath>p1"
    partitions = _partitions_on_device(devpath)
    if len(partitions) == 0:
        return False, 'device %s was not partitioned' % devpath
    elif len(partitions) > 2:
        msg = ('device %s had 3 or more partitions: %s' %
               (devpath, ' '.join([p[1] for p in partitions])))
        return False, msg
    elif len(partitions) == 2:
        cand_part, cand_path = partitions[1]
    else:
        cand_part, cand_path = partitions[0]

    if not _has_ntfs_filesystem(cand_path):
        msg = ('partition %s (%s) on device %s was not ntfs formatted' %
               (cand_part, cand_path, devpath))
        return False, msg

    @azure_ds_telemetry_reporter
    def count_files(mp):
        ignored = set(['dataloss_warning_readme.txt'])
        return len([f for f in os.listdir(mp) if f.lower() not in ignored])

    bmsg = ('partition %s (%s) on device %s was ntfs formatted' %
            (cand_part, cand_path, devpath))

    with events.ReportEventStack(
                name="mount-ntfs-and-count",
                description="mount-ntfs-and-count",
                parent=azure_ds_reporter) as evt:
        try:
            file_count = util.mount_cb(cand_path, count_files, mtype="ntfs",
                                       update_env_for_mount={'LANG': 'C'})
        except util.MountFailedError as e:
            evt.description = "cannot mount ntfs"
            if "unknown filesystem type 'ntfs'" in str(e):
                return True, (bmsg + ' but this system cannot mount NTFS,'
                              ' assuming there are no important files.'
                              ' Formatting allowed.')
            return False, bmsg + ' but mount of %s failed: %s' % (cand_part, e)

        if file_count != 0:
            evt.description = "mounted and counted %d files" % file_count
            LOG.warning("it looks like you're using NTFS on the ephemeral"
                        " disk, to ensure that filesystem does not get wiped,"
                        " set %s.%s in config", '.'.join(DS_CFG_PATH),
                        DS_CFG_KEY_PRESERVE_NTFS)
            return False, bmsg + ' but had %d files on it.' % file_count

    return True, bmsg + ' and had no important files. Safe for reformatting.'


@azure_ds_telemetry_reporter
def address_ephemeral_resize(devpath=RESOURCE_DISK_PATH, maxwait=120,
                             is_new_instance=False, preserve_ntfs=False):
    # wait for ephemeral disk to come up
    naplen = .2
    with events.ReportEventStack(
                name="wait-for-ephemeral-disk",
                description="wait for ephemeral disk",
                parent=azure_ds_reporter):
        missing = util.wait_for_files([devpath],
                                      maxwait=maxwait,
                                      naplen=naplen,
                                      log_pre="Azure ephemeral disk: ")

        if missing:
            LOG.warning("ephemeral device '%s' did"
                        " not appear after %d seconds.",
                        devpath, maxwait)
            return

    result = False
    msg = None
    if is_new_instance:
        result, msg = (True, "First instance boot.")
    else:
        result, msg = can_dev_be_reformatted(devpath, preserve_ntfs)

    LOG.debug("reformattable=%s: %s", result, msg)
    if not result:
        return

    for mod in ['disk_setup', 'mounts']:
        sempath = '/var/lib/cloud/instance/sem/config_' + mod
        bmsg = 'Marker "%s" for module "%s"' % (sempath, mod)
        if os.path.exists(sempath):
            try:
                os.unlink(sempath)
                LOG.debug('%s removed.', bmsg)
            except Exception as e:
                # python3 throws FileNotFoundError, python2 throws OSError
                LOG.warning('%s: remove failed! (%s)', bmsg, e)
        else:
            LOG.debug('%s did not exist.', bmsg)
    return


@azure_ds_telemetry_reporter
def perform_hostname_bounce(hostname, cfg, prev_hostname):
    # set the hostname to 'hostname' if it is not already set to that.
    # then, if policy is not off, bounce the interface using command
    # Returns True if the network was bounced, False otherwise.
    command = cfg['command']
    interface = cfg['interface']
    policy = cfg['policy']

    msg = ("hostname=%s policy=%s interface=%s" %
           (hostname, policy, interface))
    env = os.environ.copy()
    env['interface'] = interface
    env['hostname'] = hostname
    env['old_hostname'] = prev_hostname

    if command == "builtin":
        if util.is_FreeBSD():
            command = BOUNCE_COMMAND_FREEBSD
        elif util.which('ifup'):
            command = BOUNCE_COMMAND_IFUP
        else:
            LOG.debug(
                "Skipping network bounce: ifupdown utils aren't present.")
            # Don't bounce as networkd handles hostname DDNS updates
            return False
    LOG.debug("pubhname: publishing hostname [%s]", msg)
    shell = not isinstance(command, (list, tuple))
    # capture=False, see comments in bug 1202758 and bug 1206164.
    util.log_time(logfunc=LOG.debug, msg="publishing hostname",
                  get_uptime=True, func=util.subp,
                  kwargs={'args': command, 'shell': shell, 'capture': False,
                          'env': env})
    return True


@azure_ds_telemetry_reporter
def crtfile_to_pubkey(fname, data=None):
    pipeline = ('openssl x509 -noout -pubkey < "$0" |'
                'ssh-keygen -i -m PKCS8 -f /dev/stdin')
    (out, _err) = util.subp(['sh', '-c', pipeline, fname],
                            capture=True, data=data)
    return out.rstrip()


@azure_ds_telemetry_reporter
def pubkeys_from_crt_files(flist):
    pubkeys = []
    errors = []
    for fname in flist:
        try:
            pubkeys.append(crtfile_to_pubkey(fname))
        except util.ProcessExecutionError:
            errors.append(fname)

    if errors:
        LOG.warning("failed to convert the crt files to pubkey: %s", errors)

    return pubkeys


@azure_ds_telemetry_reporter
def write_files(datadir, files, dirmode=None):

    def _redact_password(cnt, fname):
        """Azure provides the UserPassword in plain text. So we redact it"""
        try:
            root = ET.fromstring(cnt)
            for elem in root.iter():
                if ('UserPassword' in elem.tag and
                   elem.text != DEF_PASSWD_REDACTION):
                    elem.text = DEF_PASSWD_REDACTION
            return ET.tostring(root)
        except Exception:
            LOG.critical("failed to redact userpassword in %s", fname)
            return cnt

    if not datadir:
        return
    if not files:
        files = {}
    util.ensure_dir(datadir, dirmode)
    for (name, content) in files.items():
        fname = os.path.join(datadir, name)
        if 'ovf-env.xml' in name:
            content = _redact_password(content, fname)
        util.write_file(filename=fname, content=content, mode=0o600)


@azure_ds_telemetry_reporter
def invoke_agent(cmd):
    # this is a function itself to simplify patching it for test
    if cmd:
        LOG.debug("invoking agent: %s", cmd)
        util.subp(cmd, shell=(not isinstance(cmd, list)))
    else:
        LOG.debug("not invoking agent")


def find_child(node, filter_func):
    ret = []
    if not node.hasChildNodes():
        return ret
    for child in node.childNodes:
        if filter_func(child):
            ret.append(child)
    return ret


@azure_ds_telemetry_reporter
def load_azure_ovf_pubkeys(sshnode):
    # This parses a 'SSH' node formatted like below, and returns
    # an array of dicts.
    #  [{'fingerprint': '6BE7A7C3C8A8F4B123CCA5D0C2F1BE4CA7B63ED7',
    #    'path': '/where/to/go'}]
    #
    # <SSH><PublicKeys>
    #   <PublicKey><Fingerprint>ABC</FingerPrint><Path>/x/y/z</Path>
    #   ...
    # </PublicKeys></SSH>
    # Under some circumstances, there may be a <Value> element along with the
    # Fingerprint and Path. Pass those along if they appear.
    results = find_child(sshnode, lambda n: n.localName == "PublicKeys")
    if len(results) == 0:
        return []
    if len(results) > 1:
        raise BrokenAzureDataSource("Multiple 'PublicKeys'(%s) in SSH node" %
                                    len(results))

    pubkeys_node = results[0]
    pubkeys = find_child(pubkeys_node, lambda n: n.localName == "PublicKey")

    if len(pubkeys) == 0:
        return []

    found = []
    text_node = minidom.Document.TEXT_NODE

    for pk_node in pubkeys:
        if not pk_node.hasChildNodes():
            continue

        cur = {'fingerprint': "", 'path': "", 'value': ""}
        for child in pk_node.childNodes:
            if child.nodeType == text_node or not child.localName:
                continue

            name = child.localName.lower()

            if name not in cur.keys():
                continue

            if (len(child.childNodes) != 1 or
                    child.childNodes[0].nodeType != text_node):
                continue

            cur[name] = child.childNodes[0].wholeText.strip()
        found.append(cur)

    return found


@azure_ds_telemetry_reporter
def read_azure_ovf(contents):
    try:
        dom = minidom.parseString(contents)
    except Exception as e:
        error_str = "Invalid ovf-env.xml: %s" % e
        report_diagnostic_event(error_str)
        raise BrokenAzureDataSource(error_str)

    results = find_child(dom.documentElement,
                         lambda n: n.localName == "ProvisioningSection")

    if len(results) == 0:
        raise NonAzureDataSource("No ProvisioningSection")
    if len(results) > 1:
        raise BrokenAzureDataSource("found '%d' ProvisioningSection items" %
                                    len(results))
    provSection = results[0]

    lpcs_nodes = find_child(provSection,
                            lambda n:
                            n.localName == "LinuxProvisioningConfigurationSet")

    if len(lpcs_nodes) == 0:
        raise NonAzureDataSource("No LinuxProvisioningConfigurationSet")
    if len(lpcs_nodes) > 1:
        raise BrokenAzureDataSource("found '%d' %ss" %
                                    (len(lpcs_nodes),
                                     "LinuxProvisioningConfigurationSet"))
    lpcs = lpcs_nodes[0]

    if not lpcs.hasChildNodes():
        raise BrokenAzureDataSource("no child nodes of configuration set")

    md_props = 'seedfrom'
    md = {'azure_data': {}}
    cfg = {}
    ud = ""
    password = None
    username = None

    for child in lpcs.childNodes:
        if child.nodeType == dom.TEXT_NODE or not child.localName:
            continue

        name = child.localName.lower()

        simple = False
        value = ""
        if (len(child.childNodes) == 1 and
                child.childNodes[0].nodeType == dom.TEXT_NODE):
            simple = True
            value = child.childNodes[0].wholeText

        attrs = dict([(k, v) for k, v in child.attributes.items()])

        # we accept either UserData or CustomData.  If both are present
        # then behavior is undefined.
        if name == "userdata" or name == "customdata":
            if attrs.get('encoding') in (None, "base64"):
                ud = base64.b64decode(''.join(value.split()))
            else:
                ud = value
        elif name == "username":
            username = value
        elif name == "userpassword":
            password = value
        elif name == "hostname":
            md['local-hostname'] = value
        elif name == "dscfg":
            if attrs.get('encoding') in (None, "base64"):
                dscfg = base64.b64decode(''.join(value.split()))
            else:
                dscfg = value
            cfg['datasource'] = {DS_NAME: util.load_yaml(dscfg, default={})}
        elif name == "ssh":
            cfg['_pubkeys'] = load_azure_ovf_pubkeys(child)
        elif name == "disablesshpasswordauthentication":
            cfg['ssh_pwauth'] = util.is_false(value)
        elif simple:
            if name in md_props:
                md[name] = value
            else:
                md['azure_data'][name] = value

    defuser = {}
    if username:
        defuser['name'] = username
    if password:
        defuser['lock_passwd'] = False
        if DEF_PASSWD_REDACTION != password:
            defuser['passwd'] = encrypt_pass(password)

    if defuser:
        cfg['system_info'] = {'default_user': defuser}

    if 'ssh_pwauth' not in cfg and password:
        cfg['ssh_pwauth'] = True

    cfg['PreprovisionedVm'] = _extract_preprovisioned_vm_setting(dom)

    return (md, ud, cfg)


@azure_ds_telemetry_reporter
def _extract_preprovisioned_vm_setting(dom):
    """Read the preprovision flag from the ovf. It should not
       exist unless true."""
    platform_settings_section = find_child(
        dom.documentElement,
        lambda n: n.localName == "PlatformSettingsSection")
    if not platform_settings_section or len(platform_settings_section) == 0:
        LOG.debug("PlatformSettingsSection not found")
        return False
    platform_settings = find_child(
        platform_settings_section[0],
        lambda n: n.localName == "PlatformSettings")
    if not platform_settings or len(platform_settings) == 0:
        LOG.debug("PlatformSettings not found")
        return False
    preprovisionedVm = find_child(
        platform_settings[0],
        lambda n: n.localName == "PreprovisionedVm")
    if not preprovisionedVm or len(preprovisionedVm) == 0:
        LOG.debug("PreprovisionedVm not found")
        return False
    return util.translate_bool(preprovisionedVm[0].firstChild.nodeValue)


def encrypt_pass(password, salt_id="$6$"):
    return crypt.crypt(password, salt_id + util.rand_str(strlen=16))


@azure_ds_telemetry_reporter
def _check_freebsd_cdrom(cdrom_dev):
    """Return boolean indicating path to cdrom device has content."""
    try:
        with open(cdrom_dev) as fp:
            fp.read(1024)
            return True
    except IOError:
        LOG.debug("cdrom (%s) is not configured", cdrom_dev)
    return False


@azure_ds_telemetry_reporter
def _get_random_seed(source=PLATFORM_ENTROPY_SOURCE):
    """Return content random seed file if available, otherwise,
       return None."""
    # azure / hyper-v provides random data here
    # now update ds_cfg to reflect contents pass in config
    if source is None:
        return None
    seed = util.load_file(source, quiet=True, decode=False)

    # The seed generally contains non-Unicode characters. load_file puts
    # them into a str (in python 2) or bytes (in python 3). In python 2,
    # bad octets in a str cause util.json_dumps() to throw an exception. In
    # python 3, bytes is a non-serializable type, and the handler load_file
    # uses applies b64 encoding *again* to handle it. The simplest solution
    # is to just b64encode the data and then decode it to a serializable
    # string. Same number of bits of entropy, just with 25% more zeroes.
    # There's no need to undo this base64-encoding when the random seed is
    # actually used in cc_seed_random.py.
    seed = base64.b64encode(seed).decode()

    return seed


@azure_ds_telemetry_reporter
def list_possible_azure_ds_devs():
    devlist = []
    if util.is_FreeBSD():
        cdrom_dev = "/dev/cd0"
        if _check_freebsd_cdrom(cdrom_dev):
            return [cdrom_dev]
    else:
        for fstype in ("iso9660", "udf"):
            devlist.extend(util.find_devs_with("TYPE=%s" % fstype))

    devlist.sort(reverse=True)
    return devlist


@azure_ds_telemetry_reporter
def load_azure_ds_dir(source_dir):
    ovf_file = os.path.join(source_dir, "ovf-env.xml")

    if not os.path.isfile(ovf_file):
        raise NonAzureDataSource("No ovf-env file found")

    with open(ovf_file, "rb") as fp:
        contents = fp.read()

    md, ud, cfg = read_azure_ovf(contents)
    return (md, ud, cfg, {'ovf-env.xml': contents})


def parse_network_config(imds_metadata):
    """Convert imds_metadata dictionary to network v2 configuration.

    Parses network configuration from imds metadata if present or generate
    fallback network config excluding mlx4_core devices.

    @param: imds_metadata: Dict of content read from IMDS network service.
    @return: Dictionary containing network version 2 standard configuration.
    """
    with events.ReportEventStack(
                name="parse_network_config",
                description="",
                parent=azure_ds_reporter) as evt:
        if imds_metadata != sources.UNSET and imds_metadata:
            netconfig = {'version': 2, 'ethernets': {}}
            LOG.debug('Azure: generating network configuration from IMDS')
            network_metadata = imds_metadata['network']
            for idx, intf in enumerate(network_metadata['interface']):
                # First IPv4 and/or IPv6 address will be obtained via DHCP.
                # Any additional IPs of each type will be set as static
                # addresses.
                nicname = 'eth{idx}'.format(idx=idx)
                dhcp_override = {'route-metric': (idx + 1) * 100}
                dev_config = {'dhcp4': True, 'dhcp4-overrides': dhcp_override,
                              'dhcp6': False}
                for addr_type in ('ipv4', 'ipv6'):
                    addresses = intf.get(addr_type, {}).get('ipAddress', [])
                    if addr_type == 'ipv4':
                        default_prefix = '24'
                    else:
                        default_prefix = '128'
                        if addresses:
                            dev_config['dhcp6'] = True
                            # non-primary interfaces should have a higher
                            # route-metric (cost) so default routes prefer
                            # primary nic due to lower route-metric value
                            dev_config['dhcp6-overrides'] = dhcp_override
                    for addr in addresses[1:]:
                        # Append static address config for ip > 1
                        netPrefix = intf[addr_type]['subnet'][0].get(
                            'prefix', default_prefix)
                        privateIp = addr['privateIpAddress']
                        if not dev_config.get('addresses'):
                            dev_config['addresses'] = []
                        dev_config['addresses'].append(
                            '{ip}/{prefix}'.format(
                                ip=privateIp, prefix=netPrefix))
                if dev_config:
                    mac = ':'.join(re.findall(r'..', intf['macAddress']))
                    dev_config.update(
                        {'match': {'macaddress': mac.lower()},
                         'set-name': nicname})
                    netconfig['ethernets'][nicname] = dev_config
            evt.description = "network config from imds"
        else:
            blacklist = ['mlx4_core']
            LOG.debug('Azure: generating fallback configuration')
            # generate a network config, blacklist picking mlx4_core devs
            netconfig = net.generate_fallback_config(
                blacklist_drivers=blacklist, config_driver=True)
            evt.description = "network config from fallback"
        return netconfig


@azure_ds_telemetry_reporter
def get_metadata_from_imds(fallback_nic, retries):
    """Query Azure's network metadata service, returning a dictionary.

    If network is not up, setup ephemeral dhcp on fallback_nic to talk to the
    IMDS. For more info on IMDS:
        https://docs.microsoft.com/en-us/azure/virtual-machines/windows/instance-metadata-service

    @param fallback_nic: String. The name of the nic which requires active
        network in order to query IMDS.
    @param retries: The number of retries of the IMDS_URL.

    @return: A dict of instance metadata containing compute and network
        info.
    """
    kwargs = {'logfunc': LOG.debug,
              'msg': 'Crawl of Azure Instance Metadata Service (IMDS)',
              'func': _get_metadata_from_imds, 'args': (retries,)}
    if net.is_up(fallback_nic):
        return util.log_time(**kwargs)
    else:
        try:
            with EphemeralDHCPv4WithReporting(
                    azure_ds_reporter, fallback_nic):
                return util.log_time(**kwargs)
        except Exception as e:
            report_diagnostic_event("exception while getting metadata: %s" % e)
            raise


@azure_ds_telemetry_reporter
def _get_metadata_from_imds(retries):

    url = IMDS_URL + "instance?api-version=2017-12-01"
    headers = {"Metadata": "true"}
    try:
        response = readurl(
            url, timeout=IMDS_TIMEOUT_IN_SECONDS, headers=headers,
            retries=retries, exception_cb=retry_on_url_exc)
    except Exception as e:
        msg = 'Ignoring IMDS instance metadata: %s' % e
        report_diagnostic_event(msg)
        LOG.debug(msg)
        return {}
    try:
        return util.load_json(str(response))
    except json.decoder.JSONDecodeError as e:
        report_diagnostic_event('non-json imds response' % e)
        LOG.warning(
            'Ignoring non-json IMDS instance metadata: %s', str(response))
    return {}


@azure_ds_telemetry_reporter
def maybe_remove_ubuntu_network_config_scripts(paths=None):
    """Remove Azure-specific ubuntu network config for non-primary nics.

    @param paths: List of networking scripts or directories to remove when
        present.

    In certain supported ubuntu images, static udev rules or netplan yaml
    config is delivered in the base ubuntu image to support dhcp on any
    additional interfaces which get attached by a customer at some point
    after initial boot. Since the Azure datasource can now regenerate
    network configuration as metadata reports these new devices, we no longer
    want the udev rules or netplan's 90-hotplug-azure.yaml to configure
    networking on eth1 or greater as it might collide with cloud-init's
    configuration.

    Remove the any existing extended network scripts if the datasource is
    enabled to write network per-boot.
    """
    if not paths:
        paths = UBUNTU_EXTENDED_NETWORK_SCRIPTS
    logged = False
    for path in paths:
        if os.path.exists(path):
            if not logged:
                LOG.info(
                    'Removing Ubuntu extended network scripts because'
                    ' cloud-init updates Azure network configuration on the'
                    ' following event: %s.',
                    EventType.BOOT)
                logged = True
            if os.path.isdir(path):
                util.del_dir(path)
            else:
                util.del_file(path)


def _is_platform_viable(seed_dir):
    with events.ReportEventStack(
                name="check-platform-viability",
                description="found azure asset tag",
                parent=azure_ds_reporter) as evt:

        """Check platform environment to report if this datasource may run."""
        asset_tag = util.read_dmi_data('chassis-asset-tag')
        if asset_tag == AZURE_CHASSIS_ASSET_TAG:
            return True
        msg = "Non-Azure DMI asset tag '%s' discovered." % asset_tag
        LOG.debug(msg)
        evt.description = msg
        report_diagnostic_event(msg)
        if os.path.exists(os.path.join(seed_dir, 'ovf-env.xml')):
            return True
        return False


class BrokenAzureDataSource(Exception):
    pass


class NonAzureDataSource(Exception):
    pass


# Legacy: Must be present in case we load an old pkl object
DataSourceAzureNet = DataSourceAzure

# Used to match classes to dependencies
datasources = [
    (DataSourceAzure, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
