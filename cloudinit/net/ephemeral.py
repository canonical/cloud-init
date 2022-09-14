# This file is part of cloud-init. See LICENSE file for license information.

"""Module for ephemeral network context managers
"""
import contextlib
import logging
from typing import Any, Dict, List

import cloudinit.net as net
from cloudinit import subp
from cloudinit.net.dhcp import (
    NoDHCPLeaseError,
    maybe_perform_dhcp_discovery,
    parse_static_routes,
)

LOG = logging.getLogger(__name__)


class EphemeralIPv4Network:
    """Context manager which sets up temporary static network configuration.

    No operations are performed if the provided interface already has the
    specified configuration.
    This can be verified with the connectivity_url_data.
    If unconnected, bring up the interface with valid ip, prefix and broadcast.
    If router is provided setup a default route for that interface. Upon
    context exit, clean up the interface leaving no configuration behind.
    """

    def __init__(
        self,
        interface,
        ip,
        prefix_or_mask,
        broadcast,
        router=None,
        connectivity_url_data: Dict[str, Any] = None,
        static_routes=None,
    ):
        """Setup context manager and validate call signature.

        @param interface: Name of the network interface to bring up.
        @param ip: IP address to assign to the interface.
        @param prefix_or_mask: Either netmask of the format X.X.X.X or an int
            prefix.
        @param broadcast: Broadcast address for the IPv4 network.
        @param router: Optionally the default gateway IP.
        @param connectivity_url_data: Optionally, a URL to verify if a usable
           connection already exists.
        @param static_routes: Optionally a list of static routes from DHCP
        """
        if not all([interface, ip, prefix_or_mask, broadcast]):
            raise ValueError(
                "Cannot init network on {0} with {1}/{2} and bcast {3}".format(
                    interface, ip, prefix_or_mask, broadcast
                )
            )
        try:
            self.prefix = net.ipv4_mask_to_net_prefix(prefix_or_mask)
        except ValueError as e:
            raise ValueError(
                "Cannot setup network, invalid prefix or "
                "netmask: {0}".format(e)
            ) from e

        self.connectivity_url_data = connectivity_url_data
        self.interface = interface
        self.ip = ip
        self.broadcast = broadcast
        self.router = router
        self.static_routes = static_routes
        # List of commands to run to cleanup state.
        self.cleanup_cmds: List[str] = []

    def __enter__(self):
        """Perform ephemeral network setup if interface is not connected."""
        if self.connectivity_url_data:
            if net.has_url_connectivity(self.connectivity_url_data):
                LOG.debug(
                    "Skip ephemeral network setup, instance has connectivity"
                    " to %s",
                    self.connectivity_url_data["url"],
                )
                return

        self._bringup_device()

        # rfc3442 requires us to ignore the router config *if* classless static
        # routes are provided.
        #
        # https://tools.ietf.org/html/rfc3442
        #
        # If the DHCP server returns both a Classless Static Routes option and
        # a Router option, the DHCP client MUST ignore the Router option.
        #
        # Similarly, if the DHCP server returns both a Classless Static Routes
        # option and a Static Routes option, the DHCP client MUST ignore the
        # Static Routes option.
        if self.static_routes:
            self._bringup_static_routes()
        elif self.router:
            self._bringup_router()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown anything we set up."""
        for cmd in self.cleanup_cmds:
            subp.subp(cmd, capture=True)

    def _delete_address(self, address, prefix):
        """Perform the ip command to remove the specified address."""
        subp.subp(
            [
                "ip",
                "-family",
                "inet",
                "addr",
                "del",
                "%s/%s" % (address, prefix),
                "dev",
                self.interface,
            ],
            capture=True,
        )

    def _bringup_device(self):
        """Perform the ip comands to fully setup the device."""
        cidr = "{0}/{1}".format(self.ip, self.prefix)
        LOG.debug(
            "Attempting setup of ephemeral network on %s with %s brd %s",
            self.interface,
            cidr,
            self.broadcast,
        )
        try:
            subp.subp(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "add",
                    cidr,
                    "broadcast",
                    self.broadcast,
                    "dev",
                    self.interface,
                ],
                capture=True,
                update_env={"LANG": "C"},
            )
        except subp.ProcessExecutionError as e:
            if "File exists" not in str(e.stderr):
                raise
            LOG.debug(
                "Skip ephemeral network setup, %s already has address %s",
                self.interface,
                self.ip,
            )
        else:
            # Address creation success, bring up device and queue cleanup
            subp.subp(
                [
                    "ip",
                    "-family",
                    "inet",
                    "link",
                    "set",
                    "dev",
                    self.interface,
                    "up",
                ],
                capture=True,
            )
            self.cleanup_cmds.append(
                [
                    "ip",
                    "-family",
                    "inet",
                    "link",
                    "set",
                    "dev",
                    self.interface,
                    "down",
                ]
            )
            self.cleanup_cmds.append(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "del",
                    cidr,
                    "dev",
                    self.interface,
                ]
            )

    def _bringup_static_routes(self):
        # static_routes = [("169.254.169.254/32", "130.56.248.255"),
        #                  ("0.0.0.0/0", "130.56.240.1")]
        for net_address, gateway in self.static_routes:
            via_arg = []
            if gateway != "0.0.0.0":
                via_arg = ["via", gateway]
            subp.subp(
                ["ip", "-4", "route", "append", net_address]
                + via_arg
                + ["dev", self.interface],
                capture=True,
            )
            self.cleanup_cmds.insert(
                0,
                ["ip", "-4", "route", "del", net_address]
                + via_arg
                + ["dev", self.interface],
            )

    def _bringup_router(self):
        """Perform the ip commands to fully setup the router if needed."""
        # Check if a default route exists and exit if it does
        out, _ = subp.subp(["ip", "route", "show", "0.0.0.0/0"], capture=True)
        if "default" in out:
            LOG.debug(
                "Skip ephemeral route setup. %s already has default route: %s",
                self.interface,
                out.strip(),
            )
            return
        subp.subp(
            [
                "ip",
                "-4",
                "route",
                "add",
                self.router,
                "dev",
                self.interface,
                "src",
                self.ip,
            ],
            capture=True,
        )
        self.cleanup_cmds.insert(
            0,
            [
                "ip",
                "-4",
                "route",
                "del",
                self.router,
                "dev",
                self.interface,
                "src",
                self.ip,
            ],
        )
        subp.subp(
            [
                "ip",
                "-4",
                "route",
                "add",
                "default",
                "via",
                self.router,
                "dev",
                self.interface,
            ],
            capture=True,
        )
        self.cleanup_cmds.insert(
            0, ["ip", "-4", "route", "del", "default", "dev", self.interface]
        )


class EphemeralIPv6Network:
    """Context manager which sets up a ipv6 link local address

    The linux kernel assigns link local addresses on link-up, which is
    sufficient for link-local communication.
    """

    def __init__(self, interface):
        """Setup context manager and validate call signature.

        @param interface: Name of the network interface to bring up.
        @param ip: IP address to assign to the interface.
        @param prefix: IPv6 uses prefixes, not netmasks
        """
        if not interface:
            raise ValueError("Cannot init network on {0}".format(interface))

        self.interface = interface

    def __enter__(self):
        """linux kernel does autoconfiguration even when autoconf=0

        https://www.kernel.org/doc/html/latest/networking/ipv6.html
        """
        if net.read_sys_net(self.interface, "operstate") != "up":
            subp.subp(
                ["ip", "link", "set", "dev", self.interface, "up"],
                capture=False,
            )

    def __exit__(self, *_args):
        """No need to set the link to down state"""


class EphemeralDHCPv4:
    def __init__(
        self,
        iface=None,
        connectivity_url_data: Dict[str, Any] = None,
        dhcp_log_func=None,
        tmp_dir=None,
    ):
        self.iface = iface
        self._ephipv4 = None
        self.lease = None
        self.dhcp_log_func = dhcp_log_func
        self.connectivity_url_data = connectivity_url_data
        self.tmp_dir = tmp_dir

    def __enter__(self):
        """Setup sandboxed dhcp context, unless connectivity_url can already be
        reached."""
        if self.connectivity_url_data:
            if net.has_url_connectivity(self.connectivity_url_data):
                LOG.debug(
                    "Skip ephemeral DHCP setup, instance has connectivity"
                    " to %s",
                    self.connectivity_url_data,
                )
                return
        return self.obtain_lease()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown sandboxed dhcp context."""
        self.clean_network()

    def clean_network(self):
        """Exit _ephipv4 context to teardown of ip configuration performed."""
        if self.lease:
            self.lease = None
        if not self._ephipv4:
            return
        self._ephipv4.__exit__(None, None, None)

    def obtain_lease(self):
        """Perform dhcp discovery in a sandboxed environment if possible.

        @return: A dict representing dhcp options on the most recent lease
            obtained from the dhclient discovery if run, otherwise an error
            is raised.

        @raises: NoDHCPLeaseError if no leases could be obtained.
        """
        if self.lease:
            return self.lease
        leases = maybe_perform_dhcp_discovery(
            self.iface, self.dhcp_log_func, self.tmp_dir
        )
        if not leases:
            raise NoDHCPLeaseError()
        self.lease = leases[-1]
        LOG.debug(
            "Received dhcp lease on %s for %s/%s",
            self.lease["interface"],
            self.lease["fixed-address"],
            self.lease["subnet-mask"],
        )
        nmap = {
            "interface": "interface",
            "ip": "fixed-address",
            "prefix_or_mask": "subnet-mask",
            "broadcast": "broadcast-address",
            "static_routes": [
                "rfc3442-classless-static-routes",
                "classless-static-routes",
            ],
            "router": "routers",
        }
        kwargs = self.extract_dhcp_options_mapping(nmap)
        if not kwargs["broadcast"]:
            kwargs["broadcast"] = net.mask_and_ipv4_to_bcast_addr(
                kwargs["prefix_or_mask"], kwargs["ip"]
            )
        if kwargs["static_routes"]:
            kwargs["static_routes"] = parse_static_routes(
                kwargs["static_routes"]
            )
        if self.connectivity_url_data:
            kwargs["connectivity_url_data"] = self.connectivity_url_data
        ephipv4 = EphemeralIPv4Network(**kwargs)
        ephipv4.__enter__()
        self._ephipv4 = ephipv4
        return self.lease

    def extract_dhcp_options_mapping(self, nmap):
        result = {}
        for internal_reference, lease_option_names in nmap.items():
            if isinstance(lease_option_names, list):
                self.get_first_option_value(
                    internal_reference, lease_option_names, result
                )
            else:
                result[internal_reference] = self.lease.get(lease_option_names)
        return result

    def get_first_option_value(
        self, internal_mapping, lease_option_names, result
    ):
        for different_names in lease_option_names:
            if not result.get(internal_mapping):
                result[internal_mapping] = self.lease.get(different_names)


class EphemeralIPNetwork:
    """Marries together IPv4 and IPv6 ephemeral context managers"""

    def __init__(
        self,
        interface,
        ipv6: bool = False,
        ipv4: bool = True,
        tmp_dir=None,
    ):
        self.interface = interface
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.stack = contextlib.ExitStack()
        self.state_msg: str = ""
        self.tmp_dir = tmp_dir

    def __enter__(self):
        # ipv6 dualstack might succeed when dhcp4 fails
        # therefore catch exception unless only v4 is used
        try:
            if self.ipv4:
                self.stack.enter_context(
                    EphemeralDHCPv4(self.interface, tmp_dir=self.tmp_dir)
                )
            if self.ipv6:
                self.stack.enter_context(EphemeralIPv6Network(self.interface))
        # v6 link local might be usable
        # caller may want to log network state
        except NoDHCPLeaseError as e:
            if self.ipv6:
                self.state_msg = "using link-local ipv6"
            else:
                raise e
        return self

    def __exit__(self, *_args):
        self.stack.close()
