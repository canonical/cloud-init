.. _cce-grub-dpkg:

Configure target for GRUB installation
**************************************

For a full list of keys, refer to the `grub dpkg module`_ schema.

.. code-block:: yaml

    #cloud-config
    grub_dpkg:
      enabled: true
      # BIOS mode (install_devices needs disk)
      grub-pc/install_devices: /dev/sda
      grub-pc/install_devices_empty: false
      # EFI mode (install_devices needs partition)
      grub-efi/install_devices: /dev/sda

.. LINKS
.. _grub dpkg module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#grub-dpkg
