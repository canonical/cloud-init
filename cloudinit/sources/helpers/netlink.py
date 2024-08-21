# Author: Tamilmani Manoharan <tamanoha@microsoft.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import select
import socket
import struct
from collections import namedtuple

from cloudinit import util

LOG = logging.getLogger(__name__)

# http://man7.org/linux/man-pages/man7/netlink.7.html
RTMGRP_LINK = 1
RTM_NEWLINK = 16
RTM_DELLINK = 17
RTM_GETLINK = 18
RTM_SETLINK = 19
MAX_SIZE = 65535
MSG_TYPE_OFFSET = 16
SELECT_TIMEOUT = 60

NLMSGHDR_FMT = "IHHII"
IFINFOMSG_FMT = "BHiII"
NLMSGHDR_SIZE = struct.calcsize(NLMSGHDR_FMT)
IFINFOMSG_SIZE = struct.calcsize(IFINFOMSG_FMT)
RTATTR_START_OFFSET = NLMSGHDR_SIZE + IFINFOMSG_SIZE
RTA_DATA_START_OFFSET = 4
PAD_ALIGNMENT = 4

IFLA_IFNAME = 3
IFLA_OPERSTATE = 16

# https://www.kernel.org/doc/Documentation/networking/operstates.txt
OPER_UNKNOWN = 0
OPER_NOTPRESENT = 1
OPER_DOWN = 2
OPER_LOWERLAYERDOWN = 3
OPER_TESTING = 4
OPER_DORMANT = 5
OPER_UP = 6

RTAAttr = namedtuple("RTAAttr", ["length", "rta_type", "data"])
InterfaceOperstate = namedtuple("InterfaceOperstate", ["ifname", "operstate"])
NetlinkHeader = namedtuple(
    "NetlinkHeader", ["length", "type", "flags", "seq", "pid"]
)


class NetlinkCreateSocketError(RuntimeError):
    """Raised if netlink socket fails during create or bind."""


def create_bound_netlink_socket():
    """Creates netlink socket and bind on netlink group to catch interface
    down/up events. The socket will bound only on RTMGRP_LINK (which only
    includes RTM_NEWLINK/RTM_DELLINK/RTM_GETLINK events). The socket is set to
    non-blocking mode since we're only receiving messages.

    :returns: netlink socket in non-blocking mode
    :raises: NetlinkCreateSocketError
    """
    try:
        netlink_socket = socket.socket(
            socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE
        )
        netlink_socket.bind((os.getpid(), RTMGRP_LINK))
        netlink_socket.setblocking(0)
    except socket.error as e:
        msg = "Exception during netlink socket create: %s" % e
        raise NetlinkCreateSocketError(msg) from e
    LOG.debug("Created netlink socket")
    return netlink_socket


def get_netlink_msg_header(data):
    """Gets netlink message type and length

    :param: data read from netlink socket
    :returns: netlink message type
    :raises: AssertionError if data is None or data is not >= NLMSGHDR_SIZE
    struct nlmsghdr {
               __u32 nlmsg_len;    /* Length of message including header */
               __u16 nlmsg_type;   /* Type of message content */
               __u16 nlmsg_flags;  /* Additional flags */
               __u32 nlmsg_seq;    /* Sequence number */
               __u32 nlmsg_pid;    /* Sender port ID */
    };
    """
    assert data is not None, "data is none"
    assert (
        len(data) >= NLMSGHDR_SIZE
    ), "data is smaller than netlink message header"
    msg_len, msg_type, flags, seq, pid = struct.unpack(
        NLMSGHDR_FMT, data[:MSG_TYPE_OFFSET]
    )
    LOG.debug("Got netlink msg of type %d", msg_type)
    return NetlinkHeader(msg_len, msg_type, flags, seq, pid)


def read_netlink_socket(netlink_socket, timeout=None):
    """Select and read from the netlink socket if ready.

    :param: netlink_socket: specify which socket object to read from
    :param: timeout: specify a timeout value (integer) to wait while reading,
            if none, it will block indefinitely until socket ready for read
    :returns: string of data read (max length = <MAX_SIZE>) from socket,
              if no data read, returns None
    :raises: AssertionError if netlink_socket is None
    """
    assert netlink_socket is not None, "netlink socket is none"
    read_set, _, _ = select.select([netlink_socket], [], [], timeout)
    # Incase of timeout,read_set doesn't contain netlink socket.
    # just return from this function
    if netlink_socket not in read_set:
        return None
    LOG.debug("netlink socket ready for read")
    data = netlink_socket.recv(MAX_SIZE)
    if data is None:
        LOG.error("Reading from Netlink socket returned no data")
    return data


def unpack_rta_attr(data, offset):
    """Unpack a single rta attribute.

    :param: data: string of data read from netlink socket
    :param: offset: starting offset of RTA Attribute
    :return: RTAAttr object with length, type and data. On error, return None.
    :raises: AssertionError if data is None or offset is not integer.
    """
    assert data is not None, "data is none"
    assert isinstance(offset, int), "offset is not integer"
    assert (
        offset >= RTATTR_START_OFFSET
    ), "rta offset is less than expected length"
    length = rta_type = 0
    attr_data = None
    try:
        length = struct.unpack_from("H", data, offset=offset)[0]
        rta_type = struct.unpack_from("H", data, offset=offset + 2)[0]
    except struct.error:
        return None  # Should mean our offset is >= remaining data

    # Unpack just the attribute's data. Offset by 4 to skip length/type header
    attr_data = data[offset + RTA_DATA_START_OFFSET : offset + length]
    return RTAAttr(length, rta_type, attr_data)


def read_rta_oper_state(data):
    """Reads Interface name and operational state from RTA Data.

    :param: data: string of data read from netlink socket
    :returns: InterfaceOperstate object containing if_name and oper_state.
              None if data does not contain valid IFLA_OPERSTATE and
              IFLA_IFNAME messages.
    :raises: AssertionError if data is None or length of data is
             smaller than RTATTR_START_OFFSET.
    """
    assert data is not None, "data is none"
    assert (
        len(data) > RTATTR_START_OFFSET
    ), "length of data is smaller than RTATTR_START_OFFSET"
    ifname = operstate = None
    offset = RTATTR_START_OFFSET
    while offset <= len(data):
        attr = unpack_rta_attr(data, offset)
        if not attr or attr.length == 0:
            break
        # Each attribute is 4-byte aligned. Determine pad length.
        padlen = (
            PAD_ALIGNMENT - (attr.length % PAD_ALIGNMENT)
        ) % PAD_ALIGNMENT
        offset += attr.length + padlen

        if attr.rta_type == IFLA_OPERSTATE:
            operstate = ord(attr.data)
        elif attr.rta_type == IFLA_IFNAME:
            interface_name = util.decode_binary(attr.data, "utf-8")
            ifname = interface_name.strip("\0")
    if not ifname or operstate is None:
        return None
    LOG.debug("rta attrs: ifname %s operstate %d", ifname, operstate)
    return InterfaceOperstate(ifname, operstate)


def wait_for_nic_attach_event(netlink_socket, existing_nics):
    """Block until a single nic is attached.

    :param: netlink_socket: netlink_socket to receive events
    :param: existing_nics: List of existing nics so that we can skip them.
    :raises: AssertionError if netlink_socket is none.
    """
    LOG.debug("Preparing to wait for nic attach.")
    ifname = None

    def should_continue_cb(iname, carrier, prevCarrier):
        if iname in existing_nics:
            return True
        nonlocal ifname
        ifname = iname
        return False

    # We can return even if the operational state of the new nic is DOWN
    # because we set it to UP before doing dhcp.
    read_netlink_messages(
        netlink_socket,
        None,
        [RTM_NEWLINK],
        [OPER_UP, OPER_DOWN],
        should_continue_cb,
    )
    return ifname


def wait_for_nic_detach_event(netlink_socket):
    """Block until a single nic is detached and its operational state is down.

    :param: netlink_socket: netlink_socket to receive events.
    """
    LOG.debug("Preparing to wait for nic detach.")
    ifname = None

    def should_continue_cb(iname, carrier, prevCarrier):
        nonlocal ifname
        ifname = iname
        return False

    read_netlink_messages(
        netlink_socket, None, [RTM_DELLINK], [OPER_DOWN], should_continue_cb
    )
    return ifname


def wait_for_media_disconnect_connect(netlink_socket, ifname):
    """Block until media disconnect and connect has happened on an interface.
    Listens on netlink socket to receive netlink events and when the carrier
    changes from 0 to 1, it considers event has happened and
    return from this function

    :param: netlink_socket: netlink_socket to receive events
    :param: ifname: Interface name to lookout for netlink events
    :raises: AssertionError if netlink_socket is None or ifname is None.
    """
    assert netlink_socket is not None, "netlink socket is none"
    assert ifname is not None, "interface name is none"
    assert len(ifname) > 0, "interface name cannot be empty"

    def should_continue_cb(iname, carrier, prevCarrier):
        # check for carrier down, up sequence
        isVnetSwitch = (prevCarrier == OPER_DOWN) and (carrier == OPER_UP)
        if isVnetSwitch:
            LOG.debug("Media switch happened on %s.", ifname)
            return False
        return True

    LOG.debug("Wait for media disconnect and reconnect to happen")
    read_netlink_messages(
        netlink_socket,
        ifname,
        [RTM_NEWLINK, RTM_DELLINK],
        [OPER_UP, OPER_DOWN],
        should_continue_cb,
    )


def read_netlink_messages(
    netlink_socket,
    ifname_filter,
    rtm_types,
    operstates,
    should_continue_callback,
):
    """Reads from the netlink socket until the condition specified by
    the continuation callback is met.

    :param: netlink_socket: netlink_socket to receive events.
    :param: ifname_filter: if not None, will only listen for this interface.
    :param: rtm_types: Type of netlink events to listen for.
    :param: operstates: Operational states to listen.
    :param: should_continue_callback: Specifies when to stop listening.
    """
    if netlink_socket is None:
        raise RuntimeError("Netlink socket is none")
    data = bytes()
    carrier = OPER_UP
    prevCarrier = OPER_UP
    while True:
        recv_data = read_netlink_socket(netlink_socket, SELECT_TIMEOUT)
        if recv_data is None:
            continue
        LOG.debug("read %d bytes from socket", len(recv_data))
        data += recv_data
        LOG.debug("Length of data after concat %d", len(data))
        offset = 0
        datalen = len(data)
        while offset < datalen:
            nl_msg = data[offset:]
            if len(nl_msg) < NLMSGHDR_SIZE:
                LOG.debug("Data is smaller than netlink header")
                break
            nlheader = get_netlink_msg_header(nl_msg)
            if len(nl_msg) < nlheader.length:
                LOG.debug("Partial data. Smaller than netlink message")
                break
            padlen = (nlheader.length + PAD_ALIGNMENT - 1) & ~(
                PAD_ALIGNMENT - 1
            )
            offset = offset + padlen
            LOG.debug("offset to next netlink message: %d", offset)
            # Continue if we are not interested in this message.
            if nlheader.type not in rtm_types:
                continue
            interface_state = read_rta_oper_state(nl_msg)
            if interface_state is None:
                LOG.debug("Failed to read rta attributes: %s", interface_state)
                continue
            if (
                ifname_filter is not None
                and interface_state.ifname != ifname_filter
            ):
                LOG.debug(
                    "Ignored netlink event on interface %s. Waiting for %s.",
                    interface_state.ifname,
                    ifname_filter,
                )
                continue
            if interface_state.operstate not in operstates:
                continue
            prevCarrier = carrier
            carrier = interface_state.operstate
            if not should_continue_callback(
                interface_state.ifname, carrier, prevCarrier
            ):
                return
        data = data[offset:]
