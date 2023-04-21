.. _datasource_dsname:

Datasource dsname
*****************

Each datasource has an attribute called ``dsname``, which may be used in the
kernel commandline to
:ref:`override datasource detection<kernel_datasource_override>` using a
case-insensitive match with the following mapping:


..
    generate the following map with the following one-liner:

    find cloudinit/sources -name 'DataSource*.py' \
       | xargs grep 'dsname =' \
       | awk -F '[/:"]' '{print $3 ", " $5}'


.. csv-table::
   :align: left
   :header: "Datasource", "dsname"

    DataSourceRbxCloud.py, RbxCloud
    DataSourceConfigDrive.py, ConfigDrive
    DataSourceNoCloud.py, NoCloud
    DataSourceVultr.py, Vultr
    DataSourceEc2.py, Ec2
    DataSourceOracle.py, Oracle
    DataSourceMAAS.py, MAAS
    DataSourceDigitalOcean.py, DigitalOcean
    DataSourceNone.py, None
    DataSourceSmartOS.py, Joyent
    DataSourceHetzner.py, Hetzner
    DataSourceLXD.py, LXD
    DataSourceOpenNebula.py, OpenNebula
    DataSourceAzure.py, Azure
    DataSourceGCE.py, GCE
    DataSourceScaleway.py, Scaleway
    DataSourceAltCloud.py, AltCloud
    DataSourceCloudSigma.py, CloudSigma
    DataSourceBigstep.py, Bigstep
    DataSourceIBMCloud.py, IBMCloud
    DataSourceOVF.py, OVF
    DataSourceUpCloud.py, UpCloud
    DataSourceOpenStack.py, OpenStack
    DataSourceVMware.py, VMware
    DataSourceCloudStack.py, CloudStack
    DataSourceExoscale.py, Exoscale
    DataSourceAliYun.py, AliYun
    DataSourceNWCS.py, NWCS
