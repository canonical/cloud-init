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

An include file contains a list of URLs, one per line. Blank lines and lines
that begin with ``#`` are ignored. Each URL is fetched in order and its content
is processed as if it had been supplied directly as user-data: it may be any
supported user-data format (for example, a cloud-config, a user-data script,
gzip, or a MIME multi-part archive) and may itself contain further include
directives. If an error occurs reading a file, the remaining files are not
read.

Include once
------------

Example
~~~~~~~

.. code-block:: text

    #include-once
    https://example.com/bootstrap/cloud-config.yaml

    #include
    https://example.com/always-fetched.txt

Explanation
~~~~~~~~~~~

A ``#include-once`` line (or a part with Content-Type
``text/x-include-once-url``) applies to the URLs listed after it: each such
URL is fetched only the first time it is needed. The fetched content is cached
in the ``urlcache`` directory of the instance's data path with permissions
``0600``, and later boots re-read the cached content instead of requesting the
URL again. A following ``#include`` line switches back to fetching every URL.

This is useful for one-time-use or expiring URLs, and where repeatedly fetching
the same data is undesirable. The fetched content is still stored on disk, so
treat the instance data directory as sensitive, and avoid placing secrets in
the URL itself where they might be logged.
