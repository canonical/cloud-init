# cloud-init

![Unit Tests](https://github.com/canonical/cloud-init/actions/workflows/unit.yml/badge.svg?branch=main)
![Integration Tests](https://github.com/canonical/cloud-init/actions/workflows/integration.yml/badge.svg?branch=main)
![Documentation](https://github.com/canonical/cloud-init/actions/workflows/check_format.yml/badge.svg?branch=main)

Cloud-init is the *industry standard* multi-distribution method for
cross-platform cloud instance initialization. It is supported across all
major public cloud providers, provisioning systems for private cloud
infrastructure, and bare-metal installations.

Cloud instances are initialized from a disk image and instance data:

- Cloud metadata
- User data (optional)
- Vendor data (optional)

Cloud-init will identify the cloud it is running on during boot, read any
provided metadata from the cloud and initialize the system accordingly. This
may involve setting up network and storage devices to configuring SSH
access key and many other aspects of a system. Later on cloud-init will
also parse and process any optional user or vendor data that was passed to the
instance.

The majority of [clouds](https://docs.cloud-init.io/en/latest/reference/datasources.html#datasources_supported)
and [Linux / Unix OSes](https://docs.cloud-init.io/en/latest/reference/distros.html)
are supported by and ship with cloud-init. If your distribution or cloud is not
supported, please get in contact with that distribution and send them our way!

## Getting help

The [documentation](https://docs.cloud-init.io/en/latest/) is the first place
to look for help.

If a thorough search of the documentation does not resolve your issue, consider
the following:

- Ask a question in the [``#cloud-init`` channel on Matrix](https://matrix.to/#/#cloud-init:ubuntu.com)
- Look for announcements or engage in cloud-init discussions on [GitHub Discussions](https://github.com/canonical/cloud-init/discussions)
- Find a bug? [Report bugs on GitHub Issues](https://github.com/canonical/cloud-init/issues)

## To start developing cloud-init

Check out the [contributing](https://docs.cloud-init.io/en/latest/development/index.html)
guide.

## Daily package builds

Daily package builds are useful to try the latest upstream code for the latest
features or to verify bug fixes.

For Ubuntu, see the [Daily PPAs](https://code.launchpad.net/~cloud-init-dev/+archive/ubuntu/daily)

For CentOS, see the [COPR build repos](https://copr.fedorainfracloud.org/coprs/g/cloud-init/cloud-init-dev/)

## Build / packaging

To see reference build/packaging implementations, refer to [packages](packages).
