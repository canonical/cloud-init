.. _datasource_rbx:

Rbx Cloud
*********

The Rbx datasource consumes the metadata drive available on the `HyperOne`_
and `Rootbox`_ platforms.

This datasource supports network configurations, hostname, user accounts and
user metadata.

Metadata drive
==============

Drive metadata is a `FAT`_-formatted partition with the ``CLOUDMD`` or
``cloudmd`` label on the system disk. Its contents are refreshed each time
the virtual machine is restarted, if the partition exists. For more information
see `HyperOne Virtual Machine docs`_.

.. _HyperOne: http://www.hyperone.com/
.. _Rootbox: https://rootbox.com/
.. _HyperOne Virtual Machine docs: http://www.hyperone.com/
.. _FAT: https://en.wikipedia.org/wiki/File_Allocation_Table
