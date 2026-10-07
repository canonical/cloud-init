# This file is part of cloud-init. See LICENSE file for license information.

"""Module for ephemeral network context managers"""

import contextlib
import logging
import threading
import time
from functools import partial
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Union,
)

import cloudinit.net as net
import cloudinit.netinfo as netinfo
from cloudinit import subp
from cloudinit.net.dhcp import (
    ALL_DHCP_CLIENTS,
    NoDHCPLeaseError,
    NoDHCPLeaseMissingDhclientError,
    maybe_perform_dhcp_discovery,
)
from cloudinit.subp import ProcessExecutionError
from cloudinit.url_helper import UrlError, wait_for_url

LOG = logging.getLogger(__name__)

# Columns of /proc/net/if_inet6: address, ifindex, prefixlen, scope, flags,
# device. Every numeric column is unprefixed hex. See
# include/uapi/linux/if_addr.h for the flag bits.
IF_INET6_SCOPE_LINK = "20"
IFA_F_TENTATIVE = 0x40
IFA_F_DADFAILED = 0x08


def _read_if_inet6() -> List[List[str]]:
    """Return the rows of /proc/net/if_inet6 split into fields.

    Empty when the file is absent, which is the case when IPv6 is disabled.
    """
    try:
        with open("/proc/net/if_inet6") as fp:
            return [
                fields
                for fields in (line.split() for line in fp)
                if len(fields) >= 6
            ]
    except OSError:
        return []


class EphemeralIPv4Network:
    """Context manager which sets up temporary static network configuration.

    No operations are performed if the provided interface already has the
    specified configuration.
    This can be verified with the connectivity_urls_data.
    If unconnected, bring up the interface with valid ip, prefix and broadcast.
    If router is provided setup a default route for that interface. Upon
    context exit, clean up the interface leaving no configuration behind.
    """

    def __init__(
        self,
        distro,
        interface,
        ip,
        prefix_or_mask,
        broadcast,
        interface_addrs_before_dhcp: dict,
        router=None,
        static_routes=None,
    ):
        """Setup context manager and validate call signature.

        @param interface: Name of the network interface to bring up.
        @param ip: IP address to assign to the interface.
        @param prefix_or_mask: Either netmask of the format X.X.X.X or an int
            prefix.
        @param broadcast: Broadcast address for the IPv4 network.
        @param router: Optionally the default gateway IP.
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

        self.interface = interface
        self.ip = ip
        self.broadcast = broadcast
        self.router = router
        self.static_routes = static_routes
        # List of commands to run to cleanup state.
        self.cleanup_cmds: List[Callable] = []
        self.distro = distro
        self.cidr = f"{self.ip}/{self.prefix}"
        self.interface_addrs_before_dhcp = interface_addrs_before_dhcp.get(
            self.interface, {}
        )

    def __enter__(self):
        """Set up ephemeral network if interface is not connected.

        This context manager handles the lifecycle of the network interface,
        addresses, routes, etc
        """

        try:
            try:
                self._bringup_device()
            except ProcessExecutionError as e:
                if "File exists" not in str(
                    e.stderr
                ) and "Address already assigned" not in str(e.stderr):
                    raise

            # rfc3442 requires us to ignore the router config *if*
            # classless static routes are provided.
            #
            # https://tools.ietf.org/html/rfc3442
            #
            # If the DHCP server returns both a Classless Static Routes
            # option and a Router option, the DHCP client MUST ignore
            # the Router option.
            #
            # Similarly, if the DHCP server returns both a Classless
            # Static Routes option and a Static Routes option, the DHCP
            # client MUST ignore the Static Routes option.
            if self.static_routes:
                self._bringup_static_routes()
            elif self.router:
                self._bringup_router()
        except ProcessExecutionError:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown anything we set up."""
        for cmd in self.cleanup_cmds:
            cmd()

    def _bringup_device(self):
        """Perform the ip commands to fully set up the device.

        Dhcp clients behave differently in how they leave link state and ip
        address assignment.

        Attempt assigning address and setting up link if needed to be done.
        Set cleanup_cmds to return the interface state to how it was prior
        to execution of the dhcp client.
        """
        LOG.debug(
            "Attempting setup of ephemeral network on %s with %s brd %s",
            self.interface,
            self.cidr,
            self.broadcast,
        )
        interface_addrs_after_dhcp: Mapping[str, Any] = (
            netinfo.netdev_info().get(self.interface, {})
        )
        has_link = interface_addrs_after_dhcp.get("up")
        had_link = self.interface_addrs_before_dhcp.get("up")
        has_ip = self.ip in [
            ip.get("ip") for ip in interface_addrs_after_dhcp.get("ipv4", {})
        ]
        had_ip = self.ip in [
            ip.get("ip")
            for ip in self.interface_addrs_before_dhcp.get("ipv4", {})
        ]

        if has_ip:
            LOG.debug(
                "Skip adding ip address: %s already has address %s",
                self.interface,
                self.ip,
            )
        else:
            self.distro.net_ops.add_addr(
                self.interface, self.cidr, self.broadcast
            )
        if has_link:
            LOG.debug(
                "Skip bringing up network link: interface %s is already up",
                self.interface,
            )
        else:
            self.distro.net_ops.link_up(self.interface, family="inet")
        if had_link:
            LOG.debug(
                "Not queueing link down: link [%s] was up prior before "
                "receiving a dhcp lease",
                self.interface,
            )
        else:
            self.cleanup_cmds.append(
                partial(
                    self.distro.net_ops.link_down,
                    self.interface,
                    family="inet",
                )
            )
        if had_ip:
            LOG.debug(
                "Not queueing address removal: address %s was assigned before "
                "receiving a dhcp lease",
                self.ip,
            )
        else:
            self.cleanup_cmds.append(
                partial(
                    self.distro.net_ops.del_addr, self.interface, self.cidr
                )
            )

    def _bringup_static_routes(self):
        # static_routes = [("169.254.169.254/32", "130.56.248.255"),
        #                  ("0.0.0.0/0", "130.56.240.1")]
        for net_address, gateway in self.static_routes:
            # Use "append" rather than "add" since the DHCP server may provide
            # rfc3442 classless static routes with multiple routes to the same
            # subnet via different routers or local interface addresses.
            #
            # In this scenario, `ip r add` fails.
            #
            # RHBZ: #2003231
            self.distro.net_ops.append_route(
                self.interface, net_address, gateway
            )
            self.cleanup_cmds.insert(
                0,
                partial(
                    self.distro.net_ops.del_route,
                    self.interface,
                    net_address,
                    gateway=gateway,
                ),
            )

    def _bringup_router(self):
        """Perform the ip commands to fully setup the router if needed."""
        # Check if a default route exists and exit if it does
        out = self.distro.net_ops.get_default_route()
        if "default" in out:
            LOG.debug(
                "Skip ephemeral route setup. %s already has default route: %s",
                self.interface,
                out.strip(),
            )
            return
        self.distro.net_ops.add_route(
            self.interface, self.router, source_address=self.ip
        )
        self.cleanup_cmds.insert(
            0,
            partial(
                self.distro.net_ops.del_route,
                self.interface,
                self.router,
                source_address=self.ip,
            ),
        )
        self.distro.net_ops.add_route(
            self.interface, "default", gateway=self.router
        )
        self.cleanup_cmds.insert(
            0,
            partial(self.distro.net_ops.del_route, self.interface, "default"),
        )


class EphemeralIPv6Network:
    """Context manager which sets up a ipv6 link local address

    The linux kernel assigns link local addresses on link-up, which is
    sufficient for link-local communication.

    When ``enable_ra`` is set the interface is additionally prepared for
    routed IPv6: router advertisements are accepted so a default route can be
    installed, and duplicate address detection on the link-local address is
    waited out. This is needed before soliciting a stateful DHCPv6 lease,
    which is how some clouds hand out a routable global address; it is left
    off by default so existing callers keep the plain link-local behaviour.
    """

    # accept_ra=2 (rather than 1) so advertisements are honoured even when
    # forwarding happens to be enabled on the interface.
    # https://www.kernel.org/doc/html/latest/networking/ipv6.html
    ra_sysctls = {
        "disable_ipv6": "0",
        "accept_ra": "2",
        "accept_ra_defrtr": "1",
    }

    def __init__(self, distro, interface, enable_ra: bool = False):
        """Setup context manager and validate call signature.

        @param distro: The distro object.
        @param interface: Name of the network interface to bring up.
        @param enable_ra: When True, accept router advertisements on the
            interface before link-up so the kernel installs a default route,
            and wait for the link-local address to leave the tentative state.
            Defaults to False to preserve the behaviour existing callers rely
            on.
        """
        if not interface:
            raise ValueError("Cannot init network on {0}".format(interface))

        self.interface = interface
        self.distro = distro
        self.enable_ra = enable_ra
        self.restore_sysctls: Dict[str, str] = {}

    def __enter__(self):
        """linux kernel does autoconfiguration even when autoconf=0

        https://www.kernel.org/doc/html/latest/networking/ipv6.html
        """
        # The kernel only sends a router solicitation on link-up, so the
        # accept_ra sysctls have to be in place before the link comes up.
        if self.enable_ra:
            self._apply_ra_sysctls()
        if net.read_sys_net(self.interface, "operstate") != "up":
            self.distro.net_ops.link_up(self.interface)
        if self.enable_ra and not self.wait_for_link_local():
            LOG.warning(
                "No usable link-local address on %s; IPv6 may not work",
                self.interface,
            )

    def __exit__(self, *_args):
        """Leave the link up, but undo any sysctl we changed."""
        for key, value in self.restore_sysctls.items():
            self._write_sysctl(key, value)

    def wait_for_link_local(
        self, max_wait: float = 5.0, interval: float = 0.05
    ) -> bool:
        """Return True once a link-local address on the interface is usable.

        dhclient -6 cannot bind its socket while the link-local address is
        still tentative, so callers have to let duplicate address detection
        finish before soliciting. Reads /proc/net/if_inet6 directly so the
        poll costs no subprocesses.
        """
        deadline = time.monotonic() + max_wait
        while True:
            for fields in _read_if_inet6():
                _addr, _idx, _plen, scope, flags, dev = fields[:6]
                if dev != self.interface or scope != IF_INET6_SCOPE_LINK:
                    continue
                if int(flags, 16) & (IFA_F_TENTATIVE | IFA_F_DADFAILED):
                    continue
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def _apply_ra_sysctls(self):
        """Turn on kernel RA handling, remembering values to restore."""
        for key, desired in self.ra_sysctls.items():
            current = self._read_sysctl(key)
            if current is None or current == desired:
                continue
            if self._write_sysctl(key, desired):
                self.restore_sysctls[key] = current

    def _sysctl_path(self, key: str) -> str:
        return "/proc/sys/net/ipv6/conf/{0}/{1}".format(self.interface, key)

    def _read_sysctl(self, key: str) -> Optional[str]:
        try:
            with open(self._sysctl_path(key)) as fp:
                return fp.read().strip()
        except OSError:
            LOG.debug(
                "Cannot read %s; IPv6 may be unavailable",
                self._sysctl_path(key),
            )
            return None

    def _write_sysctl(self, key: str, value: str) -> bool:
        try:
            with open(self._sysctl_path(key), "w") as fp:
                fp.write(value)
        except OSError as e:
            LOG.warning(
                "Failed to set %s=%s: %s", self._sysctl_path(key), value, e
            )
            return False
        return True


class EphemeralDHCPv6:
    """Context manager which configures an address from a DHCPv6 lease.

    Mirrors EphemeralDHCPv4. dhclient is run with -sf /bin/true so no
    dhclient-script side effects land on the filesystem, which means the
    leased address has to be configured here. It is a /128 because DHCPv6
    IA_NA hands out single addresses; the on-link prefix and the default
    route come from the router advertisement, so the interface must have
    been prepared by EphemeralIPv6Network(enable_ra=True).
    """

    # A DHCPv6 IA_NA address is assigned exclusively by the server, so
    # duplicate address detection cannot fail; nodad skips it and saves the
    # DAD delay before the address becomes usable.
    dhcp6_prefix = 128

    def __init__(
        self,
        distro,
        iface=None,
        connectivity_urls_data: Optional[List[Dict[str, Any]]] = None,
        dhcp_log_func: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.distro = distro
        self.iface = iface
        self.connectivity_urls_data = connectivity_urls_data or []
        self.dhcp_log_func = dhcp_log_func
        self.address: Optional[str] = None
        # Commands to run to undo what we configured.
        self.cleanup_cmds: List[List[str]] = []

    def __enter__(self):
        """Setup sandboxed dhcp6 context, unless connectivity_url can already
        be reached."""
        if imds_reached_at_url := _check_connectivity_to_imds(
            self.connectivity_urls_data
        ):
            LOG.debug(
                "Skip ephemeral DHCPv6 setup, instance has connectivity"
                " to %s",
                imds_reached_at_url,
            )
            return None
        return self.obtain_lease()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown sandboxed dhcp6 context."""
        self.clean_network()

    def clean_network(self):
        """Remove any address this context configured."""
        while self.cleanup_cmds:
            cmd = self.cleanup_cmds.pop()
            try:
                subp.subp(cmd)
            except ProcessExecutionError as e:
                LOG.debug("Failed removing ephemeral IPv6 address: %s", e)
        self.address = None

    def obtain_lease(self) -> str:
        """Solicit a DHCPv6 address and assign it to the interface.

        @return: The address obtained from the lease.
        @raises: NoDHCPLeaseError if no address could be obtained.
        """
        if self.address:
            return self.address
        client = self._select_client()
        address = client.dhcp6_discovery(
            self.iface, self.dhcp_log_func, self.distro
        )
        prefix = getattr(client, "dhcp6_prefix", self.dhcp6_prefix)
        cidr = "{0}/{1}".format(address, prefix)
        self._add_address(cidr)
        self.address = address
        return address

    def _select_client(self):
        """Return a DHCP client able to solicit DHCPv6.

        The distro's preferred client is used whenever it can do DHCPv6.
        Otherwise, fall back to any installed client that supports it. This
        only affects the DHCPv6 solicit and leaves the IPv4 path on the
        preferred client.
        """
        preferred = self.distro.dhcp_client
        if hasattr(preferred, "dhcp6_discovery"):
            return preferred
        for candidate in ALL_DHCP_CLIENTS:
            if not hasattr(candidate, "dhcp6_discovery"):
                continue
            try:
                client = candidate()
            except NoDHCPLeaseMissingDhclientError:
                continue  # not installed
            LOG.debug(
                "DHCP client %s cannot do DHCPv6, using %s instead",
                preferred.client_name,
                client.client_name,
            )
            return client
        LOG.debug(
            "No installed DHCP client supports DHCPv6, %s cannot",
            preferred.client_name,
        )
        raise NoDHCPLeaseError()

    def _add_address(self, cidr: str):
        """Configure the leased address, queueing its removal.

        nodad is requested because a DHCPv6 IA_NA address is server-assigned
        and cannot collide, so waiting out duplicate address detection would
        only delay the first metadata request.
        """
        try:
            subp.subp(
                ["ip", "-6", "addr", "add", cidr, "dev", self.iface, "nodad"],
                update_env={"LANG": "C"},
            )
        except ProcessExecutionError as e:
            # iproute2 words "already present" differently per family: IPv4
            # says "File exists", IPv6 says "address already assigned".
            # Treat both as success but do not queue a removal we do not own.
            stderr = str(e.stderr).lower()
            if "file exists" in stderr or "already assigned" in stderr:
                LOG.debug(
                    "Skip ephemeral IPv6 setup, %s already has %s",
                    self.iface,
                    cidr,
                )
                return
            raise
        self.cleanup_cmds.append(
            ["ip", "-6", "addr", "del", cidr, "dev", self.iface]
        )


class EphemeralDHCPv4:
    def __init__(
        self,
        distro,
        iface=None,
        connectivity_urls_data: Optional[List[Dict[str, Any]]] = None,
        dhcp_log_func: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.iface = iface
        self._ephipv4: Optional[EphemeralIPv4Network] = None
        self.lease: Optional[Dict[str, Any]] = None
        self.dhcp_log_func = dhcp_log_func
        self.connectivity_urls_data = connectivity_urls_data or []
        self.distro = distro
        self.interface_addrs_before_dhcp = netinfo.netdev_info()

    def __enter__(self):
        """Setup sandboxed dhcp context, unless connectivity_url can already be
        reached."""
        if imds_reached_at_url := _check_connectivity_to_imds(
            self.connectivity_urls_data
        ):
            LOG.debug(
                "Skip ephemeral DHCP setup, instance has connectivity"
                " to %s",
                imds_reached_at_url,
            )
            return None
        # If we don't have connectivity, perform dhcp discovery
        return self.obtain_lease()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown sandboxed dhcp context."""
        self.clean_network()

    def clean_network(self):
        """Exit _ephipv4 context to teardown of ip configuration performed."""
        self.lease = None
        if self._ephipv4:
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
        self.lease = maybe_perform_dhcp_discovery(
            self.distro, self.iface, self.dhcp_log_func
        )
        if not self.lease:
            raise NoDHCPLeaseError()
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
                "static_routes",
                "unknown-121",
            ],
            "router": "routers",
        }
        kwargs = self.extract_dhcp_options_mapping(nmap)
        if not kwargs["broadcast"]:
            kwargs["broadcast"] = net.mask_and_ipv4_to_bcast_addr(
                kwargs["prefix_or_mask"], kwargs["ip"]
            )
        if kwargs["static_routes"]:
            kwargs["static_routes"] = (
                self.distro.dhcp_client.parse_static_routes(
                    kwargs["static_routes"]
                )
            )
        ephipv4 = EphemeralIPv4Network(
            self.distro,
            interface_addrs_before_dhcp=self.interface_addrs_before_dhcp,
            **kwargs,
        )
        ephipv4.__enter__()
        self._ephipv4 = ephipv4
        return self.lease

    def extract_dhcp_options_mapping(self, nmap):
        lease = self.lease or {}
        result: Dict[str, Any] = {}
        for internal_reference, lease_option_names in nmap.items():
            if isinstance(lease_option_names, list):
                self.get_first_option_value(
                    internal_reference, lease_option_names, result
                )
            else:
                result[internal_reference] = lease.get(lease_option_names)
        return result

    def get_first_option_value(
        self, internal_mapping, lease_option_names, result
    ):
        lease = self.lease or {}
        for different_names in lease_option_names:
            if not result.get(internal_mapping):
                result[internal_mapping] = lease.get(different_names)


class EphemeralIPNetwork:
    """Combined ephemeral context manager for IPv4 and IPv6

    Either ipv4 or ipv6 ephemeral network may fail to initialize, but if either
    succeeds, then this context manager will not raise exception. This allows
    either ipv4 or ipv6 ephemeral network to succeed, but requires that error
    handling for networks unavailable be done within the context.
    """

    # Upper bound on how long the concurrent setup may block. init-local
    # blocks boot, and a datasource that fails here is retried from the
    # network stage, so waiting for a client's own timeout buys nothing.
    race_max_wait = 25.0

    def __init__(
        self,
        distro,
        interface,
        ipv6: bool = False,
        ipv4: bool = True,
        connectivity_urls_data: Optional[List[Dict[str, Any]]] = None,
        dhcp6: bool = False,
        enable_ra: bool = False,
    ):
        """
        Args:
            distro: The distro object
            interface: The interface to bring up
            ipv6: Whether to bring up an ipv6 network
            ipv4: Whether to bring up an ipv4 network
            connectivity_urls_data: List of url data to use for connectivity
                check before attempting to bring up ephemeral networks. If
                connectivity can be established to any of the urls, then the
                ephemeral network setup is skipped.
            dhcp6: Whether to solicit a stateful DHCPv6 lease rather than
                settling for a link-local address. Requesting it alongside
                ipv4 runs both families concurrently, because a family that
                has no server answers only once its client times out, which
                is far longer than a boot should wait.
            enable_ra: Passed to EphemeralIPv6Network so the kernel installs
                a default route from the router advertisement.
        """
        self.interface = interface
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.stack = contextlib.ExitStack()
        self.state_msg: str = ""
        self.distro = distro
        self.connectivity_urls_data = connectivity_urls_data or []
        self.dhcp6 = dhcp6
        self.enable_ra = enable_ra
        self._race_started = False
        self._race_winner: Optional[str] = None
        self._race_threads: Dict[str, threading.Thread] = {}

    def __enter__(self):
        if self.dhcp6 and self.ipv4 and self.ipv6:
            # Both families are wanted and IPv6 needs a lease rather than a
            # link-local address, so neither may be waited on serially.
            return self._enter_concurrent()
        if not self.ipv4 and not self.ipv6:
            # no ephemeral network requested, but this object still needs to
            # function as a context manager
            return self
        exceptions = []
        ephemeral_obtained = False

        # short-circuit if we already have connectivity to IMDS
        if imds_url := _check_connectivity_to_imds(
            self.connectivity_urls_data
        ):
            LOG.debug(
                "We already have connectivity to IMDS at %s, skipping DHCP.",
                imds_url,
            )
            return self

        # otherwise, attempt to bring up ephemeral network
        LOG.debug("No connectivity to IMDS, attempting DHCP setup.")

        # first try to bring up ephemeral network for ipv4 (if enabled)
        # then try to bring up ephemeral network for ipv6 (if enabled)
        if self.ipv4:
            ipv4_ephemeral_obtained, ipv4_exception = (
                self._perform_ephemeral_network_setup(ip_version="ipv4")
            )
            ephemeral_obtained |= ipv4_ephemeral_obtained
            if ipv4_exception:
                exceptions.append(ipv4_exception)
        if self.ipv6:
            ipv6_ephemeral_obtained, ipv6_exception = (
                self._perform_ephemeral_network_setup(ip_version="ipv6")
            )
            ephemeral_obtained |= ipv6_ephemeral_obtained
            if ipv6_exception:
                exceptions.append(ipv6_exception)

        # need to set this if we only have ipv6 ephemeral network
        if (self.ipv6 and ipv6_ephemeral_obtained) or not self.ipv4:
            self.state_msg = "using link-local ipv6"

        if not ephemeral_obtained:
            # Ephemeral network setup failed in linkup for both ipv4 and
            # ipv6. Raise only the first exception found.
            LOG.error(
                "Failed to bring up EphemeralIPNetwork. "
                "Datasource setup cannot continue"
            )
            raise exceptions[0]
        return self

    def _perform_ephemeral_network_setup(
        self,
        ip_version: Literal["ipv4", "ipv6"],
    ) -> Tuple[bool, Optional[Exception]]:
        """
        Attempt to bring up an ephemeral network for the specified IP version.

        Args:
            ip_version (str): The IP version to bring up ("ipv4" or "ipv6").

        Returns:
            Tuple: A tuple containing:
                - a boolean indicating whether an ephemeral network was
                    successfully obtained
                - an optional exception if ephemeral network setup failed
                    or None if successful
        """
        try:
            if ip_version == "ipv4":
                self.stack.enter_context(
                    EphemeralDHCPv4(
                        distro=self.distro,
                        iface=self.interface,
                    )
                )
            elif ip_version == "ipv6":
                self.stack.enter_context(
                    EphemeralIPv6Network(
                        self.distro,
                        self.interface,
                    )
                )
            else:
                raise ValueError(f"Unsupported IP version: {ip_version}")

            LOG.debug(
                "Successfully brought up %s for ephemeral %s networking.",
                self.interface,
                ip_version,
            )
            return True, None
        except (ProcessExecutionError, NoDHCPLeaseError) as e:
            LOG.debug(
                "Failed to bring up %s for ephemeral %s networking.",
                self.interface,
                ip_version,
            )
            return False, e

    def _enter_concurrent(self):
        """Bring up both families at once, returning as soon as one is up.

        Serial setup is not usable when both families are wanted: a family
        with no DHCP server on the link does not fail fast, it fails only
        once its client gives up, and dhclient's own default is a minute.
        Whichever family is absent would therefore add that delay to every
        boot. Running them in parallel bounds the wait by the family that
        does answer.

        The loser keeps soliciting in the background while metadata is fetched
        over the winner. At context exit, its client is stopped and its worker
        thread is joined so it cannot leak into the network stage.
        """
        if imds_url := _check_connectivity_to_imds(
            self.connectivity_urls_data
        ):
            LOG.debug(
                "We already have connectivity to IMDS at %s, skipping DHCP.",
                imds_url,
            )
            return self

        self._race_started = True
        progress = threading.Event()
        race_done = threading.Event()
        outcomes: Dict[str, Union[bool, Exception]] = {}
        stacks: Dict[str, contextlib.ExitStack] = {}
        lock = threading.Lock()

        families: Tuple[Literal["ipv4", "ipv6"], ...] = ("ipv4", "ipv6")
        self._race_threads = {
            family: threading.Thread(
                target=self._setup_family,
                args=(family, outcomes, stacks, lock, progress, race_done),
                daemon=True,
            )
            for family in families
        }
        for thread in self._race_threads.values():
            thread.start()

        # Prefer ipv4 when both report together, matching the order the serial
        # path attempts them in. A configured family only wins after its own
        # IMDS URL answers; an address alone does not prove it has a route.
        deadline = time.monotonic() + self.race_max_wait
        probed = set()
        winner = None
        candidate: Optional[Literal["ipv4", "ipv6"]] = None
        while True:
            candidate = None
            with lock:
                for family in families:
                    if outcomes.get(family) is True and family not in probed:
                        probed.add(family)
                        candidate = family
                        break
                finished = len(outcomes) == 2

            if candidate:
                if not self.connectivity_urls_data or (
                    _check_connectivity_to_imds(
                        self.connectivity_urls_data, ip_version=candidate
                    )
                ):
                    winner = candidate
                    break
                LOG.debug(
                    "Ephemeral %s network is up but its IMDS URL is not "
                    "reachable",
                    candidate,
                )
                with lock:
                    outcomes[candidate] = NoDHCPLeaseError(
                        "No IMDS connectivity over {0}".format(candidate)
                    )
                    stack = stacks.pop(candidate, None)
                if stack:
                    stack.close()
                continue

            if finished or time.monotonic() >= deadline:
                break
            # Woken as soon as either family reports, so a fast lease is not
            # held back by a polling interval.
            progress.wait(timeout=max(0.0, deadline - time.monotonic()))
            progress.clear()

        with lock:
            # A worker that finishes after this point must close its own stack
            # instead of publishing it into the snapshot below.
            race_done.set()
            for fam, stack in stacks.items():
                if fam == winner or outcomes.get(fam) is True:
                    self.stack.push(stack)
            failures = [
                outcome
                for outcome in outcomes.values()
                if isinstance(outcome, Exception)
            ]

        self._race_winner = winner
        if not winner:
            LOG.error(
                "Failed to bring up EphemeralIPNetwork. "
                "Datasource setup cannot continue"
            )
            self._reap_stragglers()
            raise failures[0] if failures else NoDHCPLeaseError()

        LOG.debug(
            "Successfully brought up %s for ephemeral %s networking.",
            self.interface,
            winner,
        )
        if winner == "ipv6":
            self.state_msg = "using ipv6"
        return self

    def _setup_family(
        self, family, outcomes, stacks, lock, progress, race_done
    ):
        """Bring up one family, recording the outcome for _enter_concurrent."""
        stack = contextlib.ExitStack()
        try:
            if family == "ipv4":
                stack.enter_context(
                    EphemeralDHCPv4(
                        distro=self.distro,
                        iface=self.interface,
                    )
                )
            else:
                stack.enter_context(
                    EphemeralIPv6Network(
                        self.distro,
                        self.interface,
                        enable_ra=self.enable_ra,
                    )
                )
                stack.enter_context(
                    EphemeralDHCPv6(self.distro, self.interface)
                )
        except (ProcessExecutionError, NoDHCPLeaseError, OSError) as e:
            LOG.debug(
                "Failed to bring up %s for ephemeral %s networking.",
                self.interface,
                family,
            )
            stack.close()
            with lock:
                outcomes[family] = e
        else:
            close_stack = False
            with lock:
                if race_done.is_set():
                    close_stack = True
                else:
                    stacks[family] = stack
                    outcomes[family] = True
            if close_stack:
                # The winner was already returned and the context may already
                # have exited, so this late stack must clean up after itself.
                stack.close()
        finally:
            progress.set()

    def _reap_stragglers(self):
        """Stop clients still soliciting for a family that lost the race.

        Dhcpcd rewrites its process title after daemonizing, so command-line
        matching cannot identify it. Its client implementation instead derives
        the per-family pidfile and kills the recorded process group. Dhclient
        retains its command line, so lease-file matching remains sufficient.
        """
        families = ("ipv4", "ipv6")
        losers = [family for family in families if family != self._race_winner]
        client = self.distro.dhcp_client
        stop_ephemeral = getattr(client, "stop_ephemeral", None)
        if stop_ephemeral:
            for family in losers:
                try:
                    stop_ephemeral(self.interface, family, self.distro)
                except (ProcessExecutionError, OSError) as e:
                    LOG.debug(
                        "Could not stop ephemeral %s client: %s", family, e
                    )

        patterns = []
        if "ipv6" in losers:
            patterns.append("/run/dhclient6.lease")
        lease_file = getattr(client, "lease_file", None)
        if "ipv4" in losers and lease_file:
            patterns.append(lease_file)
        for pattern in patterns:
            try:
                # rc 1 only means nothing matched.
                subp.subp(["pkill", "-f", pattern], rcs=[0, 1])
            except (ProcessExecutionError, OSError) as e:
                LOG.debug("Could not reap client for %s: %s", pattern, e)

        for family in losers:
            thread = self._race_threads.get(family)
            if thread and thread.is_alive():
                thread.join(timeout=1.0)

    def __exit__(self, *_args):
        if self._race_started:
            self._reap_stragglers()
        self.stack.close()


def _check_connectivity_to_imds(
    connectivity_urls_data: List[Dict[str, Any]],
    ip_version: Optional[Literal["ipv4", "ipv6"]] = None,
) -> Optional[str]:
    """
    Perform a connectivity check to the provided URLs to determine if the
    ephemeral network setup is necessary.

    This function attempts to reach one of the provided URLs and returns the
    URL that was successfully reached. If none of the URLs can be reached,
    it returns None.

    The timeout for the request is determined by the highest timeout value
    provided in the connectivity URLs data. If no timeout is provided, a
    default timeout of 5 seconds is used.

    Args:
        connectivity_urls_data: A list of dictionaries, each containing
            the following keys:
            - "url" (str): The URL to check connectivity for.
            - "headers" (dict, optional): Headers to include in the request.
            - "timeout" (int, optional): Timeout for the request in seconds.
            - "ip_version" (str, optional): Limit this URL to ipv4 or ipv6.
            - "request_method" (str, optional): HTTP method for the request.
        ip_version: If set, only URLs for this address family are attempted.
            Entries without an ip_version remain eligible for compatibility.

    Returns:
        Optional[str]: The URL that was successfully reached, or None if no
        connectivity was established.
    """

    if ip_version:
        connectivity_urls_data = [
            url_data
            for url_data in connectivity_urls_data
            if url_data.get("ip_version") in (None, ip_version)
        ]

    def _headers_cb(url):
        """
        Helper function to get headers for a given URL from the connectivity
        URLs data provided to _check_connectivity_to_imds.
        """
        headers = [
            url_data.get("headers")
            for url_data in connectivity_urls_data
            if url_data["url"] == url
        ][0]
        return headers

    if not connectivity_urls_data:
        LOG.debug(
            "No connectivity URLs provided for %s. "
            "Skipping connectivity check before ephemeral network setup.",
            ip_version or "any address family",
        )
        return None

    request_methods = {
        url_data.get("request_method", "")
        for url_data in connectivity_urls_data
    }
    if len(request_methods) != 1:
        LOG.debug("Connectivity URLs use different HTTP request methods")
        return None
    request_method = request_methods.pop()

    # if the user has provided timeout, use the highest value provided
    timeout = (
        max(url_data.get("timeout", 0) for url_data in connectivity_urls_data)
        or 5
    )  # this *should* be sufficient if connectivity is actually available
    request_kwargs = {}
    if request_method:
        request_kwargs["request_method"] = request_method

    try:
        url_that_worked, _ = wait_for_url(
            urls=[url_data["url"] for url_data in connectivity_urls_data],
            headers_cb=_headers_cb,  # get headers per URL
            timeout=timeout,
            connect_synchronously=False,  # use happy eyeballs
            max_wait=0,  # only try once
            **request_kwargs,
        )

    # wait_for_url will raise a UrlError if:
    # - request fails
    # - response is empty
    # - response is not OK
    # which is exactly what we want to catch here since if any of these
    # conditions are met, we don't have connectivity to IMDS
    except UrlError as e:
        LOG.debug(
            "Failed to reach IMDS without ephemeral network setup: %s",
            e,
        )
    else:
        # if an error occurs inside wait_for_url that does not result in a
        # UrlError, it won't raise an exception, so we need to check if
        # url_that_worked is None to determine if we have connectivity
        if not url_that_worked:
            LOG.debug("Failed to reach IMDS without ephemeral network setup.")
            return None

        return url_that_worked
    return None
