#!/usr/bin/sh

#############
# Save disk mappings to be restored during deploy
# Each line of the mapping file contains "<vgname> <pvid>" as output by the lspv command.
#############

CLOUD_DIR="/opt/freeware/etc/cloud"
PVID_VG_MAPPING_FILE="$CLOUD_DIR/pvid_to_vg_mappings"
if [ ! -d "$CLOUD_DIR" ]
then
    /usr/bin/mkdir -p $CLOUD_DIR
fi

LANG=C; /usr/sbin/lspv | /usr/bin/awk '{if ($2 != "none" && $3 != "rootvg") print $3 " " $2}' > $PVID_VG_MAPPING_FILE
