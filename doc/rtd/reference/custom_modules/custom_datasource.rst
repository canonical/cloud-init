.. _custom_datasource:

Custom DataSource
*****************

Custom 3rd-party out-of-tree DataSources can be added to cloud-init by:

#. :ref:`Implement a DataSource<datasource_creation>` in a Python file.

#. Place that file in as a single Python module or package in folder included
   in ``$PYTHONPATH``.

#. Extend the base configuration's
   :ref:`datasource_pkg_list<base_config_datasource_pkg_list>` to include the
   Python package where the DataSource is located.

#. Extend the :ref:`base-configuration<base_config_reference>`'s
   :ref:`datasource_list<base_config_datasource_list>` to include the name of
   the custom DataSource.
