# OCodeJS / Velclaw cloud-init bootstrap

This example is a **host-preparation baseline**, not an application deployment.
It is intended for a fresh Ubuntu 24.04 VPS image that already includes cloud-init.

## What it does

- Refreshes apt package metadata (does not run a distribution upgrade).
- Installs Git, curl, jq, CA certificates, Python and venv support.
- Creates /opt/ocodejs, /opt/velclaw and /var/lib/ocodejs.
- Does not create public users, open firewall ports, install SSH keys, expose services,
  change DNS, or deploy to Production.

## Check whether cloud-init is already installed

Most cloud VPS Ubuntu images include cloud-init. On the VPS, check:

~~~sh
cloud-init --version
cloud-init status --long
systemctl status cloud-init cloud-config cloud-final --no-pager
~~~

If the image does not include it, install it on a supported Ubuntu image:

~~~sh
sudo apt-get update
sudo apt-get install -y cloud-init
sudo systemctl enable cloud-init-local.service cloud-init.service cloud-config.service cloud-final.service
~~~

Do not install cloud-init blindly on an already provisioned machine: cloud-init is normally intended
to run during first boot and may have already consumed its user-data.

## Apply the user-data

1. Create a disposable Ubuntu 24.04 VPS or VM first.
2. In the provider's instance-creation screen, paste the contents of
   bootstrap.yaml into its cloud-init / user-data field.
3. Boot the instance, then verify:

~~~sh
sudo cloud-init status --wait
test -d /opt/ocodejs && test -d /opt/velclaw
git --version
python3 --version
~~~

For a local disposable Ubuntu VM, cloud-init can also validate the YAML before first boot
with the provider's NoCloud datasource. Do not test this against a production host.

## Next deployment stage

The actual OCodeJS / Velclaw service deployment still needs a target-specific manifest:
repository URLs, runtime (Docker Compose or systemd), service ports, health checks,
persistent-volume paths, and rollback strategy. Keep API keys, OAuth secrets, database
credentials and deployment tokens out of this repository and out of user-data committed
to Git. Inject secrets through the VPS provider's secret facility or a dedicated secret store.

No provider account, VPS, DNS record, firewall rule, or Production service is modified by
this example.
