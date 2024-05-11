.. _cce-ansible:

Install Ansible
***************

These examples show how to achieve a basic installation of Ansible, and
configures the location that playbooks should be pulled from.

For a full list of keys, refer to the `Ansible module`_ schema.

Install via package manager
===========================

This example will use the operating system distribution's package manager to
install Ansible.

.. code-block:: yaml

    #cloud-config
    ansible:
      package_name: ansible-core
      install_method: distro
      pull:
        url: "https://github.com/holmanb/vmboot.git"
        playbook_name: ubuntu.yml


Install via pip
===============

This example uses the Python package manager ``pip`` to install Ansible.

.. code-block: yaml

    #cloud-config
    ansible:
      package_name: ansible-core
      install_method: pip
      pull:
        url: "https://github.com/holmanb/vmboot.git"
        playbook_name: ubuntu.yml

.. LINKS
.. _Ansible module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ansible
