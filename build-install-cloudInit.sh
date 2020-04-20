#!/bin/bash

value=`cloud-init -v`
echo "The old version of cloud-init is $value."

#Get cloud-init
value=`rm -rf cloud-init`
echo "Next step: clone from https://git.launchpad.net/cloud-init"
git clone https://git.launchpad.net/cloud-init

#Build cloud-init
toxPath=$(pwd)/cloud-init
cd  $toxPath
echo "In the path: $(pwd)"
echo "Next step: tox."
value=`tox`
echo "Next step: /packages/bddeb."
value=`./packages/bddeb`

#Install the debian package
echo "Next step: remove old cloud-init."
value=`echo "123" | sudo -S dpkg --remove cloud-init`
value=`echo "123" | sudo -S dpkg --purge cloud-init`
echo "Next step: install new cloud-init."
value=`echo "123" | sudo -S dpkg -i cloud-init_all.deb`

value=`cloud-init -v`
echo "The new version of cloud-init is $value."

# Modify the cloud.cfg
value=`echo "123" | sudo -S sed -i '$a disable_vmware_customization: false' /etc/cloud/cloud.cfg`

wait
echo "Finished!"
echo "date: $(date)"
