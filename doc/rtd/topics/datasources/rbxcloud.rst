.. _datasource_rbx:

Rbx Cloud
=========

The Rbx datasource consumes the metadata drive available on platform
`HyperOne`_ and `Rootbox`_ platform.

Datasource supports, in particular, network configurations, hostname,
user accounts and user metadata.

Metadata drive
--------------

Drive metadata is a `FAT`_-formatted partition with the ```CLOUDMD``` label on
the system disk. Its contents are refreshed each time the virtual machine
is restarted, if the partition exists. For more information see
`HyperOne Virtual Machine docs`_.

.. _HyperOne: http://www.hyperone.com/
.. _Rootbox: https://rootbox.com/
.. _HyperOne Virtual Machine docs: http://www.hyperone.com/
.. _FAT: https://en.wikipedia.org/wiki/File_Allocation_Table

.. vi: textwidth=78
