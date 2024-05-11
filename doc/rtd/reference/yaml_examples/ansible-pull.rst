.. _cce-ansible-pull:

Install and run Ansible pull
****************************

If you're already installing other packages, you may want to manually install
Ansible to avoid multiple calls to your package manager. This example shows
how to install Ansible using ``pip`` and run the ``ubuntu.yml`` playbook,
pulled from a specific git repository.

For a full list of keys, refer to the `Ansible module`_ schema.

.. code-block:: yaml

    #cloud-config
    package_update: true
    package_upgrade: true

    packages:
      - git
    ansible:
      install_method: pip
      pull:
        url: "https://github.com/holmanb/vmboot.git"
        playbook_name: ubuntu.yml

.. LINKS
.. _Ansible module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ansible
