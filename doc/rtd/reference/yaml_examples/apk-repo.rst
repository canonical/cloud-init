.. _cce-apk-repo:

Configure APK repositories
**************************

These examples show how to configure the ``/etc/apk/repositories`` file. For a
full list of keys, refer to the `APK configure module`_ schema.


Keep the existing ``/etc/apk/repositories`` file unaltered.

.. code-block:: yaml

    #cloud-config
    apk_repos:
        preserve_repositories: true

Alpine v3.12
============

Create the repositories file for Alpine v3.12 main and community, using the
default mirror site.

.. code-block:: yaml

    #cloud-config
    apk_repos:
        alpine_repo:
            community_enabled: true
            version: 'v3.12'

Alpine Edge
===========

Create the repositories file for Alpine Edge main, community, and testing,
using a specified mirror site and a local repo.

.. code-block:: yaml

    #cloud-config
    apk_repos:
        alpine_repo:
            base_url: 'https://some-alpine-mirror/alpine'
            community_enabled: true
            testing_enabled: true
            version: 'edge'
        local_repo_base_url: 'https://my-local-server/local-alpine'

.. LINKS
.. _APK configure module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#apk-configure
