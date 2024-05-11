.. _cce-landscape:

Install Landscape client
************************

These examples will install and configure the Landscape client.

For a full list of keys, refer to the `landscape module`_ schema.

Example 1
=========

.. code-block:: yaml

    #cloud-config
    landscape:
        client:
            url: "https://landscape.canonical.com/message-system"
            ping_url: "http://landscape.canonical.com/ping"
            data_path: "/var/lib/landscape/client"
            http_proxy: "http://my.proxy.com/foobar"
            https_proxy: "https://my.proxy.com/foobar"
            tags: "server,cloud"
            computer_title: "footitle"
            registration_key: "fookey"
            account_name: "fooaccount"

Minimum viable config
=====================

The minimum viable Landscape config requires ``account_name`` and
``computer_title``.

.. code-block:: yaml

    #cloud-config
    landscape:
        client:
            computer_title: kiosk 1
            account_name: Joe's Biz

Install from a PPA
==================

To install ``landscape-client`` from a PPA, specify ``apt.sources``.

.. code-block:: yaml

    #cloud-config
    apt:
        sources:
          trunk-testing-ppa:
            source: ppa:landscape/self-hosted-beta
    landscape:
        client:
          account_name: myaccount
          computer_title: himom

.. _landscape module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#landscape
