.. _module_creation:

Module Creation
***************

Much of cloud-init functionality is provided by :ref:`modules<modules>`.
All modules follow a similar layout in order to provide consistent execution
and documentation. Use the example provided here to create a new module.

Example
=======
.. code-block:: python

    # This file is part of cloud-init. See LICENSE file for license information.
    """Example Module: Shows how to create a module"""

    from logging import Logger

    from cloudinit.cloud import Cloud
    from cloudinit.config.schema import MetaSchema, get_meta_doc
    from cloudinit.distros import ALL_DISTROS
    from cloudinit.settings import PER_INSTANCE

    MODULE_DESCRIPTION = """\
    Description that will be used in module documentation.

    This will likely take multiple lines.
    """

    meta: MetaSchema = {
        "id": "cc_example",
        "name": "Example Module",
        "title": "Shows how to create a module",
        "description": MODULE_DESCRIPTION,
        "distros": [ALL_DISTROS],
        "frequency": PER_INSTANCE,
        "examples": [
            "cc_example: example1",
            "cc_example: ['example', 2]",
        ],
    }

    __doc__ = get_meta_doc(meta)


    def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, args: list):
        log.debug(f"Hi from module {name}")


Guidelines
==========

* Create a new module in the ``cloudinit/config`` directory with a `cc_`
  prefix.
* Your module must include a ``handle`` function. The arguments are:

  * ``name``: The module name specified in the configuration
  * ``cfg``: A configuration object that is the result of the merging of
    cloud-config configuration with any datasource provided configuration.
  * ``cloud``: A cloud object that can be used to access various datasource
    and paths for the given distro and data provided by the various datasource
    instance types.
  * ``log``: A logger object that can be used to log messages.
  * ``args``: An argument list. This is usually empty and is only populated
    if the module is called independently from the command line.

* If your module introduces any new cloud-config keys, you must provide a
  schema definition in `cloud-init-schema.json`_.
* The ``meta`` variable must exist and be of type `MetaSchema`_.

  * ``distros``: Defines the list of supported distros. It can contain
    any of the values (not keys) defined in the `OSFAMILIES`_ map or
    ``[ALL_DISTROS]`` if there is no distro restriction.
  * ``frequency``: Defines how often module runs. It must be one of:

    * ``PER_ALWAYS``: Runs on every boot.
    * ``ONCE``: Runs only on first boot.
    * ``PER_INSTANCE``: Runs once per instance. When exactly this happens
      is dependent on the datasource but may triggered anytime there
      would be a significant change to the instance metadata. An example
      could be an instance being moved to a different subnet.

  * ``examples``: Lists examples to be shown in the documentation.
    These examples will automatically be tested against the defined schema
    during testing.

* ``__doc__ = get_meta_doc(meta)`` is necessary to provide proper module
  documentation.


.. _MetaSchema: https://github.com/canonical/cloud-init/blob/3bcffacb216d683241cf955e4f7f3e89431c1491/cloudinit/config/schema.py#L58
.. _OSFAMILIES: https://github.com/canonical/cloud-init/blob/3bcffacb216d683241cf955e4f7f3e89431c1491/cloudinit/distros/__init__.py#L35
.. _settings.py: https://github.com/canonical/cloud-init/blob/3bcffacb216d683241cf955e4f7f3e89431c1491/cloudinit/settings.py#L66
.. _cloud-init-schema.json: https://github.com/canonical/cloud-init/blob/main/cloudinit/config/cloud-init-schema.json
