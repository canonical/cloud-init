"""A (hopefully) temporary home for network config test data."""

import textwrap

NETWORK_CONFIGS = {
    "small_suse_dhcp6": {
        "expected_sysconfig_opensuse": {
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=cf:d6:af:48:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth99": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DHCLIENT6_MODE=managed
                LLADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                STARTMODE=auto"""
            ),
        },
        "yaml_v1": textwrap.dedent(
            """
            version: 1
            config:
                # Physical interfaces.
                - type: physical
                  name: eth99
                  mac_address: c0:d6:9f:2c:e8:80
                  subnets:
                      - type: dhcp4
                      - type: dhcp6
                      - type: static
                        address: 192.168.21.3/24
                        dns_nameservers:
                          - 8.8.8.8
                          - 8.8.4.4
                        dns_search: barley.maas sach.maas
                        routes:
                          - gateway: 65.61.151.37
                            netmask: 0.0.0.0
                            network: 0.0.0.0
                            metric: 10000
                - type: physical
                  name: eth1
                  mac_address: cf:d6:af:48:e8:80
                - type: nameserver
                  address:
                    - 1.2.3.4
                    - 5.6.7.8
                  search:
                    - wark.maas
        """
        ),
        "yaml_v2": textwrap.dedent(
            """
            version: 2
            ethernets:
                eth1:
                    match:
                        macaddress: cf:d6:af:48:e8:80
                    set-name: eth1
                eth99:
                    dhcp4: true
                    dhcp6: true
                    addresses:
                    - 192.168.21.3/24
                    match:
                        macaddress: c0:d6:9f:2c:e8:80
                    nameservers:
                        addresses:
                        - 8.8.8.8
                        - 8.8.4.4
                        search:
                        - barley.maas
                        - sach.maas
                    routes:
                    -   metric: 10000
                        to: 0.0.0.0/0
                        via: 65.61.151.37
                    set-name: eth99
            """
        ),
    },
    "small_v1": {
        "expected_networkd_eth99": textwrap.dedent(
            """\
            [Match]
            Name=eth99
            MACAddress=c0:d6:9f:2c:e8:80
            [Address]
            Address=192.168.21.3/24
            [Network]
            DHCP=ipv4
            Domains=barley.maas sach.maas
            Domains=wark.maas
            DNS=1.2.3.4 5.6.7.8
            DNS=8.8.8.8 8.8.4.4
            [Route]
            Gateway=65.61.151.37
            Destination=0.0.0.0/0
            Metric=10000
        """
        ).rstrip(" "),
        "expected_networkd_eth1": textwrap.dedent(
            """\
            [Match]
            Name=eth1
            MACAddress=cf:d6:af:48:e8:80
            [Network]
            DHCP=no
            Domains=wark.maas
            DNS=1.2.3.4 5.6.7.8
        """
        ).rstrip(" "),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback
                dns-nameservers 1.2.3.4 5.6.7.8
                dns-search wark.maas

            iface eth1 inet manual

            auto eth99
            iface eth99 inet dhcp

            # control-alias eth99
            iface eth99 inet static
                address 192.168.21.3/24
                dns-nameservers 8.8.8.8 8.8.4.4
                dns-search barley.maas sach.maas
                post-up route add default gw 65.61.151.37 metric 10000 || true
                pre-down route del default gw 65.61.151.37 metric 10000 || true
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    eth1:
                        match:
                            macaddress: cf:d6:af:48:e8:80
                        set-name: eth1
                    eth99:
                        addresses:
                        - 192.168.21.3/24
                        dhcp4: true
                        match:
                            macaddress: c0:d6:9f:2c:e8:80
                        nameservers:
                            addresses:
                            - 8.8.8.8
                            - 8.8.4.4
                            search:
                            - barley.maas
                            - sach.maas
                        routes:
                        -   metric: 10000
                            to: 0.0.0.0/0
                            via: 65.61.151.37
                        set-name: eth99
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=cf:d6:af:48:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth99": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                LLADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                STARTMODE=auto"""
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=cf:d6:af:48:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth99": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEFROUTE=yes
                DEVICE=eth99
                DHCLIENT_SET_DEFAULT_ROUTE=yes
                DNS1=8.8.8.8
                DNS2=8.8.4.4
                DOMAIN="barley.maas sach.maas"
                GATEWAY=65.61.151.37
                HWADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                METRIC=10000
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
        },
        "expected_network_manager": {
            "cloud-init-eth1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1
                uuid=3c50eb47-7260-5a6d-801d-bd4f587d6b58
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=CF:D6:AF:48:E8:80

                """
            ),
            "cloud-init-eth99.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth99
                uuid=b1b88000-1f03-5360-8377-1a2205efffb4
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=C0:D6:9F:2C:E8:80

                [ipv4]
                method=auto
                may-fail=false
                address1=192.168.21.3/24
                route1=0.0.0.0/0,65.61.151.37
                dns=8.8.8.8;8.8.4.4;
                dns-search=barley.maas;sach.maas;

                """
            ),
        },
        "yaml": textwrap.dedent(
            """
            version: 1
            config:
                # Physical interfaces.
                - type: physical
                  name: eth99
                  mac_address: c0:d6:9f:2c:e8:80
                  subnets:
                      - type: dhcp4
                      - type: static
                        address: 192.168.21.3/24
                        dns_nameservers:
                          - 8.8.8.8
                          - 8.8.4.4
                        dns_search: barley.maas sach.maas
                        routes:
                          - gateway: 65.61.151.37
                            netmask: 0.0.0.0
                            network: 0.0.0.0
                            metric: 10000
                - type: physical
                  name: eth1
                  mac_address: cf:d6:af:48:e8:80
                - type: nameserver
                  address:
                    - 1.2.3.4
                    - 5.6.7.8
                  search:
                    - wark.maas
        """
        ),
    },
    # We test a separate set of configs here because v2 doesn't support
    # generic nameservers, so that aspect needs to be modified
    "small_v2": {
        "expected_networkd_eth99": textwrap.dedent(
            """\
            [Match]
            Name=eth99
            MACAddress=c0:d6:9f:2c:e8:80
            [Address]
            Address=192.168.21.3/24
            [Network]
            DHCP=ipv4
            Domains=barley.maas sach.maas
            DNS=8.8.8.8 8.8.4.4
            [Route]
            Gateway=65.61.151.37
            Destination=0.0.0.0/0
            Metric=10000
        """
        ).rstrip(" "),
        "expected_networkd_eth1": textwrap.dedent(
            """\
            [Match]
            Name=eth1
            MACAddress=cf:d6:af:48:e8:80
            [Network]
            DHCP=no
        """
        ).rstrip(" "),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            iface eth1 inet manual

            auto eth99
            iface eth99 inet dhcp

            # control-alias eth99
            iface eth99 inet static
                address 192.168.21.3/24
                dns-nameservers 8.8.8.8 8.8.4.4
                dns-search barley.maas sach.maas
                post-up route add default gw 65.61.151.37 metric 10000 || true
                pre-down route del default gw 65.61.151.37 metric 10000 || true
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=cf:d6:af:48:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth99": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                LLADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                STARTMODE=auto"""
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=cf:d6:af:48:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth99": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEFROUTE=yes
                DEVICE=eth99
                DHCLIENT_SET_DEFAULT_ROUTE=yes
                DNS1=8.8.8.8
                DNS2=8.8.4.4
                DOMAIN="barley.maas sach.maas"
                GATEWAY=65.61.151.37
                HWADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                METRIC=10000
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
        },
        "expected_network_manager": {
            "cloud-init-eth1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1
                uuid=3c50eb47-7260-5a6d-801d-bd4f587d6b58
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=CF:D6:AF:48:E8:80

                """
            ),
            "cloud-init-eth99.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth99
                uuid=b1b88000-1f03-5360-8377-1a2205efffb4
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=C0:D6:9F:2C:E8:80

                [ipv4]
                method=auto
                may-fail=false
                route1=0.0.0.0/0,65.61.151.37
                address1=192.168.21.3/24
                dns=8.8.8.8;8.8.4.4;
                dns-search=barley.maas;sach.maas;

                """
            ),
        },
        "yaml": textwrap.dedent(
            """
            version: 2
            ethernets:
                eth1:
                    match:
                        macaddress: cf:d6:af:48:e8:80
                    set-name: eth1
                eth99:
                    addresses:
                    - 192.168.21.3/24
                    dhcp4: true
                    match:
                        macaddress: c0:d6:9f:2c:e8:80
                    nameservers:
                        addresses:
                        - 8.8.8.8
                        - 8.8.4.4
                        search:
                        - barley.maas
                        - sach.maas
                    routes:
                    -   metric: 10000
                        to: 0.0.0.0/0
                        via: 65.61.151.37
                    set-name: eth99
            """
        ),
    },
    "v4_and_v6": {
        "expected_networkd": textwrap.dedent(
            """\
            [Match]
            Name=iface0
            [Network]
            DHCP=yes
        """
        ).rstrip(" "),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet dhcp

            # control-alias iface0
            iface iface0 inet6 dhcp
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        dhcp4: true
                        dhcp6: true
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DHCLIENT6_MODE=managed
                STARTMODE=auto"""
            )
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv4]
                method=auto
                may-fail=true

                [ipv6]
                method=auto
                may-fail=true

                """
            ),
        },
        "yaml_v1": textwrap.dedent(
            """\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                - {'type': 'dhcp4'}
                - {'type': 'dhcp6'}
        """
        ).rstrip(" "),
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    dhcp4: true
                    dhcp6: true
        """
        ),
    },
    "v1_ipv4_and_ipv6_static": {
        "expected_networkd": textwrap.dedent(
            """\
            [Match]
            Name=iface0
            [Link]
            MTUBytes=8999
            [Network]
            DHCP=no
            [Address]
            Address=192.168.14.2/24
            [Address]
            Address=2001:1::1/64
        """
        ).rstrip(" "),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet static
                address 192.168.14.2/24
                mtu 9000

            # control-alias iface0
            iface iface0 inet6 static
                address 2001:1::1/64
                mtu 1500
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        addresses:
                        - 192.168.14.2/24
                        - 2001:1::1/64
                        ipv6-mtu: 1500
                        mtu: 9000
        """
        ).rstrip(" "),
        "yaml_v1": textwrap.dedent(
            """\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                mtu: 8999
                subnets:
                  - type: static
                    address: 192.168.14.2/24
                    mtu: 9000
                  - type: static
                    address: 2001:1::1/64
                    mtu: 1500
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.14.2
                IPADDR6=2001:1::1/64
                NETMASK=255.255.255.0
                STARTMODE=auto
                MTU=9000
                """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=iface0
                IPADDR=192.168.14.2
                IPV6ADDR=2001:1::1/64
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                NETMASK=255.255.255.0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                MTU=9000
                IPV6_MTU=1500
                """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mtu=9000

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.14.2/24

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::1/64

                """
            ),
        },
    },
    "v2_ipv4_and_ipv6_static": {
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    addresses:
                    - 192.168.14.2/24
                    - 2001:1::1/64
                    mtu: 9000
        """
        ).rstrip(" "),
        "expected_networkd": textwrap.dedent(
            """\
            [Match]
            Name=iface0
            [Link]
            MTUBytes=9000
            [Network]
            DHCP=no
            [Address]
            Address=192.168.14.2/24
            [Address]
            Address=2001:1::1/64
        """
        ).rstrip(" "),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet static
                address 192.168.14.2/24
                mtu 9000

            # control-alias iface0
            iface iface0 inet6 static
                address 2001:1::1/64
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        addresses:
                        - 192.168.14.2/24
                        - 2001:1::1/64
                        mtu: 9000
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.14.2
                IPADDR6=2001:1::1/64
                NETMASK=255.255.255.0
                STARTMODE=auto
                MTU=9000
                """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=iface0
                IPADDR=192.168.14.2
                IPV6ADDR=2001:1::1/64
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                NETMASK=255.255.255.0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                MTU=9000
                """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mtu=9000

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.14.2/24

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::1/64

                """
            ),
        },
    },
    "v6_and_v4": {
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DHCLIENT6_MODE=managed
                STARTMODE=auto"""
            )
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv6]
                method=auto
                may-fail=true

                [ipv4]
                method=auto
                may-fail=true

                """
            ),
        },
        "yaml": textwrap.dedent(
            """\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                  - type: dhcp6
                  - type: dhcp4
        """
        ).rstrip(" "),
        # Do not include a yaml_v2 here as it renders exactly the same as
        # the v4_and_v6 case, and that's fine
    },
    "dhcpv6_only": {
        "expected_networkd": textwrap.dedent(
            """\
            [Match]
            Name=iface0
            [Network]
            DHCP=ipv6
        """
        ).rstrip(" "),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 dhcp
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        dhcp6: true
        """
        ).rstrip(" "),
        "yaml_v1": textwrap.dedent(
            """\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                - {'type': 'dhcp6'}
        """
        ).rstrip(" "),
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
            """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                STARTMODE=auto
                """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=iface0
                DHCPV6C=yes
                IPV6INIT=yes
                DEVICE=iface0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv6]
                method=auto
                may-fail=false

                """
            ),
        },
    },
    "dhcpv6_accept_ra": {
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 dhcp
                accept_ra 1
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        accept-ra: true
                        dhcp6: true
        """
        ).rstrip(" "),
        "yaml_v1": textwrap.dedent(
            """\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                - {'type': 'dhcp6'}
                accept-ra: true
        """
        ).rstrip(" "),
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
                    accept-ra: true
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=iface0
                DHCPV6C=yes
                IPV6INIT=yes
                IPV6_FORCE_ACCEPT_RA=yes
                DEVICE=iface0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            ),
        },
        "expected_networkd": textwrap.dedent(
            """\
                [Match]
                Name=iface0
                [Network]
                DHCP=ipv6
                IPv6AcceptRA=True
            """
        ).rstrip(" "),
    },
    "dhcpv6_reject_ra": {
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 dhcp
                accept_ra 0
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        accept-ra: false
                        dhcp6: true
        """
        ).rstrip(" "),
        "yaml_v1": textwrap.dedent(
            """\
            version: 1
            config:
            - type: 'physical'
              name: 'iface0'
              subnets:
              - {'type': 'dhcp6'}
              accept-ra: false
        """
        ).rstrip(" "),
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
                    accept-ra: false
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=iface0
                DHCPV6C=yes
                IPV6INIT=yes
                IPV6_FORCE_ACCEPT_RA=no
                DEVICE=iface0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            ),
        },
        "expected_networkd": textwrap.dedent(
            """\
                [Match]
                Name=iface0
                [Network]
                DHCP=ipv6
                IPv6AcceptRA=False
            """
        ).rstrip(" "),
    },
    "ipv6_slaac": {
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 auto
                dhcp 0
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    iface0:
                        dhcp6: true
        """
        ).rstrip(" "),
        "yaml": textwrap.dedent(
            """\
            version: 1
            config:
            - type: 'physical'
              name: 'iface0'
              subnets:
              - {'type': 'ipv6_slaac'}
        """
        ).rstrip(" "),
        # A yaml_v2 doesn't make sense here as the configuration looks exactly
        # the same as the dhcpv6_only test.
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=info
                STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=iface0
                IPV6_AUTOCONF=yes
                IPV6INIT=yes
                DEVICE=iface0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv6]
                method=auto
                may-fail=false

                [ipv4]
                method=disabled

                """
            ),
        },
    },
    "static6": {
        "yaml_v1": textwrap.dedent(
            """\
        version: 1
        config:
          - type: 'physical'
            name: 'iface0'
            accept-ra: 'no'
            subnets:
            - type: 'static6'
              address: 2001:1::1/64
    """
        ).rstrip(" "),
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    accept-ra: false
                    addresses:
                    - 2001:1::1/64
            """
        ),
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
            BOOTPROTO=none
            DEVICE=iface0
            IPV6ADDR=2001:1::1/64
            IPV6INIT=yes
            IPV6_AUTOCONF=no
            IPV6_FORCE_ACCEPT_RA=no
            DEVICE=iface0
            ONBOOT=yes
            TYPE=Ethernet
            USERCTL=no
            """
            ),
        },
    },
    "dhcpv6_stateless": {
        "expected_eni": textwrap.dedent(
            """\
        auto lo
        iface lo inet loopback

        auto iface0
        iface iface0 inet6 auto
            dhcp 1
    """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
        network:
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
    """
        ).rstrip(" "),
        "yaml": textwrap.dedent(
            """\
        version: 1
        config:
          - type: 'physical'
            name: 'iface0'
            subnets:
            - {'type': 'ipv6_dhcpv6-stateless'}
    """
        ).rstrip(" "),
        # yaml_v2 makes no sense here as it would be the exact same
        # configuration as the dhcpv6_only test
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
            BOOTPROTO=dhcp6
            DHCLIENT6_MODE=info
            STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
            BOOTPROTO=none
            DEVICE=iface0
            DHCPV6C=yes
            DHCPV6C_OPTIONS=-S
            IPV6_AUTOCONF=yes
            IPV6INIT=yes
            DEVICE=iface0
            ONBOOT=yes
            TYPE=Ethernet
            USERCTL=no
            """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv6]
                method=auto
                may-fail=false

                [ipv4]
                method=disabled

                """
            ),
        },
    },
    "dhcpv6_stateful": {
        "expected_eni": textwrap.dedent(
            """\
        auto lo
        iface lo inet loopback

        auto iface0
        iface iface0 inet6 dhcp
    """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
        network:
            version: 2
            ethernets:
                iface0:
                    accept-ra: true
                    dhcp6: true
    """
        ).rstrip(" "),
        "yaml": textwrap.dedent(
            """\
        version: 1
        config:
          - type: 'physical'
            name: 'iface0'
            subnets:
            - {'type': 'ipv6_dhcpv6-stateful'}
            accept-ra: true
    """
        ).rstrip(" "),
        # yaml_v2 makes no sense here as it would be the exact same
        # configuration as the dhcpv6_only test
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
            BOOTPROTO=dhcp6
            DHCLIENT6_MODE=managed
            STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
            BOOTPROTO=none
            DEVICE=iface0
            DHCPV6C=yes
            IPV6INIT=yes
            IPV6_AUTOCONF=no
            IPV6_FAILURE_FATAL=yes
            IPV6_FORCE_ACCEPT_RA=yes
            DEVICE=iface0
            ONBOOT=yes
            TYPE=Ethernet
            USERCTL=no
            """
            ),
        },
    },
    "wakeonlan_disabled": {
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet dhcp
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                ethernets:
                    iface0:
                        dhcp4: true
                        wakeonlan: false
                version: 2
        """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=iface0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv4]
                method=auto
                may-fail=false

                """
            ),
        },
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    dhcp4: true
                    wakeonlan: false
        """
        ).rstrip(" "),
    },
    "wakeonlan_enabled": {
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet dhcp
                ethernet-wol g
        """
        ).rstrip(" "),
        "expected_netplan": textwrap.dedent(
            """
            network:
                ethernets:
                    iface0:
                        dhcp4: true
                        wakeonlan: true
                version: 2
        """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                ETHTOOL_OPTS="wol g"
                STARTMODE=auto
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-iface0": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=iface0
                ETHTOOL_OPTS="wol g"
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            ),
        },
        "expected_network_manager": {
            "cloud-init-iface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init iface0
                uuid=8ddfba48-857c-5e86-ac09-1b43eae0bf70
                autoconnect-priority=120
                type=ethernet
                interface-name=iface0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                wake-on-lan=64

                [ipv4]
                method=auto
                may-fail=false

                """
            ),
        },
        "yaml_v2": textwrap.dedent(
            """\
            version: 2
            ethernets:
                iface0:
                    dhcp4: true
                    wakeonlan: true
        """
        ).rstrip(" "),
    },
    "large_v1": {
        "expected_eni": """\
auto lo
iface lo inet loopback
    dns-nameservers 8.8.8.8 4.4.4.4 8.8.4.4
    dns-search barley.maas wark.maas foobar.maas

iface eth0 inet manual

auto eth1
iface eth1 inet manual
    bond-master bond0
    bond-mode active-backup
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto eth2
iface eth2 inet manual
    bond-master bond0
    bond-mode active-backup
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

iface eth3 inet manual

iface eth4 inet manual

# control-manual eth5
iface eth5 inet dhcp

auto ib0
iface ib0 inet static
    address 192.168.200.7/24
    mtu 9000
    hwaddress a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1

auto bond0
iface bond0 inet6 dhcp
    bond-mode active-backup
    bond-slaves none
    bond-xmit-hash-policy layer3+4
    bond_miimon 100
    hwaddress aa:bb:cc:dd:ee:ff

auto br0
iface br0 inet static
    address 192.168.14.2/24
    bridge_ageing 250
    bridge_bridgeprio 22
    bridge_fd 1
    bridge_gcint 2
    bridge_hello 1
    bridge_maxage 10
    bridge_pathcost eth3 50
    bridge_pathcost eth4 75
    bridge_portprio eth3 28
    bridge_portprio eth4 14
    bridge_ports eth3 eth4
    bridge_stp off
    bridge_waitport 1 eth3
    bridge_waitport 2 eth4
    hwaddress bb:bb:bb:bb:bb:aa

# control-alias br0
iface br0 inet6 static
    address 2001:1::1/64
    post-up route add -A inet6 default gw 2001:4800:78ff:1b::1 || true
    pre-down route del -A inet6 default gw 2001:4800:78ff:1b::1 || true

auto bond0.200
iface bond0.200 inet dhcp
    vlan-raw-device bond0
    vlan_id 200

auto eth0.101
iface eth0.101 inet static
    address 192.168.0.2/24
    dns-nameservers 192.168.0.10 10.23.23.134
    dns-search barley.maas sacchromyces.maas brettanomyces.maas
    gateway 192.168.0.1
    mtu 1500
    hwaddress aa:bb:cc:dd:ee:11
    vlan-raw-device eth0
    vlan_id 101

# control-alias eth0.101
iface eth0.101 inet static
    address 192.168.2.10/24

post-up route add -net 10.0.0.0/8 gw 11.0.0.1 metric 3 || true
pre-down route del -net 10.0.0.0/8 gw 11.0.0.1 metric 3 || true
""",
        "expected_netplan": textwrap.dedent(
            """
            network:
                version: 2
                ethernets:
                    eth0:
                        match:
                            macaddress: c0:d6:9f:2c:e8:80
                        set-name: eth0
                    eth1:
                        match:
                            macaddress: aa:d6:9f:2c:e8:80
                        set-name: eth1
                    eth2:
                        match:
                            macaddress: c0:bb:9f:2c:e8:80
                        set-name: eth2
                    eth3:
                        match:
                            macaddress: 66:bb:9f:2c:e8:80
                        set-name: eth3
                    eth4:
                        match:
                            macaddress: 98:bb:9f:2c:e8:80
                        set-name: eth4
                    eth5:
                        dhcp4: true
                        match:
                            macaddress: 98:bb:9f:2c:e8:8a
                        set-name: eth5
                bonds:
                    bond0:
                        dhcp6: true
                        interfaces:
                        - eth1
                        - eth2
                        macaddress: aa:bb:cc:dd:ee:ff
                        parameters:
                            mii-monitor-interval: 100
                            mode: active-backup
                            transmit-hash-policy: layer3+4
                bridges:
                    br0:
                        addresses:
                        - 192.168.14.2/24
                        - 2001:1::1/64
                        interfaces:
                        - eth3
                        - eth4
                        macaddress: bb:bb:bb:bb:bb:aa
                        nameservers:
                            addresses:
                            - 8.8.8.8
                            - 4.4.4.4
                            - 8.8.4.4
                            search:
                            - barley.maas
                            - wark.maas
                            - foobar.maas
                        parameters:
                            ageing-time: 250
                            forward-delay: 1
                            hello-time: 1
                            max-age: 10
                            path-cost:
                                eth3: 50
                                eth4: 75
                            port-priority:
                                eth3: 28
                                eth4: 14
                            priority: 22
                            stp: false
                        routes:
                        -   to: ::/0
                            via: 2001:4800:78ff:1b::1
                vlans:
                    bond0.200:
                        dhcp4: true
                        id: 200
                        link: bond0
                    eth0.101:
                        addresses:
                        - 192.168.0.2/24
                        - 192.168.2.10/24
                        id: 101
                        link: eth0
                        macaddress: aa:bb:cc:dd:ee:11
                        mtu: 1500
                        nameservers:
                            addresses:
                            - 192.168.0.10
                            - 10.23.23.134
                            search:
                            - barley.maas
                            - sacchromyces.maas
                            - brettanomyces.maas
                        routes:
                        -   to: default
                            via: 192.168.0.1
        """
        ).rstrip(" "),
        "expected_sysconfig_opensuse": {
            "ifcfg-bond0": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BONDING_MODULE_OPTS="mode=active-backup """
                """xmit_hash_policy=layer3+4 """
                """miimon=100"
                BONDING_SLAVE_0=eth1
                BONDING_SLAVE_1=eth2
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                LLADDR=aa:bb:cc:dd:ee:ff
                STARTMODE=auto"""
            ),
            "ifcfg-bond0.200": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                ETHERDEVICE=bond0
                STARTMODE=auto
                VLAN_ID=200"""
            ),
            "ifcfg-br0": textwrap.dedent(
                """\
                BRIDGE_AGEINGTIME=250
                BOOTPROTO=static
                IPADDR=192.168.14.2
                IPADDR6=2001:1::1/64
                LLADDRESS=bb:bb:bb:bb:bb:aa
                NETMASK=255.255.255.0
                BRIDGE_PRIORITY=22
                BRIDGE_PORTS='eth3 eth4'
                STARTMODE=auto
                BRIDGE_STP=off"""
            ),
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=c0:d6:9f:2c:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth0.101": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.0.2
                IPADDR1=192.168.2.10
                MTU=1500
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ETHERDEVICE=eth0
                STARTMODE=auto
                VLAN_ID=101"""
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                LLADDR=aa:d6:9f:2c:e8:80
                STARTMODE=hotplug"""
            ),
            "ifcfg-eth2": textwrap.dedent(
                """\
                BOOTPROTO=none
                LLADDR=c0:bb:9f:2c:e8:80
                STARTMODE=hotplug"""
            ),
            "ifcfg-eth3": textwrap.dedent(
                """\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=66:bb:9f:2c:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth4": textwrap.dedent(
                """\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=98:bb:9f:2c:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth5": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                LLADDR=98:bb:9f:2c:e8:8a
                STARTMODE=manual"""
            ),
            "ifcfg-ib0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                IPADDR=192.168.200.7
                MTU=9000
                NETMASK=255.255.255.0
                STARTMODE=auto
                TYPE=InfiniBand"""
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-bond0": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BONDING_OPTS="mode=active-backup """
                """xmit_hash_policy=layer3+4 """
                """miimon=100"
                BONDING_SLAVE0=eth1
                BONDING_SLAVE1=eth2
                BOOTPROTO=none
                DEVICE=bond0
                DHCPV6C=yes
                IPV6INIT=yes
                MACADDR=aa:bb:cc:dd:ee:ff
                ONBOOT=yes
                TYPE=Bond
                USERCTL=no"""
            ),
            "ifcfg-bond0.200": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=bond0.200
                DHCLIENT_SET_DEFAULT_ROUTE=no
                ONBOOT=yes
                PHYSDEV=bond0
                USERCTL=no
                VLAN=yes"""
            ),
            "ifcfg-br0": textwrap.dedent(
                """\
                AGEING=250
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=br0
                IPADDR=192.168.14.2
                IPV6ADDR=2001:1::1/64
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                IPV6_DEFAULTGW=2001:4800:78ff:1b::1
                MACADDR=bb:bb:bb:bb:bb:aa
                NETMASK=255.255.255.0
                ONBOOT=yes
                PRIO=22
                STP=no
                TYPE=Bridge
                USERCTL=no"""
            ),
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=c0:d6:9f:2c:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth0.101": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=eth0.101
                DNS1=192.168.0.10
                DNS2=10.23.23.134
                DOMAIN="barley.maas sacchromyces.maas brettanomyces.maas"
                GATEWAY=192.168.0.1
                IPADDR=192.168.0.2
                IPADDR1=192.168.2.10
                MTU=1500
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ONBOOT=yes
                PHYSDEV=eth0
                USERCTL=no
                VLAN=yes"""
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=aa:d6:9f:2c:e8:80
                MASTER=bond0
                ONBOOT=yes
                SLAVE=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth2": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth2
                HWADDR=c0:bb:9f:2c:e8:80
                MASTER=bond0
                ONBOOT=yes
                SLAVE=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth3": textwrap.dedent(
                """\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth3
                HWADDR=66:bb:9f:2c:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth4": textwrap.dedent(
                """\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth4
                HWADDR=98:bb:9f:2c:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth5": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=eth5
                DHCLIENT_SET_DEFAULT_ROUTE=no
                HWADDR=98:bb:9f:2c:e8:8a
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-ib0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=ib0
                HWADDR=a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                IPADDR=192.168.200.7
                MTU=9000
                NETMASK=255.255.255.0
                ONBOOT=yes
                TYPE=InfiniBand
                USERCTL=no"""
            ),
        },
        "expected_network_manager": {
            "cloud-init-eth3.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth3
                uuid=b7e95dda-7746-5bf8-bf33-6e5f3c926790
                autoconnect-priority=120
                type=ethernet
                slave-type=bridge
                master=dee46ce4-af7a-5e7c-aa08-b25533ae9213

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=66:BB:9F:2C:E8:80

                """
            ),
            "cloud-init-eth5.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth5
                uuid=5fda13c7-9942-5e90-a41b-1d043bd725dc
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=98:BB:9F:2C:E8:8A

                [ipv4]
                method=auto
                may-fail=false
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-ib0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init ib0
                uuid=11a1dda7-78b4-5529-beba-d9b5f549ad7b
                autoconnect-priority=120
                type=infiniband

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [infiniband]
                transport-mode=datagram
                mtu=9000
                mac-address=A0:00:02:20:FE:80:00:00:00:00:00:00:EC:0D:9A:03:00:15:E2:C1

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.200.7/24
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-bond0.200.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0.200
                uuid=88984a9c-ff22-5233-9267-86315e0acaa7
                autoconnect-priority=120
                type=vlan
                interface-name=bond0.200

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [vlan]
                id=200
                parent=54317911-f840-516b-a10d-82cb4c1f075c

                [ipv4]
                method=auto
                may-fail=false
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=C0:D6:9F:2C:E8:80

                """
            ),
            "cloud-init-eth4.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth4
                uuid=e27e4959-fb50-5580-b9a4-2073554627b9
                autoconnect-priority=120
                type=ethernet
                slave-type=bridge
                master=dee46ce4-af7a-5e7c-aa08-b25533ae9213

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=98:BB:9F:2C:E8:80

                """
            ),
            "cloud-init-eth1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1
                uuid=3c50eb47-7260-5a6d-801d-bd4f587d6b58
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:D6:9F:2C:E8:80

                """
            ),
            "cloud-init-br0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init br0
                uuid=dee46ce4-af7a-5e7c-aa08-b25533ae9213
                autoconnect-priority=120
                type=bridge
                interface-name=br0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bridge]
                stp=false
                priority=22
                mac-address=BB:BB:BB:BB:BB:AA

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.14.2/24
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::1/64
                route1=::/0,2001:4800:78ff:1b::1
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-eth0.101.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0.101
                uuid=b5acec5e-db80-5935-8b02-0d5619fc42bf
                autoconnect-priority=120
                type=vlan
                interface-name=eth0.101

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [vlan]
                id=101
                parent=1dd9a779-d327-56e1-8454-c65e2556c12c

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.0.2/24
                gateway=192.168.0.1
                address2=192.168.2.10/24
                dns=192.168.0.10;10.23.23.134;
                dns-search=barley.maas;sacchromyces.maas;brettanomyces.maas;

                """
            ),
            "cloud-init-bond0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0
                uuid=54317911-f840-516b-a10d-82cb4c1f075c
                autoconnect-priority=120
                type=bond
                interface-name=bond0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bond]
                mode=active-backup
                miimon=100
                xmit_hash_policy=layer3+4

                [ipv6]
                method=auto
                may-fail=false
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-eth2.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth2
                uuid=5559a242-3421-5fdd-896e-9cb8313d5804
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=C0:BB:9F:2C:E8:80

                """
            ),
        },
        "yaml": textwrap.dedent(
            """
            version: 1
            config:
                # Physical interfaces.
                - type: physical
                  name: eth0
                  mac_address: c0:d6:9f:2c:e8:80
                - type: physical
                  name: eth1
                  mac_address: aa:d6:9f:2c:e8:80
                - type: physical
                  name: eth2
                  mac_address: c0:bb:9f:2c:e8:80
                - type: physical
                  name: eth3
                  mac_address: 66:bb:9f:2c:e8:80
                - type: physical
                  name: eth4
                  mac_address: 98:bb:9f:2c:e8:80
                # specify how ifupdown should treat iface
                # control is one of ['auto', 'hotplug', 'manual']
                # with manual meaning ifup/ifdown should not affect the iface
                # useful for things like iscsi root + dhcp
                - type: physical
                  name: eth5
                  mac_address: 98:bb:9f:2c:e8:8a
                  subnets:
                    - type: dhcp
                      control: manual
                # VLAN interface.
                - type: vlan
                  name: eth0.101
                  vlan_link: eth0
                  vlan_id: 101
                  mac_address: aa:bb:cc:dd:ee:11
                  mtu: 1500
                  subnets:
                    - type: static
                      # When 'mtu' matches device-level mtu, no warnings
                      mtu: 1500
                      address: 192.168.0.2/24
                      gateway: 192.168.0.1
                      dns_nameservers:
                        - 192.168.0.10
                        - 10.23.23.134
                      dns_search:
                        - barley.maas
                        - sacchromyces.maas
                        - brettanomyces.maas
                    - type: static
                      address: 192.168.2.10/24
                # Bond.
                - type: bond
                  name: bond0
                  # if 'mac_address' is omitted, the MAC is taken from
                  # the first slave.
                  mac_address: aa:bb:cc:dd:ee:ff
                  bond_interfaces:
                    - eth1
                    - eth2
                  params:
                    bond-mode: active-backup
                    bond_miimon: 100
                    bond-xmit-hash-policy: "layer3+4"
                  subnets:
                    - type: dhcp6
                # A Bond VLAN.
                - type: vlan
                  name: bond0.200
                  vlan_link: bond0
                  vlan_id: 200
                  subnets:
                      - type: dhcp4
                # An infiniband
                - type: infiniband
                  name: ib0
                  mac_address: >-
                    a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                  subnets:
                      - type: static
                        address: 192.168.200.7/24
                        mtu: 9000
                # A bridge.
                - type: bridge
                  name: br0
                  bridge_interfaces:
                      - eth3
                      - eth4
                  ipv4_conf:
                      rp_filter: 1
                      proxy_arp: 0
                      forwarding: 1
                  ipv6_conf:
                      autoconf: 1
                      disable_ipv6: 1
                      use_tempaddr: 1
                      forwarding: 1
                      # basically anything in /proc/sys/net/ipv6/conf/.../
                  mac_address: bb:bb:bb:bb:bb:aa
                  params:
                      bridge_ageing: 250
                      bridge_bridgeprio: 22
                      bridge_fd: 1
                      bridge_gcint: 2
                      bridge_hello: 1
                      bridge_maxage: 10
                      bridge_maxwait: 0
                      bridge_pathcost:
                        - eth3 50
                        - eth4 75
                      bridge_portprio:
                        - eth3 28
                        - eth4 14
                      bridge_stp: 'off'
                      bridge_waitport:
                        - 1 eth3
                        - 2 eth4
                  subnets:
                      - type: static
                        address: 192.168.14.2/24
                      - type: static
                        address: 2001:1::1/64 # default to /64
                        routes:
                          - gateway: 2001:4800:78ff:1b::1
                            netmask: '::'
                            network: '::'
                # A global nameserver.
                - type: nameserver
                  address: 8.8.8.8
                  search: barley.maas
                # global nameservers and search in list form
                - type: nameserver
                  address:
                    - 4.4.4.4
                    - 8.8.4.4
                  search:
                    - wark.maas
                    - foobar.maas
                # A global route.
                - type: route
                  destination: 10.0.0.0/8
                  gateway: 11.0.0.1
                  metric: 3
        """
        ).lstrip(),
    },
    "large_v2": {
        "expected_eni": """\
auto lo
iface lo inet loopback
    dns-nameservers 8.8.8.8 4.4.4.4 8.8.4.4
    dns-search barley.maas wark.maas foobar.maas

iface eth0 inet manual

auto eth1
iface eth1 inet manual
    bond-master bond0
    bond-mode active-backup
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto eth2
iface eth2 inet manual
    bond-master bond0
    bond-mode active-backup
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

iface eth3 inet manual

iface eth4 inet manual

# control-manual eth5
iface eth5 inet dhcp

auto ib0
iface ib0 inet static
    address 192.168.200.7/24
    mtu 9000
    hwaddress a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1

auto bond0
iface bond0 inet6 dhcp
    bond-mode active-backup
    bond-slaves none
    bond-xmit-hash-policy layer3+4
    bond_miimon 100
    hwaddress aa:bb:cc:dd:ee:ff

auto br0
iface br0 inet static
    address 192.168.14.2/24
    bridge_ageing 250
    bridge_bridgeprio 22
    bridge_fd 1
    bridge_gcint 2
    bridge_hello 1
    bridge_maxage 10
    bridge_pathcost eth3 50
    bridge_pathcost eth4 75
    bridge_portprio eth3 28
    bridge_portprio eth4 14
    bridge_ports eth3 eth4
    bridge_stp off
    bridge_waitport 1 eth3
    bridge_waitport 2 eth4
    hwaddress bb:bb:bb:bb:bb:aa

# control-alias br0
iface br0 inet6 static
    address 2001:1::1/64
    post-up route add -A inet6 default gw 2001:4800:78ff:1b::1 || true
    pre-down route del -A inet6 default gw 2001:4800:78ff:1b::1 || true

auto bond0.200
iface bond0.200 inet dhcp
    vlan-raw-device bond0
    vlan_id 200

auto eth0.101
iface eth0.101 inet static
    address 192.168.0.2/24
    dns-nameservers 192.168.0.10 10.23.23.134
    dns-search barley.maas sacchromyces.maas brettanomyces.maas
    gateway 192.168.0.1
    mtu 1500
    hwaddress aa:bb:cc:dd:ee:11
    vlan-raw-device eth0
    vlan_id 101

# control-alias eth0.101
iface eth0.101 inet static
    address 192.168.2.10/24

post-up route add -net 10.0.0.0/8 gw 11.0.0.1 metric 3 || true
pre-down route del -net 10.0.0.0/8 gw 11.0.0.1 metric 3 || true
""",
        "expected_sysconfig_opensuse": {
            "ifcfg-bond0": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BONDING_MODULE_OPTS="mode=active-backup """
                """xmit_hash_policy=layer3+4 """
                """miimon=100"
                BONDING_SLAVE_0=eth1
                BONDING_SLAVE_1=eth2
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                LLADDR=aa:bb:cc:dd:ee:ff
                STARTMODE=auto"""
            ),
            "ifcfg-bond0.200": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                ETHERDEVICE=bond0
                STARTMODE=auto
                VLAN_ID=200"""
            ),
            "ifcfg-br0": textwrap.dedent(
                """\
                BRIDGE_AGEINGTIME=250
                BOOTPROTO=static
                IPADDR=192.168.14.2
                IPADDR6=2001:1::1/64
                LLADDRESS=bb:bb:bb:bb:bb:aa
                NETMASK=255.255.255.0
                BRIDGE_PRIORITY=22
                BRIDGE_PORTS='eth3 eth4'
                STARTMODE=auto
                BRIDGE_STP=off"""
            ),
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=c0:d6:9f:2c:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth0.101": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.0.2
                IPADDR1=192.168.2.10
                MTU=1500
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ETHERDEVICE=eth0
                STARTMODE=auto
                VLAN_ID=101"""
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                LLADDR=aa:d6:9f:2c:e8:80
                STARTMODE=hotplug"""
            ),
            "ifcfg-eth2": textwrap.dedent(
                """\
                BOOTPROTO=none
                LLADDR=c0:bb:9f:2c:e8:80
                STARTMODE=hotplug"""
            ),
            "ifcfg-eth3": textwrap.dedent(
                """\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=66:bb:9f:2c:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth4": textwrap.dedent(
                """\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=98:bb:9f:2c:e8:80
                STARTMODE=auto"""
            ),
            "ifcfg-eth5": textwrap.dedent(
                """\
                BOOTPROTO=dhcp4
                LLADDR=98:bb:9f:2c:e8:8a
                STARTMODE=manual"""
            ),
            "ifcfg-ib0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                IPADDR=192.168.200.7
                MTU=9000
                NETMASK=255.255.255.0
                STARTMODE=auto
                TYPE=InfiniBand"""
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-bond0": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BONDING_OPTS="mode=active-backup """
                """xmit_hash_policy=layer3+4 """
                """miimon=100"
                BONDING_SLAVE0=eth1
                BONDING_SLAVE1=eth2
                BOOTPROTO=none
                DEVICE=bond0
                DHCPV6C=yes
                IPV6INIT=yes
                MACADDR=aa:bb:cc:dd:ee:ff
                ONBOOT=yes
                TYPE=Bond
                USERCTL=no"""
            ),
            "ifcfg-bond0.200": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=bond0.200
                DHCLIENT_SET_DEFAULT_ROUTE=no
                ONBOOT=yes
                PHYSDEV=bond0
                USERCTL=no
                VLAN=yes"""
            ),
            "ifcfg-br0": textwrap.dedent(
                """\
                AGEING=250
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=br0
                IPADDR=192.168.14.2
                IPV6ADDR=2001:1::1/64
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                IPV6_DEFAULTGW=2001:4800:78ff:1b::1
                MACADDR=bb:bb:bb:bb:bb:aa
                NETMASK=255.255.255.0
                ONBOOT=yes
                PRIO=22
                STP=no
                TYPE=Bridge
                USERCTL=no"""
            ),
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=c0:d6:9f:2c:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth0.101": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=eth0.101
                DNS1=192.168.0.10
                DNS2=10.23.23.134
                DOMAIN="barley.maas sacchromyces.maas brettanomyces.maas"
                GATEWAY=192.168.0.1
                IPADDR=192.168.0.2
                IPADDR1=192.168.2.10
                MTU=1500
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ONBOOT=yes
                PHYSDEV=eth0
                USERCTL=no
                VLAN=yes"""
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=aa:d6:9f:2c:e8:80
                MASTER=bond0
                ONBOOT=yes
                SLAVE=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth2": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth2
                HWADDR=c0:bb:9f:2c:e8:80
                MASTER=bond0
                ONBOOT=yes
                SLAVE=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth3": textwrap.dedent(
                """\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth3
                HWADDR=66:bb:9f:2c:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth4": textwrap.dedent(
                """\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth4
                HWADDR=98:bb:9f:2c:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-eth5": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=eth5
                DHCLIENT_SET_DEFAULT_ROUTE=no
                HWADDR=98:bb:9f:2c:e8:8a
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-ib0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=ib0
                HWADDR=a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                IPADDR=192.168.200.7
                MTU=9000
                NETMASK=255.255.255.0
                ONBOOT=yes
                TYPE=InfiniBand
                USERCTL=no"""
            ),
        },
        "expected_network_manager": {
            "cloud-init-eth3.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth3
                uuid=b7e95dda-7746-5bf8-bf33-6e5f3c926790
                autoconnect-priority=120
                type=ethernet
                slave-type=bridge
                master=dee46ce4-af7a-5e7c-aa08-b25533ae9213

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=66:BB:9F:2C:E8:80

                """
            ),
            "cloud-init-eth5.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth5
                uuid=5fda13c7-9942-5e90-a41b-1d043bd725dc
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=98:BB:9F:2C:E8:8A

                [ipv4]
                method=auto
                may-fail=false
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-ib0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init ib0
                uuid=11a1dda7-78b4-5529-beba-d9b5f549ad7b
                autoconnect-priority=120
                type=infiniband

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [infiniband]
                transport-mode=datagram
                mtu=9000
                mac-address=A0:00:02:20:FE:80:00:00:00:00:00:00:EC:0D:9A:03:00:15:E2:C1

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.200.7/24
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-bond0.200.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0.200
                uuid=88984a9c-ff22-5233-9267-86315e0acaa7
                autoconnect-priority=120
                type=vlan
                interface-name=bond0.200

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [vlan]
                id=200
                parent=54317911-f840-516b-a10d-82cb4c1f075c

                [ipv4]
                method=auto
                may-fail=false
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=C0:D6:9F:2C:E8:80

                """
            ),
            "cloud-init-eth4.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth4
                uuid=e27e4959-fb50-5580-b9a4-2073554627b9
                autoconnect-priority=120
                type=ethernet
                slave-type=bridge
                master=dee46ce4-af7a-5e7c-aa08-b25533ae9213

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=98:BB:9F:2C:E8:80

                """
            ),
            "cloud-init-eth1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1
                uuid=3c50eb47-7260-5a6d-801d-bd4f587d6b58
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:D6:9F:2C:E8:80

                """
            ),
            "cloud-init-br0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init br0
                uuid=dee46ce4-af7a-5e7c-aa08-b25533ae9213
                autoconnect-priority=120
                type=bridge
                interface-name=br0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bridge]
                stp=false
                priority=22
                mac-address=BB:BB:BB:BB:BB:AA

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.14.2/24
                dns=8.8.8.8;4.4.4.4;8.8.4.4;
                dns-search=barley.maas;wark.maas;foobar.maas;

                [ipv6]
                route1=::/0,2001:4800:78ff:1b::1
                method=manual
                may-fail=false
                address1=2001:1::1/64
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-eth0.101.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0.101
                uuid=b5acec5e-db80-5935-8b02-0d5619fc42bf
                autoconnect-priority=120
                type=vlan
                interface-name=eth0.101

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [vlan]
                id=101
                parent=1dd9a779-d327-56e1-8454-c65e2556c12c

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.0.2/24
                route1=0.0.0.0/0,192.168.0.1
                address2=192.168.2.10/24
                dns=192.168.0.10;10.23.23.134;
                dns-search=barley.maas;sacchromyces.maas;brettanomyces.maas;

                """
            ),
            "cloud-init-bond0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0
                uuid=54317911-f840-516b-a10d-82cb4c1f075c
                autoconnect-priority=120
                type=bond
                interface-name=bond0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bond]
                mode=active-backup
                miimon=100
                xmit_hash_policy=layer3+4

                [ipv6]
                method=auto
                may-fail=false
                dns-search=barley.maas;wark.maas;foobar.maas;

                """
            ),
            "cloud-init-eth2.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth2
                uuid=5559a242-3421-5fdd-896e-9cb8313d5804
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=C0:BB:9F:2C:E8:80

                """
            ),
        },
        "yaml": textwrap.dedent(
            """
            version: 2
            ethernets:
                eth0:
                    match:
                        macaddress: c0:d6:9f:2c:e8:80
                    set-name: eth0
                eth1:
                    match:
                        macaddress: aa:d6:9f:2c:e8:80
                    set-name: eth1
                eth2:
                    match:
                        macaddress: c0:bb:9f:2c:e8:80
                    set-name: eth2
                eth3:
                    match:
                        macaddress: 66:bb:9f:2c:e8:80
                    set-name: eth3
                eth4:
                    match:
                        macaddress: 98:bb:9f:2c:e8:80
                    set-name: eth4
                eth5:
                    dhcp4: true
                    match:
                        macaddress: 98:bb:9f:2c:e8:8a
                    set-name: eth5
            bonds:
                bond0:
                    dhcp6: true
                    interfaces:
                      - eth1
                      - eth2
                    macaddress: aa:bb:cc:dd:ee:ff
                    parameters:
                        mii-monitor-interval: 100
                        mode: active-backup
                        transmit-hash-policy: layer3+4
            bridges:
                br0:
                    addresses:
                      - 192.168.14.2/24
                      - 2001:1::1/64
                    interfaces:
                      - eth3
                      - eth4
                    macaddress: bb:bb:bb:bb:bb:aa
                    nameservers:
                        addresses:
                          - 8.8.8.8
                          - 4.4.4.4
                          - 8.8.4.4
                        search:
                          - barley.maas
                          - wark.maas
                          - foobar.maas
                    parameters:
                        ageing-time: 250
                        forward-delay: 1
                        hello-time: 1
                        max-age: 10
                        path-cost:
                            eth3: 50
                            eth4: 75
                        port-priority:
                            eth3: 28
                            eth4: 14
                        priority: 22
                        stp: false
                    routes:
                      - to: ::/0
                        via: 2001:4800:78ff:1b::1
            vlans:
                bond0.200:
                    dhcp4: true
                    id: 200
                    link: bond0
                eth0.101:
                    addresses:
                        - 192.168.0.2/24
                        - 192.168.2.10/24
                    id: 101
                    link: eth0
                    macaddress: aa:bb:cc:dd:ee:11
                    mtu: 1500
                    nameservers:
                        addresses:
                            - 192.168.0.10
                            - 10.23.23.134
                        search:
                            - barley.maas
                            - sacchromyces.maas
                            - brettanomyces.maas
                    routes:
                        - to: 0.0.0.0/0
                          via: 192.168.0.1
            """
        ),
    },
    "bond_v1": {
        "yaml": textwrap.dedent(
            """
            version: 1
            config:
              - type: physical
                name: bond0s0
                mac_address: aa:bb:cc:dd:e8:00
              - type: physical
                name: bond0s1
                mac_address: aa:bb:cc:dd:e8:01
              - type: bond
                name: bond0
                mac_address: aa:bb:cc:dd:e8:ff
                mtu: 9000
                bond_interfaces:
                  - bond0s0
                  - bond0s1
                params:
                  bond-mode: active-backup
                  bond_miimon: 100
                  bond-xmit-hash-policy: "layer3+4"
                  bond-num-grat-arp: 5
                  bond-downdelay: 10
                  bond-updelay: 20
                  bond-fail-over-mac: active
                  bond-primary: bond0s0
                  bond-primary-reselect: always
                subnets:
                  - type: static
                    address: 192.168.0.2/24
                    gateway: 192.168.0.1
                    routes:
                     - gateway: 192.168.0.3
                       netmask: 255.255.255.0
                       network: 10.1.3.0
                  - type: static
                    address: 192.168.1.2/24
                  - type: static
                    address: 2001:1::1/92
                    routes:
                        - gateway: 2001:67c:1562::1
                          network: "2001:67c::"
                          netmask: "ffff:ffff::"
                        - gateway: 3001:67c:15::1
                          network: "3001:67c::"
                          netmask: "ffff:ffff::"
                          metric: 10000
            """
        ),
        "expected_netplan": textwrap.dedent(
            """
         network:
             version: 2
             ethernets:
                 bond0s0:
                     match:
                         macaddress: aa:bb:cc:dd:e8:00
                     set-name: bond0s0
                 bond0s1:
                     match:
                         macaddress: aa:bb:cc:dd:e8:01
                     set-name: bond0s1
             bonds:
                 bond0:
                     addresses:
                     - 192.168.0.2/24
                     - 192.168.1.2/24
                     - 2001:1::1/92
                     interfaces:
                     - bond0s0
                     - bond0s1
                     macaddress: aa:bb:cc:dd:e8:ff
                     mtu: 9000
                     parameters:
                         down-delay: 10
                         fail-over-mac-policy: active
                         gratuitous-arp: 5
                         mii-monitor-interval: 100
                         mode: active-backup
                         primary: bond0s0
                         primary-reselect-policy: always
                         transmit-hash-policy: layer3+4
                         up-delay: 20
                     routes:
                     -   to: default
                         via: 192.168.0.1
                     -   to: 10.1.3.0/24
                         via: 192.168.0.3
                     -   to: 2001:67c::/32
                         via: 2001:67c:1562::1
                     -   metric: 10000
                         to: 3001:67c::/32
                         via: 3001:67c:15::1
        """
        ),
        "expected_eni": textwrap.dedent(
            """\
auto lo
iface lo inet loopback

auto bond0s0
iface bond0s0 inet manual
    bond-downdelay 10
    bond-fail-over-mac active
    bond-master bond0
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto bond0s1
iface bond0s1 inet manual
    bond-downdelay 10
    bond-fail-over-mac active
    bond-master bond0
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto bond0
iface bond0 inet static
    address 192.168.0.2/24
    gateway 192.168.0.1
    bond-downdelay 10
    bond-fail-over-mac active
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-slaves none
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    bond_miimon 100
    hwaddress aa:bb:cc:dd:e8:ff
    mtu 9000
    post-up route add -net 10.1.3.0/24 gw 192.168.0.3 || true
    pre-down route del -net 10.1.3.0/24 gw 192.168.0.3 || true

# control-alias bond0
iface bond0 inet static
    address 192.168.1.2/24

# control-alias bond0
iface bond0 inet6 static
    address 2001:1::1/92
    post-up route add -A inet6 2001:67c::/32 gw 2001:67c:1562::1 || true
    pre-down route del -A inet6 2001:67c::/32 gw 2001:67c:1562::1 || true
    post-up route add -A inet6 3001:67c::/32 gw 3001:67c:15::1 metric 10000 \
|| true
    pre-down route del -A inet6 3001:67c::/32 gw 3001:67c:15::1 metric 10000 \
|| true
        """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-bond0": textwrap.dedent(
                """\
        BONDING_MASTER=yes
        BONDING_MODULE_OPTS="mode=active-backup xmit_hash_policy=layer3+4 """
                """miimon=100 num_grat_arp=5 """
                """downdelay=10 updelay=20 """
                """fail_over_mac=active """
                """primary=bond0s0 """
                """primary_reselect=always"
        BONDING_SLAVE_0=bond0s0
        BONDING_SLAVE_1=bond0s1
        BOOTPROTO=static
        LLADDR=aa:bb:cc:dd:e8:ff
        IPADDR=192.168.0.2
        IPADDR1=192.168.1.2
        IPADDR6=2001:1::1/92
        MTU=9000
        NETMASK=255.255.255.0
        NETMASK1=255.255.255.0
        STARTMODE=auto
        """
            ),
            "ifcfg-bond0s0": textwrap.dedent(
                """\
        BOOTPROTO=none
        LLADDR=aa:bb:cc:dd:e8:00
        STARTMODE=hotplug
        """
            ),
            "ifcfg-bond0s1": textwrap.dedent(
                """\
        BOOTPROTO=none
        LLADDR=aa:bb:cc:dd:e8:01
        STARTMODE=hotplug
        """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-bond0": textwrap.dedent(
                """\
        BONDING_MASTER=yes
        BONDING_OPTS="mode=active-backup xmit_hash_policy=layer3+4 """
                """miimon=100 num_grat_arp=5 """
                """downdelay=10 updelay=20 """
                """fail_over_mac=active """
                """primary=bond0s0 """
                """primary_reselect=always"
        BONDING_SLAVE0=bond0s0
        BONDING_SLAVE1=bond0s1
        BOOTPROTO=none
        DEFROUTE=yes
        DEVICE=bond0
        GATEWAY=192.168.0.1
        MACADDR=aa:bb:cc:dd:e8:ff
        IPADDR=192.168.0.2
        IPADDR1=192.168.1.2
        IPV6ADDR=2001:1::1/92
        IPV6INIT=yes
        IPV6_AUTOCONF=no
        IPV6_FORCE_ACCEPT_RA=no
        MTU=9000
        NETMASK=255.255.255.0
        NETMASK1=255.255.255.0
        ONBOOT=yes
        TYPE=Bond
        USERCTL=no
        """
            ),
            "ifcfg-bond0s0": textwrap.dedent(
                """\
        BOOTPROTO=none
        DEVICE=bond0s0
        HWADDR=aa:bb:cc:dd:e8:00
        MASTER=bond0
        ONBOOT=yes
        SLAVE=yes
        TYPE=Ethernet
        USERCTL=no
        """
            ),
            "route6-bond0": textwrap.dedent(
                """\
        # Created by cloud-init automatically, do not edit.
        #
        2001:67c::/32 via 2001:67c:1562::1  dev bond0
        3001:67c::/32 via 3001:67c:15::1 metric 10000 dev bond0
            """
            ),
            "route-bond0": textwrap.dedent(
                """\
        ADDRESS0=10.1.3.0
        GATEWAY0=192.168.0.3
        NETMASK0=255.255.255.0
        """
            ),
            "ifcfg-bond0s1": textwrap.dedent(
                """\
        BOOTPROTO=none
        DEVICE=bond0s1
        HWADDR=aa:bb:cc:dd:e8:01
        MASTER=bond0
        ONBOOT=yes
        SLAVE=yes
        TYPE=Ethernet
        USERCTL=no
        """
            ),
        },
        "expected_network_manager": {
            "cloud-init-bond0s0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0s0
                uuid=09d0b5b9-67e7-5577-a1af-74d1cf17a71e
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:BB:CC:DD:E8:00

                """
            ),
            "cloud-init-bond0s1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0s1
                uuid=4d9aca96-b515-5630-ad83-d13daac7f9d0
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:BB:CC:DD:E8:01

                """
            ),
            "cloud-init-bond0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0
                uuid=54317911-f840-516b-a10d-82cb4c1f075c
                autoconnect-priority=120
                type=bond
                interface-name=bond0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bond]
                mode=active-backup
                miimon=100
                xmit_hash_policy=layer3+4
                num_grat_arp=5
                downdelay=10
                updelay=20
                fail_over_mac=active
                primary_reselect=always
                primary=bond0s0

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.0.2/24
                gateway=192.168.0.1
                route1=10.1.3.0/24,192.168.0.3
                address2=192.168.1.2/24

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::1/92
                route1=2001:67c::/32,2001:67c:1562::1
                route2=3001:67c::/32,3001:67c:15::1

                """
            ),
        },
    },
    "bond_v2": {
        "yaml": textwrap.dedent(
            """
            version: 2
            ethernets:
              bond0s0:
                match:
                    driver: "virtio_net"
                    macaddress: aa:bb:cc:dd:e8:00
                set-name: bond0s0
              bond0s1:
                set-name: bond0s1
                match:
                    driver: "e1000"
                    macaddress: aa:bb:cc:dd:e8:01
            bonds:
              bond0:
                addresses:
                - 192.168.0.2/24
                - 192.168.1.2/24
                - 2001:1::1/92
                interfaces:
                - bond0s0
                - bond0s1
                macaddress: aa:bb:cc:dd:e8:ff
                mtu: 9000
                parameters:
                    down-delay: 10
                    fail-over-mac-policy: active
                    gratuitous-arp: 5
                    mii-monitor-interval: 100
                    mode: active-backup
                    primary: bond0s0
                    primary-reselect-policy: always
                    transmit-hash-policy: layer3+4
                    up-delay: 20
                routes:
                -   to: 0.0.0.0/0
                    via: 192.168.0.1
                -   to: 10.1.3.0/24
                    via: 192.168.0.3
                -   to: 2001:67c::/32
                    via: 2001:67c:1562::1
                -   metric: 10000
                    to: 3001:67c::/32
                    via: 3001:67c:15::1
            """
        ),
        "expected_netplan": textwrap.dedent(
            """
         network:
             version: 2
             ethernets:
                 bond0s0:
                     match:
                         driver: virtio_net
                         macaddress: aa:bb:cc:dd:e8:00
                     set-name: bond0s0
                 bond0s1:
                     match:
                         driver: e1000
                         macaddress: aa:bb:cc:dd:e8:01
                     set-name: bond0s1
             bonds:
                 bond0:
                     addresses:
                     - 192.168.0.2/24
                     - 192.168.1.2/24
                     - 2001:1::1/92
                     interfaces:
                     - bond0s0
                     - bond0s1
                     macaddress: aa:bb:cc:dd:e8:ff
                     mtu: 9000
                     parameters:
                         down-delay: 10
                         fail-over-mac-policy: active
                         gratuitous-arp: 5
                         mii-monitor-interval: 100
                         mode: active-backup
                         primary: bond0s0
                         primary-reselect-policy: always
                         transmit-hash-policy: layer3+4
                         up-delay: 20
                     routes:
                     -   to: 0.0.0.0/0
                         via: 192.168.0.1
                     -   to: 10.1.3.0/24
                         via: 192.168.0.3
                     -   to: 2001:67c::/32
                         via: 2001:67c:1562::1
                     -   metric: 10000
                         to: 3001:67c::/32
                         via: 3001:67c:15::1
        """
        ),
        "expected_eni": textwrap.dedent(
            """\
auto lo
iface lo inet loopback

auto bond0s0
iface bond0s0 inet manual
    bond-downdelay 10
    bond-fail-over-mac active
    bond-master bond0
    bond_miimon 100
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-updelay 20
    bond-xmit-hash-policy layer3+4

auto bond0s1
iface bond0s1 inet manual
    bond-downdelay 10
    bond-fail-over-mac active
    bond-master bond0
    bond_miimon 100
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-updelay 20
    bond-xmit-hash-policy layer3+4

auto bond0
iface bond0 inet static
    address 192.168.0.2/24
    gateway 192.168.0.1
    bond-downdelay 10
    bond-fail-over-mac active
    bond_miimon 100
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-slaves none
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    hwaddress aa:bb:cc:dd:e8:ff
    mtu 9000
    post-up route add -net 10.1.3.0/24 gw 192.168.0.3 || true
    pre-down route del -net 10.1.3.0/24 gw 192.168.0.3 || true

# control-alias bond0
iface bond0 inet static
    address 192.168.1.2/24

# control-alias bond0
iface bond0 inet6 static
    address 2001:1::1/92
    post-up route add -A inet6 2001:67c::/32 gw 2001:67c:1562::1 || true
    pre-down route del -A inet6 2001:67c::/32 gw 2001:67c:1562::1 || true
    post-up route add -A inet6 3001:67c::/32 gw 3001:67c:15::1 metric 10000 \
|| true
    pre-down route del -A inet6 3001:67c::/32 gw 3001:67c:15::1 metric 10000 \
|| true
        """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-bond0": textwrap.dedent(
                """\
        BONDING_MASTER=yes
        BONDING_MODULE_OPTS="mode=active-backup xmit_hash_policy=layer3+4 """
                """miimon=100 num_grat_arp=5 """
                """downdelay=10 updelay=20 """
                """fail_over_mac=active """
                """primary=bond0s0 """
                """primary_reselect=always"
        BONDING_SLAVE_0=bond0s0
        BONDING_SLAVE_1=bond0s1
        BOOTPROTO=static
        LLADDR=aa:bb:cc:dd:e8:ff
        IPADDR=192.168.0.2
        IPADDR1=192.168.1.2
        IPADDR6=2001:1::1/92
        MTU=9000
        NETMASK=255.255.255.0
        NETMASK1=255.255.255.0
        STARTMODE=auto
        """
            ),
            "ifcfg-bond0s0": textwrap.dedent(
                """\
        BOOTPROTO=none
        LLADDR=aa:bb:cc:dd:e8:00
        STARTMODE=hotplug
        """
            ),
            "ifcfg-bond0s1": textwrap.dedent(
                """\
        BOOTPROTO=none
        LLADDR=aa:bb:cc:dd:e8:01
        STARTMODE=hotplug
        """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-bond0": textwrap.dedent(
                """\
        BONDING_MASTER=yes
        BONDING_OPTS="mode=active-backup xmit_hash_policy=layer3+4 """
                """miimon=100 num_grat_arp=5 """
                """downdelay=10 updelay=20 """
                """fail_over_mac=active """
                """primary=bond0s0 """
                """primary_reselect=always"
        BONDING_SLAVE0=bond0s0
        BONDING_SLAVE1=bond0s1
        BOOTPROTO=none
        DEFROUTE=yes
        DEVICE=bond0
        GATEWAY=192.168.0.1
        MACADDR=aa:bb:cc:dd:e8:ff
        IPADDR=192.168.0.2
        IPADDR1=192.168.1.2
        IPV6ADDR=2001:1::1/92
        IPV6INIT=yes
        IPV6_AUTOCONF=no
        IPV6_FORCE_ACCEPT_RA=no
        MTU=9000
        NETMASK=255.255.255.0
        NETMASK1=255.255.255.0
        ONBOOT=yes
        TYPE=Bond
        USERCTL=no
        """
            ),
            "ifcfg-bond0s0": textwrap.dedent(
                """\
        BOOTPROTO=none
        DEVICE=bond0s0
        HWADDR=aa:bb:cc:dd:e8:00
        MASTER=bond0
        ONBOOT=yes
        SLAVE=yes
        TYPE=Ethernet
        USERCTL=no
        """
            ),
            "route6-bond0": textwrap.dedent(
                """\
        # Created by cloud-init automatically, do not edit.
        #
        2001:67c::/32 via 2001:67c:1562::1  dev bond0
        3001:67c::/32 via 3001:67c:15::1 metric 10000 dev bond0
            """
            ),
            "route-bond0": textwrap.dedent(
                """\
        ADDRESS0=10.1.3.0
        GATEWAY0=192.168.0.3
        NETMASK0=255.255.255.0
        """
            ),
            "ifcfg-bond0s1": textwrap.dedent(
                """\
        BOOTPROTO=none
        DEVICE=bond0s1
        HWADDR=aa:bb:cc:dd:e8:01
        MASTER=bond0
        ONBOOT=yes
        SLAVE=yes
        TYPE=Ethernet
        USERCTL=no
        """
            ),
        },
        "expected_network_manager": {
            "cloud-init-bond0s0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0s0
                uuid=09d0b5b9-67e7-5577-a1af-74d1cf17a71e
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:BB:CC:DD:E8:00

                """
            ),
            "cloud-init-bond0s1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0s1
                uuid=4d9aca96-b515-5630-ad83-d13daac7f9d0
                autoconnect-priority=120
                type=ethernet
                slave-type=bond
                master=54317911-f840-516b-a10d-82cb4c1f075c

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:BB:CC:DD:E8:01

                """
            ),
            "cloud-init-bond0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init bond0
                uuid=54317911-f840-516b-a10d-82cb4c1f075c
                autoconnect-priority=120
                type=bond
                interface-name=bond0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bond]
                mode=active-backup
                miimon=100
                xmit_hash_policy=layer3+4
                num_grat_arp=5
                downdelay=10
                updelay=20
                fail_over_mac=active
                primary_reselect=always
                primary=bond0s0

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.0.2/24
                route1=0.0.0.0/0,192.168.0.1
                route2=10.1.3.0/24,192.168.0.3
                address2=192.168.1.2/24

                [ipv6]
                route1=2001:67c::/32,2001:67c:1562::1
                route2=3001:67c::/32,3001:67c:15::1
                method=manual
                may-fail=false
                address1=2001:1::1/92

                """
            ),
        },
    },
    "vlan_v1": {
        "yaml": textwrap.dedent(
            """
            version: 1
            config:
              - type: physical
                name: en0
                mac_address: aa:bb:cc:dd:e8:00
              - type: vlan
                mtu: 2222
                name: en0.99
                vlan_link: en0
                vlan_id: 99
                subnets:
                  - type: static
                    address: '192.168.2.2/24'
                  - type: static
                    address: '192.168.1.2/24'
                    gateway: 192.168.1.1
                  - type: static
                    address: 2001:1::bbbb/96
                    routes:
                     - gateway: 2001:1::1
                       netmask: '::'
                       network: '::'
            """
        ),
        "expected_sysconfig_opensuse": {
            # TODO RJS: unknown proper BOOTPROTO setting ask Marius
            "ifcfg-en0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=aa:bb:cc:dd:e8:00
                STARTMODE=auto"""
            ),
            "ifcfg-en0.99": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.2.2
                IPADDR1=192.168.1.2
                IPADDR6=2001:1::bbbb/96
                MTU=2222
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                STARTMODE=auto
                ETHERDEVICE=en0
                VLAN_ID=99
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-en0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=en0
                HWADDR=aa:bb:cc:dd:e8:00
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-en0.99": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=en0.99
                GATEWAY=192.168.1.1
                IPADDR=192.168.2.2
                IPADDR1=192.168.1.2
                IPV6ADDR=2001:1::bbbb/96
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                IPV6_DEFAULTGW=2001:1::1
                MTU=2222
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ONBOOT=yes
                PHYSDEV=en0
                USERCTL=no
                VLAN=yes"""
            ),
        },
        "expected_network_manager": {
            "cloud-init-en0.99.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init en0.99
                uuid=f594e2ed-f107-51df-b225-1dc530a5356b
                autoconnect-priority=120
                type=vlan
                interface-name=en0.99

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [vlan]
                id=99
                parent=e0ca478b-8d84-52ab-8fae-628482c629b5

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.2.2/24
                address2=192.168.1.2/24
                gateway=192.168.1.1

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::bbbb/96
                route1=::/0,2001:1::1

                """
            ),
            "cloud-init-en0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init en0
                uuid=e0ca478b-8d84-52ab-8fae-628482c629b5
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:BB:CC:DD:E8:00

                """
            ),
        },
    },
    "vlan_v2": {
        "yaml": textwrap.dedent(
            """
            version: 2
            ethernets:
                en0:
                    match:
                        macaddress: aa:bb:cc:dd:e8:00
                    set-name: en0
            vlans:
                en0.99:
                    addresses:
                    - 192.168.2.2/24
                    - 192.168.1.2/24
                    - 2001:1::bbbb/96
                    id: 99
                    link: en0
                    mtu: 2222
                    routes:
                    -   to: 0.0.0.0/0
                        via: 192.168.1.1
                    -   to: ::/0
                        via: 2001:1::1

            """
        ),
        "expected_sysconfig_opensuse": {
            # TODO RJS: unknown proper BOOTPROTO setting ask Marius
            "ifcfg-en0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=aa:bb:cc:dd:e8:00
                STARTMODE=auto"""
            ),
            "ifcfg-en0.99": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.2.2
                IPADDR1=192.168.1.2
                IPADDR6=2001:1::bbbb/96
                MTU=2222
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                STARTMODE=auto
                ETHERDEVICE=en0
                VLAN_ID=99
            """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-en0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=en0
                HWADDR=aa:bb:cc:dd:e8:00
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
            "ifcfg-en0.99": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=en0.99
                GATEWAY=192.168.1.1
                IPADDR=192.168.2.2
                IPADDR1=192.168.1.2
                IPV6ADDR=2001:1::bbbb/96
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                IPV6_DEFAULTGW=2001:1::1
                MTU=2222
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ONBOOT=yes
                PHYSDEV=en0
                USERCTL=no
                VLAN=yes"""
            ),
        },
        "expected_network_manager": {
            "cloud-init-en0.99.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init en0.99
                uuid=f594e2ed-f107-51df-b225-1dc530a5356b
                autoconnect-priority=120
                type=vlan
                interface-name=en0.99

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [vlan]
                id=99
                parent=e0ca478b-8d84-52ab-8fae-628482c629b5

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.2.2/24
                route1=0.0.0.0/0,192.168.1.1
                address2=192.168.1.2/24

                [ipv6]
                route1=::/0,2001:1::1
                method=manual
                may-fail=false
                address1=2001:1::bbbb/96

                """
            ),
            "cloud-init-en0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init en0
                uuid=e0ca478b-8d84-52ab-8fae-628482c629b5
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=AA:BB:CC:DD:E8:00

                """
            ),
        },
    },
    "bridge": {
        "yaml_v1": textwrap.dedent(
            """
            version: 1
            config:
              - type: physical
                name: eth0
                mac_address: '52:54:00:12:34:00'
                subnets:
                  - type: static
                    address: 2001:1::100/96
              - type: physical
                name: eth1
                mac_address: '52:54:00:12:34:01'
                subnets:
                  - type: static
                    address: 2001:1::101/96
              - type: bridge
                name: br0
                bridge_interfaces:
                  - eth0
                  - eth1
                params:
                  bridge_stp: 0
                  bridge_bridgeprio: 22
                subnets:
                  - type: static
                    address: 192.168.2.2/24"""
        ),
        "yaml_v2": textwrap.dedent(
            """
            version: 2
            ethernets:
                eth0:
                    addresses:
                    - 2001:1::100/96
                    match:
                        macaddress: '52:54:00:12:34:00'
                    set-name: eth0
                eth1:
                    addresses:
                    - 2001:1::101/96
                    match:
                        macaddress: '52:54:00:12:34:01'
                    set-name: eth1
            bridges:
                br0:
                    addresses:
                    - 192.168.2.2/24
                    interfaces:
                    - eth0
                    - eth1
                    parameters:
                        priority: 22
                        stp: false
            """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-br0": textwrap.dedent(
                """\
                BOOTPROTO=static
                IPADDR=192.168.2.2
                NETMASK=255.255.255.0
                STARTMODE=auto
                BRIDGE_STP=off
                BRIDGE_PRIORITY=22
                BRIDGE_PORTS='eth0 eth1'
                """
            ),
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=52:54:00:12:34:00
                IPADDR6=2001:1::100/96
                STARTMODE=auto
                """
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=52:54:00:12:34:01
                IPADDR6=2001:1::101/96
                STARTMODE=auto
                """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-br0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=br0
                IPADDR=192.168.2.2
                NETMASK=255.255.255.0
                ONBOOT=yes
                PRIO=22
                STP=no
                TYPE=Bridge
                USERCTL=no
                """
            ),
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth0
                HWADDR=52:54:00:12:34:00
                IPV6ADDR=2001:1::100/96
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth1
                HWADDR=52:54:00:12:34:01
                IPV6ADDR=2001:1::101/96
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
        },
        "expected_network_manager": {
            "cloud-init-br0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init br0
                uuid=dee46ce4-af7a-5e7c-aa08-b25533ae9213
                autoconnect-priority=120
                type=bridge
                interface-name=br0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [bridge]
                stp=false
                priority=22

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.2.2/24

                """
            ),
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                slave-type=bridge
                master=dee46ce4-af7a-5e7c-aa08-b25533ae9213

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=52:54:00:12:34:00

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::100/96

                """
            ),
            "cloud-init-eth1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1
                uuid=3c50eb47-7260-5a6d-801d-bd4f587d6b58
                autoconnect-priority=120
                type=ethernet
                slave-type=bridge
                master=dee46ce4-af7a-5e7c-aa08-b25533ae9213

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=52:54:00:12:34:01

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:1::101/96

                """
            ),
        },
    },
    "manual": {
        "yaml": textwrap.dedent(
            """
            version: 1
            config:
              - type: physical
                name: eth0
                mac_address: '52:54:00:12:34:00'
                subnets:
                  - type: static
                    address: 192.168.1.2/24
                    control: manual
              - type: physical
                name: eth1
                mtu: 1480
                mac_address: 52:54:00:12:34:aa
                subnets:
                  - type: manual
              - type: physical
                name: eth2
                mac_address: 52:54:00:12:34:ff
                subnets:
                  - type: manual
                    control: manual
                  """
        ),
        "expected_eni": textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            # control-manual eth0
            iface eth0 inet static
                address 192.168.1.2/24

            auto eth1
            iface eth1 inet manual
                mtu 1480

            # control-manual eth2
            iface eth2 inet manual
            """
        ),
        "expected_netplan": textwrap.dedent(
            """\

            network:
                version: 2
                ethernets:
                    eth0:
                        addresses:
                        - 192.168.1.2/24
                        match:
                            macaddress: '52:54:00:12:34:00'
                        set-name: eth0
                    eth1:
                        match:
                            macaddress: 52:54:00:12:34:aa
                        mtu: 1480
                        set-name: eth1
                    eth2:
                        match:
                            macaddress: 52:54:00:12:34:ff
                        set-name: eth2
            """
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=52:54:00:12:34:00
                IPADDR=192.168.1.2
                NETMASK=255.255.255.0
                STARTMODE=manual
                """
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=52:54:00:12:34:aa
                MTU=1480
                STARTMODE=auto
                """
            ),
            "ifcfg-eth2": textwrap.dedent(
                """\
                BOOTPROTO=static
                LLADDR=52:54:00:12:34:ff
                STARTMODE=manual
                """
            ),
        },
        "expected_sysconfig_rhel": {
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=52:54:00:12:34:00
                IPADDR=192.168.1.2
                NETMASK=255.255.255.0
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            "ifcfg-eth1": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=52:54:00:12:34:aa
                MTU=1480
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            "ifcfg-eth2": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth2
                HWADDR=52:54:00:12:34:ff
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no
                """
            ),
        },
        "expected_network_manager": {
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=52:54:00:12:34:00

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.1.2/24

                """
            ),
            "cloud-init-eth1.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1
                uuid=3c50eb47-7260-5a6d-801d-bd4f587d6b58
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mtu=1480
                mac-address=52:54:00:12:34:AA

                [ipv4]
                method=auto
                may-fail=true

                """
            ),
            "cloud-init-eth2.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth2
                uuid=5559a242-3421-5fdd-896e-9cb8313d5804
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=52:54:00:12:34:FF

                [ipv4]
                method=auto
                may-fail=true

                """
            ),
        },
    },
    "v1-dns": {
        "expected_networkd": textwrap.dedent(
            """\
            [Address]
            Address=192.168.1.20/16

            [Match]
            MACAddress=11:22:33:44:55:66
            Name=interface0

            [Network]
            DHCP=no
            DNS=1.1.1.1 3.3.3.3
            Domains=aaaa cccc

            [Route]
            Gateway=192.168.1.1
        """
        ),
        "expected_eni": textwrap.dedent(
            """\
            # This file is generated from information provided by the datasource.  Changes
            # to it will not persist across an instance reboot.  To disable cloud-init's
            # network configuration capabilities, write a file
            # /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
            # network: {config: disabled}
            auto lo
            iface lo inet loopback
                dns-nameservers 2.2.2.2
                dns-search bbbb

            iface lo inet6 loopback
                dns-nameservers FEDC::1
                dns-search bbbb

            auto interface0
            iface interface0 inet static
                address 192.168.1.20/16
                dns-nameservers 1.1.1.1 3.3.3.3
                dns-search aaaa cccc
                gateway 192.168.1.1
        """  # noqa: E501
        ),
        "expected_netplan": textwrap.dedent(
            """\
            # This file is generated from information provided by the datasource.  Changes
            # to it will not persist across an instance reboot.  To disable cloud-init's
            # network configuration capabilities, write a file
            # /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
            # network: {config: disabled}
            network:
                version: 2
                ethernets:
                    interface0:
                        addresses:
                        - 192.168.1.20/16
                        match:
                            macaddress: 11:22:33:44:55:66
                        nameservers:
                            addresses:
                            - 1.1.1.1
                            - 3.3.3.3
                            search:
                            - aaaa
                            - cccc
                        routes:
                        -   to: default
                            via: 192.168.1.1
                        set-name: interface0
        """  # noqa: E501
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-interface0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                BOOTPROTO=static
                IPADDR=192.168.1.20
                LLADDR=11:22:33:44:55:66
                NETMASK=255.255.0.0
                STARTMODE=auto
            """
            )
        },
        "expected_sysconfig_rhel": {
            "ifcfg-eth0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=interface0
                DNS1=1.1.1.1
                DNS2=3.3.3.3
                DOMAIN=aaaa cccc
                GATEWAY=192.168.1.1
                HWADDR=11:22:33:44:55:66
                IPADDR=192.168.1.20
                NETMASK=255.255.0.0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            ),
        },
        "expected_network_manager": {
            "cloud-init-interface0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init interface0
                uuid=8b6862ed-dbd6-5830-93f7-a91451c13828
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=11:22:33:44:55:66

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.1.20/16
                gateway=192.168.1.1
                dns=3.3.3.3;1.1.1.1;
                dns-search=cccc;aaaa;

            """
            )
        },
        "yaml": textwrap.dedent(
            """\
            version: 1
            config:
            - type: physical
              name: interface0
              mac_address: "11:22:33:44:55:66"
              subnets:
              - type: static
                address: 192.168.1.20/16
                gateway: 192.168.1.1
                dns_nameservers:
                - 3.3.3.3
                dns_search:
                - cccc
            - type: nameserver
              interface: interface0
              address:
              - 1.1.1.1
              search:
              - aaaa
            - type: nameserver
              address:
              - 2.2.2.2
              - FEDC::1
              search:
              - bbbb
        """
        ),
    },
    "v2-dev-name-via-mac-lookup": {
        "expected_sysconfig_rhel": {
            "ifcfg-eth0": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=cf:d6:af:48:e8:80
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""
            ),
        },
        "yaml": textwrap.dedent(
            """\
            version: 2
            ethernets:
              nic0:
                match:
                  macaddress: 'cf:d6:af:48:e8:80'
            """
        ),
    },
    "v2-mixed-routes": {
        "expected_network_manager": {
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                interface-name=eth0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mtu=500

                [ipv4]
                method=auto
                may-fail=true
                route1=169.254.42.42/32,62.210.0.1
                route1_options=mtu=400
                route2=169.254.42.43/32,62.210.0.2
                route2_options=mtu=200
                address1=192.168.1.20/16
                dns=8.8.8.8;
                dns-search=lab;home;

                [ipv6]
                route1=::/0,fe80::dc00:ff:fe20:186
                route1_options=mtu=300
                route2=fe80::dc00:ff:fe20:188/64,fe80::dc00:ff:fe20:187
                route2_options=mtu=100
                method=auto
                may-fail=true
                address1=2001:bc8:1210:232:dc00:ff:fe20:185/64
                dns=FEDC::1;
                dns-search=lab;home;

            """
            )
        },
        "yaml": textwrap.dedent(
            """\
            version: 2
            ethernets:
              eth0:
                dhcp4: true
                dhcp6: true
                mtu: 500
                nameservers:
                  search: [lab, home]
                  addresses: [8.8.8.8, "FEDC::1"]
                routes:
                  - to: 169.254.42.42/32
                    via: 62.210.0.1
                    mtu: 400
                  - via: fe80::dc00:ff:fe20:186
                    to: ::/0
                    mtu: 300
                  - to: 169.254.42.43/32
                    via: 62.210.0.2
                    mtu: 200
                  - via: fe80::dc00:ff:fe20:187
                    to: fe80::dc00:ff:fe20:188
                    mtu: 100
                addresses:
                  - 192.168.1.20/16
                  - 2001:bc8:1210:232:dc00:ff:fe20:185/64
        """
        ),
    },
    "v2-dns": {
        "expected_networkd": textwrap.dedent(
            """\
            [Address]
            Address=192.168.1.20/16

            [Address]
            Address=2001:bc8:1210:232:dc00:ff:fe20:185/64

            [Match]
            Name=eth0

            [Network]
            DHCP=no
            DNS=8.8.8.8 FEDC::1
            Domains=lab home
        """
        ),
        "expected_eni": textwrap.dedent(
            """\
            # This file is generated from information provided by the datasource.  Changes
            # to it will not persist across an instance reboot.  To disable cloud-init's
            # network configuration capabilities, write a file
            # /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
            # network: {config: disabled}
            auto lo
            iface lo inet loopback

            auto eth0
            iface eth0 inet static
                address 192.168.1.20/16
                dns-nameservers 8.8.8.8
                dns-search lab home

            # control-alias eth0
            iface eth0 inet6 static
                address 2001:bc8:1210:232:dc00:ff:fe20:185/64
                dns-nameservers FEDC::1
                dns-search lab home
        """  # noqa: E501
        ),
        "expected_sysconfig_opensuse": {
            "ifcfg-eth0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                BOOTPROTO=static
                IPADDR=192.168.1.20
                IPADDR6=2001:bc8:1210:232:dc00:ff:fe20:185/64
                NETMASK=255.255.0.0
                STARTMODE=auto
            """
            )
        },
        "expected_sysconfig_rhel": {
            "ifcfg-eth0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                BOOTPROTO=none
                DEVICE=eth0
                DNS1=8.8.8.8
                DNS2=FEDC::1
                DOMAIN="lab home"
                IPADDR=192.168.1.20
                IPV6ADDR=2001:bc8:1210:232:dc00:ff:fe20:185/64
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_FORCE_ACCEPT_RA=no
                NETMASK=255.255.0.0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """
            )
        },
        "expected_network_manager": {
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                interface-name=eth0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv4]
                method=manual
                may-fail=false
                address1=192.168.1.20/16
                dns=8.8.8.8;
                dns-search=lab;home;

                [ipv6]
                method=manual
                may-fail=false
                address1=2001:bc8:1210:232:dc00:ff:fe20:185/64
                dns=FEDC::1;
                dns-search=lab;home;

            """
            )
        },
        "yaml": textwrap.dedent(
            """\
            version: 2
            ethernets:
              eth0:
                nameservers:
                  search: [lab, home]
                  addresses: [8.8.8.8, "FEDC::1"]
                addresses:
                - 192.168.1.20/16
                - 2001:bc8:1210:232:dc00:ff:fe20:185/64
        """
        ),
    },
    "v2-dns-no-if-ips": {
        "expected_network_manager": {
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                interface-name=eth0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv4]
                method=auto
                may-fail=true
                dns=8.8.8.8;
                dns-search=lab;home;

                [ipv6]
                method=auto
                may-fail=true
                dns=FEDC::1;
                dns-search=lab;home;

            """
            )
        },
        "yaml": textwrap.dedent(
            """\
            version: 2
            ethernets:
              eth0:
                dhcp4: true
                dhcp6: true
                nameservers:
                  search: [lab, home]
                  addresses: [8.8.8.8, "FEDC::1"]
        """
        ),
    },
    "v2-dns-no-dhcp": {
        "expected_network_manager": {
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                interface-name=eth0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

            """
            )
        },
        "yaml": textwrap.dedent(
            """\
            version: 2
            ethernets:
              eth0:
                nameservers:
                  search: [lab, home]
                  addresses: [8.8.8.8, "FEDC::1"]
        """
        ),
    },
    "v2-route-no-gateway": {
        "expected_network_manager": {
            "cloud-init-eth0.nmconnection": textwrap.dedent(
                """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                interface-name=eth0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv4]
                method=auto
                may-fail=false
                route1=0.0.0.0/0

                """
            )
        },
        "yaml": textwrap.dedent(
            """\
            version: 2
            ethernets:
              eth0:
                dhcp4: true
                routes:
                - to: "0.0.0.0/0"
            """
        ),
    },
}
