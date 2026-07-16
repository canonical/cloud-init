.. _cce-ansible:

Install Ansible
***************

These examples show how to achieve a basic installation of Ansible, and
configures the location that playbooks should be pulled from.

For a full list of keys, refer to the :ref:`Ansible module <mod_cc_ansible>`
schema.

Install via package manager
===========================

This example will use the operating system distribution's package manager to
install Ansible.

.. literalinclude:: ../../../module-docs/cc_ansible/example1.yaml
   :language: yaml
   :linenos:

Install via pip
===============

This example uses the Python package manager ``pip`` to install Ansible.

.. literalinclude:: ../../../module-docs/cc_ansible/example2.yaml
   :language: yaml
   :linenos:

Install and run Ansible pull
============================

If you're already installing other packages, you may want to manually install
Ansible to avoid multiple calls to your package manager. This example shows
how to install Ansible using ``pip`` and run the ``ubuntu.yml`` playbook,
pulled from a specific git repository.

For a full list of keys, refer to the :ref:`Ansible module <mod_cc_ansible>`
schema.

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

