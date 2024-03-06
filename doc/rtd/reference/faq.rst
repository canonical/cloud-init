.. _faq:

FAQ
***

How do I get help?
==================

Having trouble? We would like to help!

- First go through this page with answers to common questions
- Use the search bar at the upper left to search our documentation
- Ask questions in the ``#cloud-init`` `IRC channel on Libera`_
- Join and ask questions on the ``cloud-init`` `mailing list`_
- Find a bug? Check out the :ref:`reporting_bugs` topic to find out how to
  report one

``autoinstall``, ``preruncmd``, ``postruncmd``
==============================================

Since ``cloud-init`` ignores top level user data ``cloud-config`` keys, other
projects such as `Juju`_ and `Subiquity autoinstaller`_ use a YAML-formatted
config that combines ``cloud-init``'s user data cloud-config YAML format with
their custom YAML keys. Since ``cloud-init`` ignores unused top level keys,
these combined YAML configurations may be valid ``cloud-config`` files,
however keys such as ``autoinstall``, ``preruncmd``, and ``postruncmd`` are
not used by ``cloud-init`` to configure anything.

Please direct bugs and questions about other projects that use ``cloud-init``
to their respective support channels. For Subiquity autoinstaller that is via
IRC (``#ubuntu-server`` on Libera) or Discourse. For Juju support see their
`discourse page`_.

Can I use cloud-init as a library?
==================================
Please don't. Some projects `do`_. However, ``cloud-init`` does not
currently make any API guarantees to either external consumers or out-of-tree
datasources / modules. Current users of cloud-init as a library are
projects that have close contact with ``cloud-init``, which is why this
(fragile) model currently works.

For those that choose to ignore this advice, logging in cloud-init is
configured in ``cloud-init/cmd/main.py``, and reconfigured in the
``cc_rsyslog`` module for obvious reasons.

Where can I learn more?
=======================

Below are some videos, blog posts, and white papers about ``cloud-init`` from a
variety of sources.

Videos:

- `cloud-init - The Good Parts`_
- `Perfect Proxmox Template with Cloud Image and Cloud Init`_
  [proxmox, cloud-init, template]
- `cloud-init - Building clouds one Linux box at a time (Video)`_
- `Metadata and cloud-init`_
- `Introduction to cloud-init`_

Blog Posts:

- `cloud-init - The cross-cloud Magic Sauce (PDF)`_
- `cloud-init - Building clouds one Linux box at a time (PDF)`_
- `The beauty of cloud-init`_
- `Cloud-init Getting Started`_ [fedora, libvirt, cloud-init]
- `Build Azure Devops Agents With Linux cloud-init for Dotnet Development`_
  [terraform, azure, devops, docker, dotnet, cloud-init]
- `Cloud-init Getting Started`_ [fedora, libvirt, cloud-init]
- `Setup Neovim cloud-init Completion`_
  [neovim, yaml, Language Server Protocol, jsonschema, cloud-init]

Events:

- `cloud-init Summit 2019`_
- `cloud-init Summit 2018`_
- `cloud-init Summit 2017`_

Whitepapers:

- `Utilising cloud-init on Microsoft Azure (Whitepaper)`_
- `Cloud Instance Initialization with cloud-init (Whitepaper)`_

.. _mailing list: https://launchpad.net/~cloud-init
.. _IRC channel on Libera: https://kiwiirc.com/nextclient/irc.libera.chat/cloud-init
.. _Juju: https://ubuntu.com/blog/topics/juju
.. _discourse page: https://discourse.charmhub.io
.. _do: https://github.com/canonical/ubuntu-pro-client/blob/9b46480b9e4b88e918bac5ced0d4b8edb3cbbeab/lib/auto_attach.py#L35

.. _cloud-init - The Good Parts: https://www.youtube.com/watch?v=2_m6EUo6VOI
.. _Utilising cloud-init on Microsoft Azure (Whitepaper): https://ubuntu.com/engage/azure-cloud-init-whitepaper
.. _Cloud Instance Initialization with cloud-init (Whitepaper): https://ubuntu.com/blog/cloud-instance-initialisation-with-cloud-init

.. _cloud-init - The cross-cloud Magic Sauce (PDF): https://events.linuxfoundation.org/wp-content/uploads/2017/12/cloud-init-The-cross-cloud-Magic-Sauce-Scott-Moser-Chad-Smith-Canonical.pdf
.. _cloud-init - Building clouds one Linux box at a time (Video): https://www.youtube.com/watch?v=1joQfUZQcPg
.. _cloud-init - Building clouds one Linux box at a time (PDF): https://web.archive.org/web/20181111020605/https://annex.debconf.org/debconf-share/debconf17/slides/164-cloud-init_Building_clouds_one_Linux_box_at_a_time.pdf
.. _Metadata and cloud-init: https://www.youtube.com/watch?v=RHVhIWifVqU
.. _The beauty of cloud-init: https://web.archive.org/web/20180830161317/http://brandon.fuller.name/archives/2011/05/02/06.40.57/
.. _Introduction to cloud-init: http://www.youtube.com/watch?v=-zL3BdbKyGY
.. _Build Azure Devops Agents With Linux cloud-init for Dotnet Development: https://codingsoul.org/2022/04/25/build-azure-devops-agents-with-linux-cloud-init-for-dotnet-development/
.. _Perfect Proxmox Template with Cloud Image and Cloud Init: https://www.youtube.com/watch?v=shiIi38cJe4
.. _Cloud-init Getting Started: https://blog.while-true-do.io/cloud-init-getting-started/
.. _Setup Neovim cloud-init Completion: https://phoenix-labs.xyz/blog/setup-neovim-cloud-init-completion/

.. _cloud-init Summit 2019: https://powersj.io/post/cloud-init-summit19/
.. _cloud-init Summit 2018: https://powersj.io/post/cloud-init-summit18/
.. _cloud-init Summit 2017: https://powersj.io/post/cloud-init-summit17/
.. _Subiquity autoinstaller: https://ubuntu.com/server/docs/install/autoinstall
.. _juju_project: https://discourse.charmhub.io/t/model-config-cloudinit-userdata/512
.. _discourse page: https://discourse.charmhub.io
