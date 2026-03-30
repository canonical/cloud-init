:orphan:

.. _datasource_dsname:

Datasource dsname
*****************

Each datasource has an attribute called dsname. This may be used in the
kernel command line to
:ref:`override datasource detection<kernel_datasource_override>`. The
``dsname`` on the kernel command line may be a case-insensitive match. See the
mapping between datasource module names and ``dsname`` in the table below.


..
    generate the following map with the following one-liner:

    find cloudinit/sources -name 'DataSource*.py' | sort -u \
    |  xargs grep 'dsname =' \
    | awk -F '[/:"]' 'BEGIN { print "**Datasource Module**, **dsname**" }\
      {print $3 ", " $5}'


.. csv-table::
   :align: left

    **Datasource Module**, **dsname**
    DataSourceAkamai.py, Akamai
    DataSourceAliYun.py, AliYun
    DataSourceAltCloud.py, AltCloud
    DataSourceAzure.py, Azure
    DataSourceBigstep.py, Bigstep
    DataSourceCloudSigma.py, CloudSigma
    DataSourceCloudStack.py, CloudStack
    DataSourceConfigDrive.py, ConfigDrive
    DataSourceDigitalOcean.py, DigitalOcean
    DataSourceEc2.py, Ec2
    DataSourceExoscale.py, Exoscale
    DataSourceGCE.py, GCE
    DataSourceHetzner.py, Hetzner
    DataSourceIBMCloud.py, IBMCloud
    DataSourceLXD.py, LXD
    DataSourceMAAS.py, MAAS
    DataSourceNoCloud.py, NoCloud
    DataSourceNone.py, None
    DataSourceNWCS.py, NWCS
    DataSourceOpenNebula.py, OpenNebula
    DataSourceOpenStack.py, OpenStack
    DataSourceOracle.py, Oracle
    DataSourceOVF.py, OVF
    DataSourceRbxCloud.py, RbxCloud
    DataSourceScaleway.py, Scaleway
    DataSourceSmartOS.py, Joyent
    DataSourceUpCloud.py, UpCloud
    DataSourceVMware.py, VMware
    DataSourceVultr.py, Vultr
    DataSourceWSL.py, WSL
