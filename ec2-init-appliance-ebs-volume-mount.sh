#!/bin/sh

if [ -n "$EBSMOUNT_DEBUG" ]
then
    do="echo"
    mktemp_args="-u"
else
    do=""
    mktemp_args=""
fi

if [ "$#" -lt 2 ]
then
	echo "Usage: $0 <EBS device> <path> [<path> [<path>...]]"
	exit 1
fi

ebs_volume_device="$1"
shift

canonicalise_dir() {
    dirname="$1"
    echo "${dirname}" | sed -e 's/[^a-zA-Z0-9]/_/g'
}

# The blkid call will detect whether there's already a filesystem on the EBS volume
if [ -n "$(blkid -p -o udev "${ebs_volume_device}")" ]
then
    $do mkfs.ext3 "${ebs_volume_device}"
fi

tmpdir="$(mktemp -d $mktemp_args --tmpdir=/var/run/ec2-init)"
$do mount ${ebs_volume_device} ${tmpdir}

for dir in "$@"
do
    ebsdir="${tmpdir}/$(canonicalise_dir "${dir}")"
    if [ ! -d "${ebsdir}" ]
    then
        # We bootstrap the storage with the existing data
        $do mkdir "${ebsdir}"
        $do cp -a ${dir} "${ebsdir}"
        $do chown --reference "${dir}" "${ebsdir}"
        $do chmod --reference "${dir}" "${ebsdir}"
    fi
    # Finally, we mount it on top of the old directory.
    $do mount --bind "${ebsdir}" "${dir}"
done
