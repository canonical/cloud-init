.. _module_creation:

Module creation
***************

Much of ``cloud-init``'s functionality is provided by :ref:`modules<modules>`.
All modules follow a similar layout in order to provide consistent execution
and documentation. Use the example provided here to create a new module.

Example
=======

.. code-block:: python

    # This file is part of cloud-init. See LICENSE file for license information.
    """Example Module: Shows how to create a module"""

    import logging
    from cloudinit.cloud import Cloud
    from cloudinit.config import Config
    from cloudinit.config.schema import MetaSchema, get_meta_doc
    from cloudinit.distros import ALL_DISTROS
    from cloudinit.settings import PER_INSTANCE

    MODULE_DESCRIPTION = """\
    Description that will be used in module documentation.

    This will likely take multiple lines.
    """

    LOG = logging.getLogger(__name__)

    meta: MetaSchema = {
        "id": "cc_example",
        "name": "Example Module",
        "title": "Shows how to create a module",
        "description": MODULE_DESCRIPTION,
        "distros": [ALL_DISTROS],
        "frequency": PER_INSTANCE,
        "activate_by_schema_keys": ["example_key, example_other_key"],
        "examples": [
            "example_key: example_value",
            "example_other_key: ['value', 2]",
        ],
    }

    __doc__ = get_meta_doc(meta)


    def handle(
        name: str, cfg: Config, cloud: Cloud, args: list
    ) -> None:
        LOG.debug(f"Hi from module {name}")

.. _module_creation-Guidelines:

Guidelines
==========

* Create a new module in the :file:`cloudinit/config` directory with a ``cc_``
  prefix.
* Your module must include a ``handle`` function. The arguments are:

  * ``name``: The module name specified in the configuration.
  * ``cfg``: A configuration object that is the result of the merging of
    cloud-config configuration with any datasource-provided configuration.
  * ``cloud``: A cloud object that can be used to access various datasource
    and paths for the given distro and data provided by the various datasource
    instance types.
  * ``args``: An argument list. This is usually empty and is only populated
    if the module is called independently from the command line or if the
    module definition in :file:`/etc/cloud/cloud.cfg[.d]` has been modified
    to pass arguments to this module.

* If your module introduces any new cloud-config keys, you must provide a
  schema definition in `cloud-init-schema.json`_.
* The ``meta`` variable must exist and be of type `MetaSchema`_.

  * ``id``: The module ID. In most cases this will be the filename without
    the ``.py`` extension.
  * ``distros``: Defines the list of supported distros. It can contain
    any of the values (not keys) defined in the `OSFAMILIES`_ map or
    ``[ALL_DISTROS]`` if there is no distro restriction.
  * ``frequency``: Defines how often module runs. It must be one of:

    * ``PER_ALWAYS``: Runs on every boot.
    * ``ONCE``: Runs only on first boot.
    * ``PER_INSTANCE``: Runs once per instance. When exactly this happens
      is dependent on the datasource, but may triggered any time there
      would be a significant change to the instance metadata. An example
      could be an instance being moved to a different subnet.

  * ``activate_by_schema_keys``: Optional list of cloud-config keys that will
    activate this module. When this list not empty, the config module will be
    skipped unless one of the ``activate_by_schema_keys`` are present in merged
    cloud-config instance-data.
  * ``examples``: Lists examples of any cloud-config keys this module reacts
    to. These examples will be rendered in the module reference documentation
    and will automatically be tested against the defined schema
    during testing.

* ``__doc__ = get_meta_doc(meta)`` is necessary to provide proper module
  documentation.

Module execution
================

In order for a module to be run, it must be defined in a module run section in
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
