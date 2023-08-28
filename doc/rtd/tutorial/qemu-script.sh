#!/bin/bash

TEMP_DIR=temp
IMAGE_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"

# setup
mkdir "$TEMP_DIR" && cd "$TEMP_DIR" || {
		echo "Error: Failed to create directory [$TEMP_DIR], aborting early"
        exit 1
}

wget "$IMAGE_URL"

# Create user-data, vendor-data, meta-data
cat << EOF > user-data
#cloud-config
password: password
chpasswd:
  expire: False
EOF

cat << EOF > meta-data
instance-id: someid/somehostname
local-hostname: jammy
EOF

touch vendor-data

# start ad hoc imds webserver
python3 -m http.server --directory . &

# start an instance of your image in a virtual machine
qemu-system-x86_64                                              \
    -net nic                                                    \
    -net user                                                   \
    -machine accel=kvm:tcg                                      \
    -cpu host                                                   \
    -m 512                                                      \
    -nographic                                                  \
    -hda jammy-server-cloudimg-amd64.img                        \
    -smbios type=1,serial=ds='nocloud;s=http://10.0.2.2:8000/'

echo -e "\nTo reuse the image and config files, start the python webserver and "
echo -e "virtual machine from $(pwd), which contains these files:\n$(ls -1)\n"

# end the python server on exit
trap "trap - SIGTERM && kill -- -$$" EXIT
