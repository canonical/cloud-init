.. _cce-apt:

Configure APT
*************

For a full list of keys, refer to the
:ref:`APT configure module <mod_cc_apt_configure>` schema.

Example 1
=========

Cloud-init version 23.4 will generate a ``deb822``-formatted ``sources`` file
at ``/etc/apt/sources.list.d/<distro>.sources`` instead of
``/etc/apt/sources.list`` when ``sources_list`` content is in ``deb822``
format.

.. literalinclude:: ../../../module-docs/cc_apt_configure/example2.yaml
   :language: yaml
   :linenos:

Example 2
=========

.. literalinclude:: ../../../module-docs/cc_apt_configure/example1.yaml
   :language: yaml
   :linenos:

Update APT on first boot
========================

This example will update the ``apt`` repository on first boot; it runs the
``apt-get update`` command.


The default is ``false``. However, if packages are given, or if
``package_upgrade`` is set to ``true``, then the update will be done
irrespective of this setting.

.. code-block:: yaml

    #cloud-config
    package_update: true

Specify mirrors
===============

* Default: auto select based on cloud metadata in EC2, the default is
  ``<region>.archive.ubuntu.com``.

One can either specify a URI to use as a mirror with the ``uri`` key, or a list
of URLs using the ``search`` key, which will have cloud-init search the list
for the first mirror available. This option is limited in that it only verifies
that the mirror is DNS-resolvable (or an IP address).

If neither mirror is set (the default), then use the mirror provided by the
DataSource. In EC2, that means using ``<region>.ec2.archive.ubuntu.com``.

If no mirror is provided by the DataSource, but ``search_dns`` is true, then
search for DNS names ``<distro>-mirror`` in each of:
- FQDN of this host per cloud metadata
- localdomain
- no domain (which would search domains listed in ``/etc/resolv.conf``)

If there is a DNS entry for ``<distro>-mirror``, then it is assumed that there
is a distro mirror at ``http://<distro>-mirror.<domain>/<distro>``. That gives
the cloud provider the opportunity to set up mirrors of a distro and expose
them only by creating DNS entries.

If none of that is found, then the default distro mirror is used.

.. code-block:: yaml

    #cloud-config
    apt:
      primary:
        - arches: [default]
          uri: http://us.archive.ubuntu.com/ubuntu/
    # or
    apt:
      primary:
        - arches: [default]
          search:
            - http://local-mirror.mydomain
            - http://archive.ubuntu.com
    # or
    apt:
      primary:
        - arches: [default]
          search_dns: True

Explanation of APT config
=========================

The APT config consists of two major "areas":

* Global configuration for the APT feature
* The source dictionary, which defines various entries to be considered by APT

Global APT configuration
========================

``preserve_sources_list``
-------------------------

Preserves the existing ``/etc/apt/sources.list``.

Default: ``false`` - do overwrite ``sources_list``. If set to ``true`` then
any "mirrors" configuration will have no effect.

Set to ``true`` to avoid affecting ``sources.list``. In that case only "extra"
source specifications will be written into ``/etc/apt/sources.list.d/*``

``disable_suites``
------------------

This is an empty list by default, so nothing is disabled.

If given, those suites are removed from ``sources.list`` after all other
modifications have been made.

Suites are even disabled if no other modification was made, but not if
``preserve_sources_list`` is active.

There is a special alias ``$RELEASE`` as in the sources that will be replaced
by the matching release.

To ease configuration and improve readability the following common Ubuntu
suites will be automatically mapped to their full definition:

- ``updates``   => ``$RELEASE-updates``
- ``backports`` => ``$RELEASE-backports``
- ``security``  => ``$RELEASE-security``
- ``proposed``  => ``$RELEASE-proposed``
- ``release``   => ``$RELEASE``

There is no harm in specifying a suite to be disabled that is not found in the
``sources.list`` file (just a no-op then).

.. note::
   Lines don't get deleted, but rather disabled by being converted to a
   comment. The example below disables all the usual defaults except
   ``$RELEASE-security``. It also disables a custom suite called "mysuite".

``primary``/``security`` archives
---------------------------------

Default: none - instead it is auto select based on cloud metadata so if
none of ``uri``, ``search``, or ``search_dns`` are set (the default) then use
the mirror provided by the DataSource found. In EC2, that means using
``<region>.ec2.archive.ubuntu.com``.

``security`` is optional, if not defined it is set to the same value as
primary.

Define a custom (e.g. localized) mirror that will be used in ``sources.list``
and any custom sources entries for ``deb`` / ``deb-src`` lines.

One can set primary and security mirror to different URIs. The child
elements to the keys primary and secondary are equivalent.

* ``arches`` is list of architectures the config applies to. The special
  keyword "default" applies to any architecture not explicitly listed. In the
  example below, ``arches`` is set twice, which allows one to have separate
  configs for different per-arch mirrors

* ``uri`` is just defining the target as-is
* ``search`` via search one can define lists that are tried one by one. The
  first with a working DNS resolution (or if it is an IP) will be picked.
  That way one can keep one configuration for multiple sub-environments that
  select the working one.
* ``search_dns`` If no mirror is provided by URI or search but 'search_dns'
  is true, then search for DNS names ``'<distro>-mirror'`` in each of:

  - FQDN of this host per cloud metadata
  - ``localdomain``
  - no domain (which would search domains listed in ``/etc/resolv.conf``)

If there is a DNS entry for ``<distro>-mirror``, then it is assumed that
there is a distro mirror at ``http://<distro>-mirror.<domain>/<distro>``.
That gives the cloud provider the opportunity to set mirrors of a distro up
and expose them only by creating DNS entries.

If none of that is found, then the default distro mirror is used.

If multiple of a category are given:

1. ``uri``
2. ``search``
3. ``search_dns``

The first defining a valid mirror wins (in the order as defined here, not
the order as listed in the config).

Additionally, if the repository requires a custom signing key, it can be
specified via the same fields as for custom sources:

* ``keyid``: providing a key to import via shortid or fingerprint
* ``key``: providing a raw PGP key
* ``keyserver``: specify an alternate keyserver to pull keys from that were
  specified by keyid

If ``search_dns`` is set for security the searched pattern is:
``<distro>-security-mirror``.

If no mirrors are specified at all (or all lookups fail), it will try to get
them from the cloud datasource. If neither of those provide one, it will fall
back to:

- ``primary: http://archive.ubuntu.com/ubuntu``
- ``security: http://security.ubuntu.com/ubuntu``

``sources_list``
----------------

Provides a custom template for rendering ``sources.list``. Without one
provided, cloud-init uses built-in templates for Ubuntu and Debian.

Within these ``sources.list`` templates you can use the following replacement
variables (all have sensible Ubuntu defaults, but mirrors can be overwritten
as needed (see above)):

- ``$RELEASE``
- ``$MIRROR``
- ``$PRIMARY``
- ``$SECURITY``

``conf``
--------

Specifies any APT config string that will be made available to APT. Seee the
``APT.CONF(5)`` manpage for details of what can be specified.

``(http_|ftp_|https_)proxy``
----------------------------

Proxies are the most common ``apt.conf`` option, so for simplified use
there is a shortcut for those. They get automatically translated into the
correct ``Acquire::*::Proxy`` statements.

.. note::
   ``proxy`` is a short synonym to ``http_proxy``.

Source list dictionary
======================

This is a dictionary (unlike most block/net which are lists).

The key of each source entry is the filename, which is prepended by
``/etc/apt/sources.list.d/`` if it doesn't start with a ``'/'``.

If it doesn't end with ``.list`` it will be appended so that APT picks up its
configuration.

Whenever there is no content to be written into such a file, the key is
not used as filename -- yet it can still be used as index for merging
configuration.

The values inside the entries consist of the following optional entries:

- ``source``: A ``sources.list`` entry (some variable replacements apply)
- ``keyid``: Providing a key to import via short ID or fingerprint
- ``key``: Providing a raw PGP key
- ``keyserver``: Specify an alternate keyserver to pull the keys from that
  were specified by ``keyid``

This allows merging between multiple input files given a list like:

.. code-block:: yaml

   cloud-config1
   sources:
     s1: {'key': 'key1', 'source': 'source1'}
   cloud-config2
   sources:
     s2: {'key': 'key2'}
     s1: {'keyserver': 'foo'}

This would be merged to:

.. code-block:: yaml

   sources:
     s1:
       keyserver: foo
       key: key1
       source: source1
     s2:
       key: key2

Sources example
---------------

.. code-block:: yaml

    #cloud-config
    apt_pipelining: False
    packages: ['pastebinit']
    apt:
      preserve_sources_list: true
      disable_suites: [$RELEASE-updates, backports, $RELEASE, mysuite]
      primary:
        - arches: [amd64, i386, default]
          uri: http://us.archive.ubuntu.com/ubuntu
          search:
            - http://cool.but-sometimes-unreachable.com/ubuntu
            - http://us.archive.ubuntu.com/ubuntu
          search_dns: true
        - arches: [s390x, arm64]
      security:
        - uri: http://security.ubuntu.com/ubuntu
          arches: [default]
      sources_list: | # written by cloud-init custom template
        deb $MIRROR $RELEASE main restricted
        deb-src $MIRROR $RELEASE main restricted
        deb $PRIMARY $RELEASE universe restricted
        deb $SECURITY $RELEASE-security multiverse
      conf: | # APT config
        APT {
          Get {
            Assume-Yes "true";
            Fix-Broken "true";
          };
        };

      proxy: http://[[user][:pass]@]host[:port]/
      http_proxy: http://[[user][:pass]@]host[:port]/
      ftp_proxy: ftp://[[user][:pass]@]host[:port]/
      https_proxy: https://[[user][:pass]@]host[:port]/
      add_apt_repo_match: '^[\w-]+:\w'
      sources:
        curtin-dev-ppa.list:
          source: "deb http://ppa.launchpad.net/curtin-dev/test-archive/ubuntu bionic main"
          keyid: F430BBA5 # GPG key ID published on a key server
        ignored1:
          source: "ppa:curtin-dev/test-archive"    # Quote the string
        my-repo2.list:
          source: deb [signed-by=$KEY_FILE] $MIRROR $RELEASE multiverse
          keyid: F430BBA5
        my-repo3.list:
          source: "deb http://ppa.launchpad.net/curtin-dev/test-archive/ubuntu bionic main"
          keyid: F430BBA5 # GPG key ID published on the key server
          filename: curtin-dev-ppa.list
        ignored2:
          keyid: F430BBA5 # GPG key ID published on a key server
        ignored3:
          keyid: B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77
        ignored4:
          keyid: B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77
          keyserver: pgp.mit.edu
        ignored5:
          source: deb [signed-by=$KEY_FILE] $MIRROR $RELEASE multiverse
          keyid: B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77
        my-repo4.list:
          key: |
            -----BEGIN PGP PUBLIC KEY BLOCK-----
            Version: SKS 1.0.10
            mI0ESpA3UQEEALdZKVIMq0j6qWAXAyxSlF63SvPVIgxHPb9Nk0DZUixn+akqytxG4zKCONz6
            qLjoBBfHnynyVLfT4ihg9an1PqxRnTO+JKQxl8NgKGz6Pon569GtAOdWNKw15XKinJTDLjnj
            9y96ljJqRcpV9t/WsIcdJPcKFR5voHTEoABE2aEXABEBAAG0GUxhdW5jaHBhZCBQUEEgZm9y
            IEFsZXN0aWOItgQTAQIAIAUCSpA3UQIbAwYLCQgHAwIEFQIIAwQWAgMBAh4BAheAAAoJEA7H
            5Qi+CcVxWZ8D/1MyYvfj3FJPZUm2Yo1zZsQ657vHI9+pPouqflWOayRR9jbiyUFIn0VdQBrP
            t0FwvnOFArUovUWoKAEdqR8hPy3M3APUZjl5K4cMZR/xaMQeQRZ5CHpS4DBKURKAHC0ltS5o
            uBJKQOZm5iltJp15cgyIkBkGe8Mx18VFyVglAZey
            =Y2oI
            -----END PGP PUBLIC KEY BLOCK-----

Breakdown of the entries in the ``sources:`` list:

* ``curtin-dev-ppa.list:``

  - ``source:`` Creates a file in ``/etc/apt/sources.list.d/`` for the sources
    list entry based on the key:
    ``/etc/apt/sources.list.d/curtin-dev-ppa.list``

  - ``keyid:`` Imports a GPG key for a given ``keyid``. Used keyserver defaults
    to ``keyserver.ubuntu.com``.

* ``ignored1:``

  - ``source:`` Creates a PPA shortcut, setting up the correct APT
    ``sources.list`` line and auto-imports the signing key from Launchpad.

    See ``https://help.launchpad.net/Packaging/PPA`` for more information.
    This requires ``'add-apt-repository'``, and will create a file in
    ``/etc/apt/sources.list.d`` automatically, therefore the key here is
    ignored as filename in those cases.

* ``my-repo2.list:``

  - ``source:`` Uses replacement variables. Sources can use ``$MIRROR``,
    ``$PRIMARY``, ``$SECURITY``, ``$RELEASE`` and ``$KEY_FILE`` replacement
    variables. They will be replaced with the default or specified mirrors and
    the running release. The entry in this example may be turned into e.g.:
    ``source: deb http://archive.ubuntu.com/ubuntu bionic multiverse``

* ``my-repo3.list:``

  - This would have the same end effect as ``'ppa:curtin-dev/test-archive'``.

* ``ignored2:``

  - Specifying only the key would result in only importing the key without
    adding a PPA or other source spec. Since this doesn't generate a
    ``source.list`` file the filename key is ignored.

* ``ignored3:``

  - Alternative ``keyid`` can also be specified via their long fingerprints.

* ``ignored4:``

  - Alternative keyservers can also be specified to fetch keys from.

* ``ignored5:``

  - One can specify ``[signed-by=$KEY_FILE]`` in the source definition, which
    will install the key in the directory ``/etc/cloud-init.gpg.d/`` and the
    ``$KEY_FILE`` replacement variable will be replaced with the path to the
    specified key. If ``$KEY_FILE`` is used, but no key is specified,
    APT update will (rightfully) fail due to an invalid value.

* ``my-repo4.list:``

  - The APT signing key can also be specified by providing a PGP public key
    block. Providing the PGP key this way is the most robust method for
    specifying a key, as it removes dependency on a remote key server.

    As with ``keyid``, this can be specified with or without some actual source
    content.

.. LINKS
.. _APT configure module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#apt-configure
