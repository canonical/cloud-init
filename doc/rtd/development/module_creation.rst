.. _module_creation:

Module creation
***************

Much of ``cloud-init``'s functionality is provided by :ref:`modules<modules>`.
All modules follow a similar layout in order to provide consistent execution
and documentation. Use the example provided here to create a new module.

.. _module_creation-Guidelines:

Your Python module
==================

Modules are located in the ``cloudinit/config/`` directory, where the naming
convention for modules is to use ``cc_<module_name>`` (with underscores as the
separators).

The handle function
-------------------

Your module must include a ``handle`` function. The arguments are:

- ``name``: The module name specified in the configuration.
- ``cfg``: A configuration object that is the result of the merging of
  cloud-config configuration with any datasource-provided configuration.
- ``cloud``: A cloud object that can be used to access various datasource
  and paths for the given distro and data provided by the various datasource
  instance types.
- ``args``: An argument list. This is usually empty and is only populated
  if the module is called independently from the command line or if the
  module definition in :file:`/etc/cloud/cloud.cfg[.d]` has been modified
  to pass arguments to this module.

Schema definition
-----------------

If your module introduces any new cloud-config keys, you must provide a schema
definition in `cloud-init-schema.json`_.

- The ``meta`` variable must exist and be of type `MetaSchema`_.

  - ``id``: The module ID. In most cases this will be the filename without
    the ``.py`` extension.
  - ``distros``: Defines the list of supported distros. It can contain
    any of the values (not keys) defined in the `OSFAMILIES`_ map or
    ``[ALL_DISTROS]`` if there is no distro restriction.
  - ``frequency``: Defines how often module runs. It must be one of:

    - ``PER_ALWAYS``: Runs on every boot.
    - ``ONCE``: Runs only on first boot.
    - ``PER_INSTANCE``: Runs once per instance. When exactly this happens
      is dependent on the datasource, but may be triggered any time there
      would be a significant change to the instance metadata. An example
      could be an instance being moved to a different subnet.

  - ``activate_by_schema_keys``: Optional list of cloud-config keys that will
    activate this module. When this list not empty, the config module will be
    skipped unless one of the ``activate_by_schema_keys`` are present in merged
    cloud-config instance-data.

Example module.py file
======================

.. code-block:: python

    # This file is part of cloud-init. See LICENSE file for license information.
    """Example Module: Shows how to create a module"""

    import logging
    from cloudinit.cloud import Cloud
    from cloudinit.config import Config
    from cloudinit.config.schema import MetaSchema
    from cloudinit.distros import ALL_DISTROS
    from cloudinit.settings import PER_INSTANCE

    LOG = logging.getLogger(__name__)

    meta: MetaSchema = {
        "id": "cc_example",
        "distros": [ALL_DISTROS],
        "frequency": PER_INSTANCE,
        "activate_by_schema_keys": ["example_key, example_other_key"],
    } # type: ignore

    def handle(
        name: str, cfg: Config, cloud: Cloud, args: list
    ) -> None:
        LOG.debug(f"Hi from module {name}")

Module documentation
====================

Every module has a folder in the ``doc/module-docs/`` directory, containing
a ``data.yaml`` file, and one or more ``example*.yaml`` files.

- The ``data.yaml`` file contains most of the documentation fields. At a
  minimum, your module should be provided with this file. Examples are not
  strictly required, but are helpful to readers of the documentation so it is
  preferred for at least one example to be included.
- The ``example*.yaml`` files are illustrative demonstrations of using the
  module, but should be self-contained and in correctly-formatted YAML. These
  will be automatically tested against the defined schema.

Example data.yaml file
----------------------

.. code-block:: yaml

   cc_module_name:
     description: >
       This module provides some functionality, which you can describe here.

       For straightforward text examples, use a greater-than (``>``) symbol
       next to ``description: `` to ensure proper rendering in the
       documentation. Empty lines will be respected, but line-breaks are
       folded together to create proper paragraphs.

       If you need to use call-outs or code blocks, use a pipe (``|``) symbol
       instead of ``>`` so that reStructuredText formatting (e.g. for
       directives, which take varying levels of indentation) is respected.
     examples:
     - comment: |
         Example 1: (optional) description of the expected behavior of the example
       file: cc_module_name/example1.yaml
     - comment: |
         Example 2: (optional) description of a second example.
       file: cc_module_name/example2.yaml
     name: Module Name
     title: Very brief (1 sentence) tag line describing what your module does

Rendering the module docs
-------------------------

The module documentation is auto-generated via the
:file:`doc/rtd/reference/modules.rst` file.

For your module documentation to be shown in the cloud-init docs, you will
need to add an entry to this page. Modules are listed in alphabetical order.
The entry should be in the following reStructuredText format:

.. code-block:: text

   .. datatemplate:yaml:: ../../module-docs/cc_ansible/data.yaml
      :template: modules.tmpl

The template pulls information from both your ``module.py`` file, and from its
corresponding entry in the the ``module-docs`` directory.

Module execution
================

For a module to be run, it must be defined in a module run section in
:file:`/etc/cloud/cloud.cfg` or :file:`/etc/cloud/cloud.cfg.d` on the launched
instance. The three module sections are
`cloud_init_modules`_, `cloud_config_modules`_, and `cloud_final_modules`_,
corresponding to the :ref:`Network<boot-Network>`, :ref:`Config<boot-Config>`,
and :ref:`Final<boot-Final>` boot stages respectively.

Add your module to `cloud.cfg.tmpl`_ under the appropriate module section.
Each module gets run in the order listed, so ensure your module is defined
in the correct location based on dependencies. If your module has no particular
dependencies or is not necessary for a later boot stage, it should be placed
in the ``cloud_final_modules`` section before the ``final-message`` module.


.. _MetaSchema: https://github.com/canonical/cloud-init/blob/3bcffacb216d683241cf955e4f7f3e89431c1491/cloudinit/config/schema.py#L58
.. _OSFAMILIES: https://github.com/canonical/cloud-init/blob/3bcffacb216d683241cf955e4f7f3e89431c1491/cloudinit/distros/__init__.py#L35
.. _settings.py: https://github.com/canonical/cloud-init/blob/3bcffacb216d683241cf955e4f7f3e89431c1491/cloudinit/settings.py#L66
.. _cloud-init-schema.json: https://github.com/canonical/cloud-init/blob/main/cloudinit/config/schemas/versions.schema.cloud-config.json
.. _cloud.cfg.tmpl: https://github.com/canonical/cloud-init/blob/main/config/cloud.cfg.tmpl
.. _cloud_init_modules: https://github.com/canonical/cloud-init/blob/b4746b6aed7660510071395e70b2d6233fbdc3ab/config/cloud.cfg.tmpl#L70
.. _cloud_config_modules: https://github.com/canonical/cloud-init/blob/b4746b6aed7660510071395e70b2d6233fbdc3ab/config/cloud.cfg.tmpl#L101
.. _cloud_final_modules: https://github.com/canonical/cloud-init/blob/b4746b6aed7660510071395e70b2d6233fbdc3ab/config/cloud.cfg.tmpl#L144
