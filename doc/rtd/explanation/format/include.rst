.. _user_data_formats-include:

Include file
============

Example
-------

.. code-block:: text

    #include
    https://raw.githubusercontent.com/canonical/cloud-init/403f70b930e3ce0f05b9b6f0e1a38d383d058b53/doc/examples/cloud-config-run-cmds.txt
    https://raw.githubusercontent.com/canonical/cloud-init/403f70b930e3ce0f05b9b6f0e1a38d383d058b53/doc/examples/cloud-config-boot-cmds.txt

Explanation
-----------

An include file contains a list of URLs, one per line. Each of the URLs will
be read and their content can be any kind of user-data format. If an error
occurs reading a file the remaining files will not be read.
