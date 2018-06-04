.. _datasource_ec2:

Amazon EC2
==========

The EC2 datasource is the oldest and most widely used datasource that
cloud-init supports. This datasource interacts with a *magic* ip that is
provided to the instance by the cloud provider. Typically this ip is
``169.254.169.254`` of which at this ip a http server is provided to the
instance so that the instance can make calls to get instance userdata and
instance metadata.

Metadata is accessible via the following URL:

::
    
    GET http://169.254.169.254/2009-04-04/meta-data/
    ami-id
    ami-launch-index
    ami-manifest-path
    block-device-mapping/
    hostname
    instance-id
    instance-type
    local-hostname
    local-ipv4
    placement/
    public-hostname
    public-ipv4
    public-keys/
    reservation-id
    security-groups

Userdata is accessible via the following URL:

::
    
    GET http://169.254.169.254/2009-04-04/user-data
    1234,fred,reboot,true | 4512,jimbo, | 173,,,

Note that there are multiple versions of this data provided, cloud-init
by default uses **2009-04-04** but newer versions can be supported with
relative ease (newer versions have more data exposed, while maintaining
backward compatibility with the previous versions). 

To see which versions are supported from your cloud provider use the following URL:

::
    
    GET http://169.254.169.254/
    1.0
    2007-01-19
    2007-03-01
    2007-08-29
    2007-10-10
    2007-12-15
    2008-02-01
    2008-09-01
    2009-04-04
    ...
    latest



Configuration
-------------
The following configuration can be set for the datasource in system
configuration (in `/etc/cloud/cloud.cfg` or `/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

 * **metadata_urls**: This list of urls will be searched for an Ec2
   metadata service. The first entry that successfully returns a 200 response
   for <url>/<version>/meta-data/instance-id will be selected.
   (default: ['http://169.254.169.254', 'http://instance-data:8773']).
 * **max_wait**:  the maximum amount of clock time in seconds that should be
   spent searching metadata_urls.  A value less than zero will result in only
   one request being made, to the first in the list. (default: 120)
 * **timeout**: the timeout value provided to urlopen for each individual http
   request.  This is used both when selecting a metadata_url and when crawling
   the metadata service. (default: 50)

An example configuration with the default values is provided below:

.. sourcecode:: yaml

  datasource:
   Ec2:
    metadata_urls: ["http://169.254.169.254:80", "http://instance-data:8773"]
    max_wait: 120
    timeout: 50

.. vi: textwidth=78
