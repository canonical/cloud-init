.. _cce-gluster:

Gluster
*******

This example mounts ``volfile`` exported by ``glusterfsd``, running on
``volfile-server-hostname`` onto the local mount point ``/mnt/data``.

Replace ``volfile-server-hostname`` with one of your nodes running
``glusterfsd``.

.. code-block:: yaml

    #cloud-config
    packages:
     - glusterfs-client
    mounts:
     - [ 'volfile-server-hostname:6996', /mnt/data, glusterfs, "defaults,nofail", "0", "2" ]
    runcmd:
     - [ modprobe, fuse ]
     - [ mkdir, '-p', /mnt/data ]
     - [ mount, '-a' ]
