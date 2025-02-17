.. _launch_libvirt:

Run cloud-init locally with libvirt
***********************************

`Libvirt`_ is a tool for managing virtual machines and containers.

Create your configuration
-------------------------

.. include:: shared/create_config.txt

Download a cloud image
----------------------

.. include:: shared/download_image.txt

Create an instance
------------------

.. code-block:: shell-session

    virt-install --name cloud-init-001 --memory 4000 --noreboot \
        --os-variant detect=on,name=ubuntujammy \
        --disk=size=10,backing_store="$(pwd)/jammy-server-cloudimg-amd64.img" \
        --cloud-init user-data="$(pwd)/user-data,meta-data=$(pwd)/meta-data,network-config=$(pwd)/network-config"

.. LINKS
.. _Libvirt: https://libvirt.org/

