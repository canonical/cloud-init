.. _cce-zypper-repo:

Configure Zypper repositories
*****************************

This example shows how to configure a Zypper repository. For a full list of
keys, refer to the `Zypper add repo module`_ schema.

.. code-block:: yaml

    #cloud-config
    zypper:
      repos:
        - id: opensuse-oss
          name: os-oss
          baseurl: http://dl.opensuse.org/dist/leap/v/repo/oss/
          enabled: 1
          autorefresh: 1
        - id: opensuse-oss-update
          name: os-oss-up
          baseurl: http://dl.opensuse.org/dist/leap/v/update
          # any setting per
          # https://en.opensuse.org/openSUSE:Standards_RepoInfo
          # enable and autorefresh are on by default
      config:
        reposdir: /etc/zypp/repos.dir
        servicesdir: /etc/zypp/services.d
        download.use_deltarpm: true
        # any setting in /etc/zypp/zypp.conf

.. LINKS
.. _Zypper add repo module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#zypper-add-repo
