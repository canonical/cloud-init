.. _datasource_exoscale:

Exoscale
========

This datasource supports reading from the metadata server used on the
`Exoscale platform <https://exoscale.com>`_.

Use of the Exoscale datasource is recommended to benefit from new features of
the Exoscale platform.

The datasource relies on the availability of a compatible metadata server
(``http://169.254.169.254`` is used by default) and its companion password
server, reachable at the same address (by default on port 8080).

Crawling of metadata
--------------------

The metadata service and password server are crawled slightly differently:

 * The "metadata service" is crawled every boot.
 * The password server is also crawled every boot (the Exoscale datasource
   forces the password module to run with "frequency always").

In the password server case, the following rules apply in order to enable the
"restore instance password" functionality:

 * If a password is returned by the password server, it is then marked "saved"
   by the cloud-init datasource. Subsequent boots will skip setting the
   password (the password server will return "saved_password").
 * When the instance password is reset (via the Exoscale UI), the password
   server will return the non-empty password at next boot, therefore causing
   cloud-init to reset the instance's password.

Configuration
-------------

Users of this datasource are discouraged from changing the default settings
unless instructed to by Exoscale support.

The following settings are available and can be set for the datasource in
system configuration (in `/etc/cloud/cloud.cfg.d/`).

The settings available are:

 * **metadata_url**: The URL for the metadata service (defaults to
   ``http://169.254.169.254``)
 * **api_version**: The API version path on which to query the instance
   metadata (defaults to ``1.0``)
 * **password_server_port**: The port (on the metadata server) on which the
   password server listens (defaults to ``8080``).
 * **timeout**: the timeout value provided to urlopen for each individual http
   request. (defaults to ``10``)
 * **retries**: The number of retries that should be done for an http request
   (defaults to ``6``)


An example configuration with the default values is provided below:

.. sourcecode:: yaml

   datasource:
     Exoscale:
       metadata_url: "http://169.254.169.254"
       api_version: "1.0"
       password_server_port: 8080
       timeout: 10
       retries: 6
