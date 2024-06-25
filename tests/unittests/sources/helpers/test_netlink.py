# Author: Tamilmani Manoharan <tamanoha@microsoft.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import codecs
import socket
import struct

from cloudinit.sources.helpers.netlink import (
    MAX_SIZE,
    OPER_DORMANT,
    OPER_DOWN,
    OPER_LOWERLAYERDOWN,
    OPER_NOTPRESENT,
    OPER_TESTING,
    OPER_UNKNOWN,
    OPER_UP,
    RTATTR_START_OFFSET,
    RTM_DELLINK,
    RTM_GETLINK,
    RTM_NEWLINK,
    RTM_SETLINK,
    NetlinkCreateSocketError,
    create_bound_netlink_socket,
    read_netlink_socket,
    read_rta_oper_state,
    unpack_rta_attr,
    wait_for_media_disconnect_connect,
    wait_for_nic_attach_event,
    wait_for_nic_detach_event,
)
from tests.unittests.helpers import CiTestCase, mock


def int_to_bytes(i):
    r"""convert integer to binary: eg: 1 to \x01"""
    hex_value = "{0:x}".format(i)
    hex_value = "0" * (len(hex_value) % 2) + hex_value
    return codecs.decode(hex_value, "hex_codec")


class TestCreateBoundNetlinkSocket(CiTestCase):
    @mock.patch("cloudinit.sources.helpers.netlink.socket.socket")
    def test_socket_error_on_create(self, m_socket):
        """create_bound_netlink_socket catches socket creation exception"""

        # NetlinkCreateSocketError is raised when socket creation errors.
        m_socket.side_effect = socket.error("Fake socket failure")
        with self.assertRaises(NetlinkCreateSocketError) as ctx_mgr:
            create_bound_netlink_socket()
        self.assertEqual(
            "Exception during netlink socket create: Fake socket failure",
            str(ctx_mgr.exception),
        )


class TestReadNetlinkSocket(CiTestCase):
    @mock.patch("cloudinit.sources.helpers.netlink.socket.socket")
    @mock.patch("cloudinit.sources.helpers.netlink.select.select")
    def test_read_netlink_socket(self, m_select, m_socket):
        """read_netlink_socket able to receive data"""
        data = "netlinktest"
        m_select.return_value = [m_socket], None, None
        m_socket.recv.return_value = data
        recv_data = read_netlink_socket(m_socket, 2)
        m_select.assert_called_with([m_socket], [], [], 2)
        m_socket.recv.assert_called_with(MAX_SIZE)
        self.assertIsNotNone(recv_data)
        self.assertEqual(recv_data, data)

    @mock.patch("cloudinit.sources.helpers.netlink.socket.socket")
    @mock.patch("cloudinit.sources.helpers.netlink.select.select")
    def test_netlink_read_timeout(self, m_select, m_socket):
        """read_netlink_socket should timeout if nothing to read"""
        m_select.return_value = [], None, None
        data = read_netlink_socket(m_socket, 1)
        m_select.assert_called_with([m_socket], [], [], 1)
        self.assertEqual(m_socket.recv.call_count, 0)
        self.assertIsNone(data)

    def test_read_invalid_socket(self):
        """read_netlink_socket raises assert error if socket is invalid"""
        socket = None
        with self.assertRaises(AssertionError) as context:
            read_netlink_socket(socket, 1)
        self.assertTrue("netlink socket is none" in str(context.exception))


class TestParseNetlinkMessage(CiTestCase):
    def test_read_rta_oper_state(self):
        """read_rta_oper_state could parse netlink message and extract data"""
        ifname = "eth0"
        bytes = ifname.encode("utf-8")
        buf = bytearray(48)
        struct.pack_into(
            "HH4sHHc",
            buf,
            RTATTR_START_OFFSET,
            8,
            3,
            bytes,
            5,
            16,
            int_to_bytes(OPER_DOWN),
        )
        interface_state = read_rta_oper_state(buf)
        self.assertEqual(interface_state.ifname, ifname)
        self.assertEqual(interface_state.operstate, OPER_DOWN)

    def test_read_none_data(self):
        """read_rta_oper_state raises assert error if data is none"""
        data = None
        with self.assertRaises(AssertionError) as context:
            read_rta_oper_state(data)
        self.assertEqual("data is none", str(context.exception))

    def test_read_invalid_rta_operstate_none(self):
        """read_rta_oper_state returns none if operstate is none"""
        ifname = "eth0"
        buf = bytearray(40)
        bytes = ifname.encode("utf-8")
        struct.pack_into("HH4s", buf, RTATTR_START_OFFSET, 8, 3, bytes)
        interface_state = read_rta_oper_state(buf)
        self.assertIsNone(interface_state)

    def test_read_invalid_rta_ifname_none(self):
        """read_rta_oper_state returns none if ifname is none"""
        buf = bytearray(40)
        struct.pack_into(
            "HHc", buf, RTATTR_START_OFFSET, 5, 16, int_to_bytes(OPER_DOWN)
        )
        interface_state = read_rta_oper_state(buf)
        self.assertIsNone(interface_state)

    def test_read_invalid_data_len(self):
        """raise assert error if data size is smaller than required size"""
        buf = bytearray(32)
        with self.assertRaises(AssertionError) as context:
            read_rta_oper_state(buf)
        self.assertTrue(
            "length of data is smaller than RTATTR_START_OFFSET"
            in str(context.exception)
        )

    def test_unpack_rta_attr_none_data(self):
        """unpack_rta_attr raises assert error if data is none"""
        data = None
        with self.assertRaises(AssertionError) as context:
            unpack_rta_attr(data, RTATTR_START_OFFSET)
        self.assertTrue("data is none" in str(context.exception))

    def test_unpack_rta_attr_invalid_offset(self):
        """unpack_rta_attr raises assert error if offset is invalid"""
        data = bytearray(48)
        with self.assertRaises(AssertionError) as context:
            unpack_rta_attr(data, "offset")
        self.assertTrue("offset is not integer" in str(context.exception))
        with self.assertRaises(AssertionError) as context:
            unpack_rta_attr(data, 31)
        self.assertTrue(
            "rta offset is less than expected length" in str(context.exception)
        )


@mock.patch("cloudinit.sources.helpers.netlink.socket.socket")
@mock.patch("cloudinit.sources.helpers.netlink.read_netlink_socket")
class TestNicAttachDetach(CiTestCase):
    with_logs = True

    def _media_switch_data(self, ifname, msg_type, operstate):
        """construct netlink data with specified fields"""
        if ifname and operstate is not None:
            data = bytearray(48)
            bytes = ifname.encode("utf-8")
            struct.pack_into(
                "HH4sHHc",
                data,
                RTATTR_START_OFFSET,
                8,
                3,
                bytes,
                5,
                16,
                int_to_bytes(operstate),
            )
        elif ifname:
            data = bytearray(40)
            bytes = ifname.encode("utf-8")
            struct.pack_into("HH4s", data, RTATTR_START_OFFSET, 8, 3, bytes)
        elif operstate:
            data = bytearray(40)
            struct.pack_into(
                "HHc",
                data,
                RTATTR_START_OFFSET,
                5,
                16,
                int_to_bytes(operstate),
            )
        struct.pack_into("=LHHLL", data, 0, len(data), msg_type, 0, 0, 0)
        return data

    def test_nic_attached_oper_down(self, m_read_netlink_socket, m_socket):
        """Test for a new nic attached"""
        ifname = "eth0"
        data_op_down = self._media_switch_data(ifname, RTM_NEWLINK, OPER_DOWN)
        m_read_netlink_socket.side_effect = [data_op_down]
        ifread = wait_for_nic_attach_event(m_socket, [])
        self.assertEqual(m_read_netlink_socket.call_count, 1)
        self.assertEqual(ifname, ifread)

    def test_nic_attached_oper_up(self, m_read_netlink_socket, m_socket):
        """Test for a new nic attached"""
        ifname = "eth0"
        data_op_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        m_read_netlink_socket.side_effect = [data_op_up]
        ifread = wait_for_nic_attach_event(m_socket, [])
        self.assertEqual(m_read_netlink_socket.call_count, 1)
        self.assertEqual(ifname, ifread)

    def test_nic_attach_ignore_existing(self, m_read_netlink_socket, m_socket):
        """Test that we read only the interfaces we are interested in."""
        data_eth0 = self._media_switch_data("eth0", RTM_NEWLINK, OPER_DOWN)
        data_eth1 = self._media_switch_data("eth1", RTM_NEWLINK, OPER_DOWN)
        m_read_netlink_socket.side_effect = [data_eth0, data_eth1]
        ifread = wait_for_nic_attach_event(m_socket, ["eth0"])
        self.assertEqual(m_read_netlink_socket.call_count, 2)
        self.assertEqual("eth1", ifread)

    def test_nic_attach_read_first(self, m_read_netlink_socket, m_socket):
        """Test that we read only the interfaces we are interested in."""
        data_eth0 = self._media_switch_data("eth0", RTM_NEWLINK, OPER_DOWN)
        data_eth1 = self._media_switch_data("eth1", RTM_NEWLINK, OPER_DOWN)
        m_read_netlink_socket.side_effect = [data_eth0, data_eth1]
        ifread = wait_for_nic_attach_event(m_socket, ["eth1"])
        self.assertEqual(m_read_netlink_socket.call_count, 1)
        self.assertEqual("eth0", ifread)

    def test_nic_detached(self, m_read_netlink_socket, m_socket):
        """Test for an existing nic detached"""
        ifname = "eth0"
        data_op_down = self._media_switch_data(ifname, RTM_DELLINK, OPER_DOWN)
        m_read_netlink_socket.side_effect = [data_op_down]
        ifread = wait_for_nic_detach_event(m_socket)
        self.assertEqual(m_read_netlink_socket.call_count, 1)
        self.assertEqual(ifname, ifread)


@mock.patch("cloudinit.sources.helpers.netlink.socket.socket")
@mock.patch("cloudinit.sources.helpers.netlink.read_netlink_socket")
class TestWaitForMediaDisconnectConnect(CiTestCase):
    with_logs = True

    def _media_switch_data(self, ifname, msg_type, operstate):
        """construct netlink data with specified fields"""
        if ifname and operstate is not None:
            data = bytearray(48)
            bytes = ifname.encode("utf-8")
            struct.pack_into(
                "HH4sHHc",
                data,
                RTATTR_START_OFFSET,
                8,
                3,
                bytes,
                5,
                16,
                int_to_bytes(operstate),
            )
        elif ifname:
            data = bytearray(40)
            bytes = ifname.encode("utf-8")
            struct.pack_into("HH4s", data, RTATTR_START_OFFSET, 8, 3, bytes)
        elif operstate:
            data = bytearray(40)
            struct.pack_into(
                "HHc",
                data,
                RTATTR_START_OFFSET,
                5,
                16,
                int_to_bytes(operstate),
            )
        struct.pack_into("=LHHLL", data, 0, len(data), msg_type, 0, 0, 0)
        return data

    def test_media_down_up_scenario(self, m_read_netlink_socket, m_socket):
        """Test for media down up sequence for required interface name"""
        ifname = "eth0"
        # construct data for Oper State down
        data_op_down = self._media_switch_data(ifname, RTM_NEWLINK, OPER_DOWN)
        # construct data for Oper State up
        data_op_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        m_read_netlink_socket.side_effect = [data_op_down, data_op_up]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 2)

    def test_wait_for_media_switch_diff_interface(
        self, m_read_netlink_socket, m_socket
    ):
        """wait_for_media_disconnect_connect ignores unexpected interfaces.

        The first two messages are for other interfaces and last two are for
        expected interface. So the function exit only after receiving last
        2 messages and therefore the call count for m_read_netlink_socket
        has to be 4
        """
        other_ifname = "eth1"
        expected_ifname = "eth0"
        data_op_down_eth1 = self._media_switch_data(
            other_ifname, RTM_NEWLINK, OPER_DOWN
        )
        data_op_up_eth1 = self._media_switch_data(
            other_ifname, RTM_NEWLINK, OPER_UP
        )
        data_op_down_eth0 = self._media_switch_data(
            expected_ifname, RTM_NEWLINK, OPER_DOWN
        )
        data_op_up_eth0 = self._media_switch_data(
            expected_ifname, RTM_NEWLINK, OPER_UP
        )
        m_read_netlink_socket.side_effect = [
            data_op_down_eth1,
            data_op_up_eth1,
            data_op_down_eth0,
            data_op_up_eth0,
        ]
        wait_for_media_disconnect_connect(m_socket, expected_ifname)
        self.assertIn(
            "Ignored netlink event on interface %s" % other_ifname,
            self.logs.getvalue(),
        )
        self.assertEqual(m_read_netlink_socket.call_count, 4)

    def test_invalid_msgtype_getlink(self, m_read_netlink_socket, m_socket):
        """wait_for_media_disconnect_connect ignores GETLINK events.

        The first two messages are for oper down and up for RTM_GETLINK type
        which netlink module will ignore. The last 2 messages are RTM_NEWLINK
        with oper state down and up messages. Therefore the call count for
        m_read_netlink_socket has to be 4 ignoring first 2 messages
        of RTM_GETLINK
        """
        ifname = "eth0"
        data_getlink_down = self._media_switch_data(
            ifname, RTM_GETLINK, OPER_DOWN
        )
        data_getlink_up = self._media_switch_data(ifname, RTM_GETLINK, OPER_UP)
        data_newlink_down = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_DOWN
        )
        data_newlink_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        m_read_netlink_socket.side_effect = [
            data_getlink_down,
            data_getlink_up,
            data_newlink_down,
            data_newlink_up,
        ]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 4)

    def test_invalid_msgtype_setlink(self, m_read_netlink_socket, m_socket):
        """wait_for_media_disconnect_connect ignores SETLINK events.

        The first two messages are for oper down and up for RTM_GETLINK type
        which it will ignore. 3rd and 4th messages are RTM_NEWLINK with down
        and up messages. This function should exit after 4th messages since it
        sees down->up scenario. So the call count for m_read_netlink_socket
        has to be 4 ignoring first 2 messages of RTM_GETLINK and
        last 2 messages of RTM_NEWLINK
        """
        ifname = "eth0"
        data_setlink_down = self._media_switch_data(
            ifname, RTM_SETLINK, OPER_DOWN
        )
        data_setlink_up = self._media_switch_data(ifname, RTM_SETLINK, OPER_UP)
        data_newlink_down = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_DOWN
        )
        data_newlink_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        m_read_netlink_socket.side_effect = [
            data_setlink_down,
            data_setlink_up,
            data_newlink_down,
            data_newlink_up,
            data_newlink_down,
            data_newlink_up,
        ]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 4)

    def test_netlink_invalid_switch_scenario(
        self, m_read_netlink_socket, m_socket
    ):
        """returns only if it receives UP event after a DOWN event"""
        ifname = "eth0"
        data_op_down = self._media_switch_data(ifname, RTM_NEWLINK, OPER_DOWN)
        data_op_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        data_op_dormant = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_DORMANT
        )
        data_op_notpresent = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_NOTPRESENT
        )
        data_op_lowerdown = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_LOWERLAYERDOWN
        )
        data_op_testing = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_TESTING
        )
        data_op_unknown = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_UNKNOWN
        )
        m_read_netlink_socket.side_effect = [
            data_op_up,
            data_op_up,
            data_op_dormant,
            data_op_up,
            data_op_notpresent,
            data_op_up,
            data_op_lowerdown,
            data_op_up,
            data_op_testing,
            data_op_up,
            data_op_unknown,
            data_op_up,
            data_op_down,
            data_op_up,
        ]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 14)

    def test_netlink_valid_inbetween_transitions(
        self, m_read_netlink_socket, m_socket
    ):
        """wait_for_media_disconnect_connect handles in between transitions"""
        ifname = "eth0"
        data_op_down = self._media_switch_data(ifname, RTM_NEWLINK, OPER_DOWN)
        data_op_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        data_op_dormant = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_DORMANT
        )
        data_op_unknown = self._media_switch_data(
            ifname, RTM_NEWLINK, OPER_UNKNOWN
        )
        m_read_netlink_socket.side_effect = [
            data_op_down,
            data_op_dormant,
            data_op_unknown,
            data_op_up,
        ]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 4)

    def test_netlink_invalid_operstate(self, m_read_netlink_socket, m_socket):
        """wait_for_media_disconnect_connect should handle invalid operstates.

        The function should not fail and return even if it receives invalid
        operstates. It always should wait for down up sequence.
        """
        ifname = "eth0"
        data_op_down = self._media_switch_data(ifname, RTM_NEWLINK, OPER_DOWN)
        data_op_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        data_op_invalid = self._media_switch_data(ifname, RTM_NEWLINK, 7)
        m_read_netlink_socket.side_effect = [
            data_op_invalid,
            data_op_up,
            data_op_down,
            data_op_invalid,
            data_op_up,
        ]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 5)

    def test_wait_invalid_socket(self, m_read_netlink_socket, m_socket):
        """wait_for_media_disconnect_connect handle none netlink socket."""
        socket = None
        ifname = "eth0"
        with self.assertRaises(AssertionError) as context:
            wait_for_media_disconnect_connect(socket, ifname)
        self.assertTrue("netlink socket is none" in str(context.exception))

    def test_wait_invalid_ifname(self, m_read_netlink_socket, m_socket):
        """wait_for_media_disconnect_connect handle none interface name"""
        ifname = None
        with self.assertRaises(AssertionError) as context:
            wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertTrue("interface name is none" in str(context.exception))
        ifname = ""
        with self.assertRaises(AssertionError) as context:
            wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertTrue(
            "interface name cannot be empty" in str(context.exception)
        )

    def test_wait_invalid_rta_attr(self, m_read_netlink_socket, m_socket):
        """wait_for_media_disconnect_connect handles invalid rta data"""
        ifname = "eth0"
        data_invalid1 = self._media_switch_data(None, RTM_NEWLINK, OPER_DOWN)
        data_invalid2 = self._media_switch_data(ifname, RTM_NEWLINK, None)
        data_op_down = self._media_switch_data(ifname, RTM_NEWLINK, OPER_DOWN)
        data_op_up = self._media_switch_data(ifname, RTM_NEWLINK, OPER_UP)
        m_read_netlink_socket.side_effect = [
            data_invalid1,
            data_invalid2,
            data_op_down,
            data_op_up,
        ]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 4)

    def test_read_multiple_netlink_msgs(self, m_read_netlink_socket, m_socket):
        """Read multiple messages in single receive call"""
        ifname = "eth0"
        bytes = ifname.encode("utf-8")
        data = bytearray(96)
        struct.pack_into("=LHHLL", data, 0, 48, RTM_NEWLINK, 0, 0, 0)
        struct.pack_into(
            "HH4sHHc",
            data,
            RTATTR_START_OFFSET,
            8,
            3,
            bytes,
            5,
            16,
            int_to_bytes(OPER_DOWN),
        )
        struct.pack_into("=LHHLL", data, 48, 48, RTM_NEWLINK, 0, 0, 0)
        struct.pack_into(
            "HH4sHHc",
            data,
            48 + RTATTR_START_OFFSET,
            8,
            3,
            bytes,
            5,
            16,
            int_to_bytes(OPER_UP),
        )
        m_read_netlink_socket.return_value = data
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 1)

    def test_read_partial_netlink_msgs(self, m_read_netlink_socket, m_socket):
        """Read partial messages in receive call"""
        ifname = "eth0"
        bytes = ifname.encode("utf-8")
        data1 = bytearray(112)
        data2 = bytearray(32)
        struct.pack_into("=LHHLL", data1, 0, 48, RTM_NEWLINK, 0, 0, 0)
        struct.pack_into(
            "HH4sHHc",
            data1,
            RTATTR_START_OFFSET,
            8,
            3,
            bytes,
            5,
            16,
            int_to_bytes(OPER_DOWN),
        )
        struct.pack_into("=LHHLL", data1, 48, 48, RTM_NEWLINK, 0, 0, 0)
        struct.pack_into(
            "HH4sHHc", data1, 80, 8, 3, bytes, 5, 16, int_to_bytes(OPER_DOWN)
        )
        struct.pack_into("=LHHLL", data1, 96, 48, RTM_NEWLINK, 0, 0, 0)
        struct.pack_into(
            "HH4sHHc", data2, 16, 8, 3, bytes, 5, 16, int_to_bytes(OPER_UP)
        )
        m_read_netlink_socket.side_effect = [data1, data2]
        wait_for_media_disconnect_connect(m_socket, ifname)
        self.assertEqual(m_read_netlink_socket.call_count, 2)
