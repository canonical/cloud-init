# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Disk Setup: Configure partitions and filesystems."""

import json
import logging
import os
import shlex
from pathlib import Path

from cloudinit import performance, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

LANG_C_ENV = {"LANG": "C"}
LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_disk_setup",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["disk_setup", "fs_setup"],
}


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """
    See doc/examples/cloud-config-disk-setup.txt for documentation on the
    format.
    """
    device_aliases = cfg.get("device_aliases", {})

    def alias_to_device(cand):
        name = device_aliases.get(cand)
        return cloud.device_name_to_device(name or cand) or name

    disk_setup = cfg.get("disk_setup")
    if isinstance(disk_setup, dict):
        update_disk_setup_devices(disk_setup, alias_to_device)
        LOG.debug("Partitioning disks: %s", str(disk_setup))
        for disk, definition in disk_setup.items():
            if not isinstance(definition, dict):
                LOG.warning("Invalid disk definition for %s", disk)
                continue

            try:
                with performance.Timed(
                    f"Creating partition on {disk}",
                ):
                    mkpart(disk, definition)
            except Exception as e:
                util.logexc(LOG, "Failed partitioning operation\n%s" % e)

    fs_setup = cfg.get("fs_setup")
    if isinstance(fs_setup, list):
        LOG.debug("setting up filesystems: %s", str(fs_setup))
        update_fs_setup_devices(fs_setup, alias_to_device)
        for definition in fs_setup:
            if not isinstance(definition, dict):
                LOG.warning("Invalid file system definition: %s", definition)
                continue

            try:
                with performance.Timed("Creating new filesystem"):
                    mkfs(definition)
            except Exception as e:
                util.logexc(LOG, "Failed during filesystem operation\n%s" % e)


def update_disk_setup_devices(disk_setup, tformer):
    # update 'disk_setup' dictionary anywhere were a device may occur
    # update it with the response from 'tformer'
    for origname in list(disk_setup):
        transformed = tformer(origname)
        if transformed is None or transformed == origname:
            continue
        if transformed in disk_setup:
            LOG.info(
                "Replacing %s in disk_setup for translation of %s",
                origname,
                transformed,
            )
            del disk_setup[transformed]

        disk_setup[transformed] = disk_setup[origname]
        if isinstance(disk_setup[transformed], dict):
            disk_setup[transformed]["_origname"] = origname
        del disk_setup[origname]
        LOG.debug(
            "updated disk_setup device entry '%s' to '%s'",
            origname,
            transformed,
        )


def update_fs_setup_devices(disk_setup, tformer):
    # update 'fs_setup' dictionary anywhere were a device may occur
    # update it with the response from 'tformer'
    for definition in disk_setup:
        if not isinstance(definition, dict):
            LOG.warning("entry in disk_setup not a dict: %s", definition)
            continue

        origname = definition.get("device")

        if origname is None:
            continue

        (dev, part) = util.expand_dotted_devname(origname)

        tformed = tformer(dev)
        if tformed is not None:
            dev = tformed
            LOG.debug(
                "%s is mapped to disk=%s part=%s", origname, tformed, part
            )
            definition["_origname"] = origname
            definition["device"] = tformed

        if part:
            # In origname with <dev>.N, N overrides 'partition' key.
            if "partition" in definition:
                LOG.warning(
                    "Partition '%s' from dotted device name '%s' "
                    "overrides 'partition' key in %s",
                    part,
                    origname,
                    definition,
                )
                definition["_partition"] = definition["partition"]
            definition["partition"] = part


def value_splitter(values, start=None):
    """
    Returns the key/value pairs of output sent as string
    like:  FOO='BAR' HOME='127.0.0.1'
    """
    _values = shlex.split(values)
    if start:
        _values = _values[start:]

    for key, value in [x.split("=") for x in _values]:
        yield key, value


def enumerate_disk(device, nodeps=False):
    """
    Enumerate the elements of a child device.

    Parameters:
        device: the kernel device name
        nodeps <BOOL>: don't enumerate children devices

    Return a dict describing the disk:
        type: the entry type, i.e disk or part
        fstype: the filesystem type, if it exists
        label: file system label, if it exists
        name: the device name, i.e. sda
    """

    lsblk_cmd = [
        "lsblk",
        "--pairs",
        "--output",
        "NAME,TYPE,FSTYPE,LABEL",
        device,
    ]

    if nodeps:
        lsblk_cmd.append("--nodeps")

    info = None
    try:
        info, _err = subp.subp(lsblk_cmd)
    except Exception as e:
        raise RuntimeError(
            "Failed during disk check for %s\n%s" % (device, e)
        ) from e

    parts = [x for x in (info.strip()).splitlines() if len(x.split()) > 0]

    for part in parts:
        d = {
            "name": None,
            "type": None,
            "fstype": None,
            "label": None,
        }

        for key, value in value_splitter(part):
            d[key.lower()] = value

        yield d


def device_type(device):
    """
    Return the device type of the device by calling lsblk.
    """

    for d in enumerate_disk(device, nodeps=True):
        if "type" in d:
            return d["type"].lower()
    return None


def is_device_valid(name, partition=False):
    """
    Check if the device is a valid device.
    """
    d_type = ""
    try:
        d_type = device_type(name)
    except Exception:
        LOG.warning("Query against device %s failed", name)
        return False

    if partition and d_type == "part":
        return True
    elif not partition and d_type == "disk":
        return True
    return False


def check_fs(device):
    """
    Check if the device has a filesystem on it

    Output of blkid is generally something like:
    /dev/sda: LABEL="Backup500G" UUID="..." TYPE="ext4"

    Return values are device, label, type, uuid
    """
    out, label, fs_type, uuid = None, None, None, None

    blkid_cmd = ["blkid", "-c", "/dev/null", device]
    try:
        out, _err = subp.subp(blkid_cmd, rcs=[0, 2])
    except Exception as e:
        raise RuntimeError(
            "Failed during disk check for %s\n%s" % (device, e)
        ) from e

    if out:
        if len(out.splitlines()) == 1:
            for key, value in value_splitter(out, start=1):
                if key.lower() == "label":
                    label = value
                elif key.lower() == "type":
                    fs_type = value
                elif key.lower() == "uuid":
                    uuid = value

    return label, fs_type, uuid


def is_filesystem(device):
    """
    Returns true if the device has a file system.
    """
    _, fs_type, _ = check_fs(device)
    return fs_type


def find_device_node(
    device,
    fs_type=None,
    label=None,
    valid_targets=None,
    label_match=True,
    replace_fs=None,
):
    """
    Find a device that is either matches the spec, or the first

    The return is value is (<device>, <bool>) where the device is the
    device to use and the bool is whether the device matches the
    fs_type and label.

    Note: This works with GPT partition tables!
    """
    # label of None is same as no label
    if label is None:
        label = ""

    if not valid_targets:
        valid_targets = ["disk", "part"]

    raw_device_used = False
    for d in enumerate_disk(device):

        if d["fstype"] == replace_fs and label_match is False:
            # We found a device where we want to replace the FS
            return ("/dev/%s" % d["name"], False)

        if d["fstype"] == fs_type and (
            (label_match and d["label"] == label) or not label_match
        ):
            # If we find a matching device, we return that
            return ("/dev/%s" % d["name"], True)

        if d["type"] in valid_targets:

            if d["type"] != "disk" or d["fstype"]:
                raw_device_used = True

            if d["type"] == "disk":
                # Skip the raw disk, its the default
                pass

            elif not d["fstype"]:
                return ("/dev/%s" % d["name"], False)

    if not raw_device_used:
        return (device, False)

    LOG.warning("Failed to find device during available device search.")
    return (None, False)


def is_disk_used(device):
    """
    Check if the device is currently used. Returns true if the device
    has either a file system or a partition entry
    is no filesystem found on the disk.
    """

    # If the child count is higher 1, then there are child nodes
    # such as partition or device mapper nodes
    if len(list(enumerate_disk(device))) > 1:
        return True

    # If we see a file system, then its used
    _, check_fstype, _ = check_fs(device)
    if check_fstype:
        return True

    return False


def get_hdd_size(device):
    try:
        size_in_bytes, _ = subp.subp(["blockdev", "--getsize64", device])
        sector_size, _ = subp.subp(["blockdev", "--getss", device])
    except Exception as e:
        raise RuntimeError("Failed to get %s size\n%s" % (device, e)) from e

    return int(size_in_bytes) / int(sector_size)


def check_partition_mbr_layout(device, layout):
    """
    Returns true if the partition layout matches the one on the disk

    Layout should be a list of values. At this time, this only
    verifies that the number of partitions and their labels is correct.
    """

    read_parttbl(device)

    prt_cmd = ["sfdisk", "-l", device]
    try:
        out, _err = subp.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise RuntimeError(
            "Error running partition command on %s\n%s" % (device, e)
        ) from e

    found_layout = []
    for line in out.splitlines():
        _line = line.split()
        if not _line:
            continue

        if device in _line[0]:
            # We don't understand extended partitions yet
            if _line[-1].lower() in ["extended", "empty"]:
                continue

            # Find the partition types
            type_label = None
            for x in sorted(range(1, len(_line)), reverse=True):
                if _line[x].isdigit() and _line[x] != "/":
                    type_label = _line[x]
                    break

            found_layout.append(type_label)
    return found_layout


# gdisk uses its own ids, convert them to standard GPT partition GUIDs.
# From gdisk sources:
#   grep " AddType" parttypes.cc |
#    sed -e 's,AddType(,,' -e 's,"\,.*$,"\,,' -e 's,0x,",' -e 's,\,,":,' |
#    tr "[a-z]" "[A-Z]"
sgdisk_to_gpt_id = {
    "0000": "00000000-0000-0000-0000-000000000000",
    "0100": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "0400": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "0600": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "0700": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "0701": "558D43C5-A1AC-43C0-AAC8-D1472B2923D1",
    "0702": "90B6FF38-B98F-4358-A21F-48F35B4A8AD3",
    "0B00": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "0C00": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "0C01": "E3C9E316-0B5C-4DB8-817D-F92DF00215AE",
    "0E00": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1100": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1400": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1600": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1700": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1B00": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1C00": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "1E00": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
    "2700": "DE94BBA4-06D1-4D40-A16A-BFD50179D6AC",
    "3000": "7412F7D5-A156-4B13-81DC-867174929325",
    "3001": "D4E6E2CD-4469-46F3-B5CB-1BFF57AFC149",
    "3900": "C91818F9-8025-47AF-89D2-F030D7000C2C",
    "4100": "9E1A2D38-C612-4316-AA26-8B49521E5A8B",
    "4200": "AF9B60A0-1431-4F62-BC68-3311714A69AD",
    "4201": "5808C8AA-7E8F-42E0-85D2-E1E90434CFB3",
    "4202": "E75CAF8F-F680-4CEE-AFA3-B001E56EFC2D",
    "7501": "37AFFC90-EF7D-4E96-91C3-2D7AE055B174",
    "7F00": "FE3A2A5D-4F32-41A7-B725-ACCC3285A309",
    "7F01": "3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC",
    "7F02": "2E0A753D-9E48-43B0-8337-B15192CB1B5E",
    "7F03": "CAB6E88E-ABF3-4102-A07A-D4BB9BE3C1D3",
    "7F04": "09845860-705F-4BB5-B16C-8A8A099CAF52",
    "7F05": "3F0F8318-F146-4E6B-8222-C28C8F02E0D5",
    "8200": "0657FD6D-A4AB-43C4-84E5-0933C84B4F4F",
    "8300": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
    "8301": "8DA63339-0007-60C0-C436-083AC8230908",
    "8302": "933AC7E1-2EB4-4F13-B844-0E14E2AEF915",
    "8303": "44479540-F297-41B2-9AF7-D131D5F0458A",
    "8304": "4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709",
    "8305": "B921B045-1DF0-41C3-AF44-4C6F280D3FAE",
    "8306": "3B8F8425-20E0-4F3B-907F-1A25A76F98E8",
    "8307": "69DAD710-2CE4-4E3C-B16C-21A1D49ABED3",
    "8308": "7FFEC5C9-2D00-49B7-8941-3EA10A5586B7",
    "8309": "CA7D7CCB-63ED-4C53-861C-1742536059CC",
    "830A": "993D8D3D-F80E-4225-855A-9DAF8ED7EA97",
    "830B": "D13C5D3B-B5D1-422A-B29F-9454FDC89D76",
    "830C": "2C7357ED-EBD2-46D9-AEC1-23D437EC2BF5",
    "830D": "7386CDF2-203C-47A9-A498-F2ECCE45A2D6",
    "830E": "DF3300CE-D69F-4C92-978C-9BFB0F38D820",
    "830F": "86ED10D5-B607-45BB-8957-D350F23D0571",
    "8310": "4D21B016-B534-45C2-A9FB-5C16E091FD2D",
    "8311": "7EC6F557-3BC5-4ACA-B293-16EF5DF639D1",
    "8312": "773F91EF-66D4-49B5-BD83-D683BF40AD16",
    "8313": "75250D76-8CC6-458E-BD66-BD47CC81A812",
    "8314": "8484680C-9521-48C6-9C11-B0720656F69E",
    "8315": "7D0359A3-02B3-4F0A-865C-654403E70625",
    "8316": "B0E01050-EE5F-4390-949A-9101B17104E9",
    "8317": "4301D2A6-4E3B-4B2A-BB94-9E0B2C4225EA",
    "8318": "8F461B0D-14EE-4E81-9AA9-049B6FB97ABD",
    "8319": "77FF5F63-E7B6-4633-ACF4-1565B864C0E6",
    "831A": "C215D751-7BCD-4649-BE90-6627490A4C05",
    "831B": "6E11A4E7-FBCA-4DED-B9E9-E1A512BB664E",
    "831C": "6A491E03-3BE7-4545-8E38-83320E0EA880",
    "831D": "6523F8AE-3EB1-4E2A-A05A-18B695AE656F",
    "831E": "D27F46ED-2919-4CB8-BD25-9531F3C16534",
    "831F": "77055800-792C-4F94-B39A-98C91B762BB6",
    "8320": "E9434544-6E2C-47CC-BAE2-12D6DEAFB44C",
    "8321": "D113AF76-80EF-41B4-BDB6-0CFF4D3D4A25",
    "8322": "37C58C8A-D913-4156-A25F-48B1B64E07F0",
    "8323": "700BDA43-7A34-4507-B179-EEB93D7A7CA3",
    "8324": "1AACDB3B-5444-4138-BD9E-E5C2239B2346",
    "8325": "1DE3F1EF-FA98-47B5-8DCD-4A860A654D78",
    "8326": "912ADE1D-A839-4913-8964-A10EEE08FBD2",
    "8327": "C31C45E6-3F39-412E-80FB-4809C4980599",
    "8328": "60D5A7FE-8E7D-435C-B714-3DD8162144E1",
    "8329": "72EC70A6-CF74-40E6-BD49-4BDA08E8F224",
    "832A": "08A7ACEA-624C-4A20-91E8-6E0FA67D23F9",
    "832B": "5EEAD9A9-FE09-4A1E-A1D7-520D00531306",
    "832C": "C50CDD70-3862-4CC3-90E1-809A8C93EE2C",
    "832D": "E18CF08C-33EC-4C0D-8246-C6C6FB3DA024",
    "832E": "7978A683-6316-4922-BBEE-38BFF5A2FECC",
    "832F": "E611C702-575C-4CBE-9A46-434FA0BF7E3F",
    "8330": "773B2ABC-2A99-4398-8BF5-03BAAC40D02B",
    "8331": "57E13958-7331-4365-8E6E-35EEEE17C61B",
    "8332": "0F4868E9-9952-4706-979F-3ED3A473E947",
    "8333": "C97C1F32-BA06-40B4-9F22-236061B08AA8",
    "8334": "DC4A4480-6917-4262-A4EC-DB9384949F25",
    "8335": "7D14FEC5-CC71-415D-9D6C-06BF0B3C3EAF",
    "8336": "2C9739E2-F068-46B3-9FD0-01C5A9AFBCCA",
    "8337": "15BB03AF-77E7-4D4A-B12B-C0D084F7491C",
    "8338": "B933FB22-5C3F-4F91-AF90-E2BB0FA50702",
    "8339": "BEAEC34B-8442-439B-A40B-984381ED097D",
    "833A": "CD0F869B-D0FB-4CA0-B141-9EA87CC78D66",
    "833B": "8A4F5770-50AA-4ED3-874A-99B710DB6FEA",
    "833C": "55497029-C7C1-44CC-AA39-815ED1558630",
    "833D": "FC56D9E9-E6E5-4C06-BE32-E74407CE09A5",
    "833E": "24B2D975-0F97-4521-AFA1-CD531E421B8D",
    "833F": "F3393B22-E9AF-4613-A948-9D3BFBD0C535",
    "8340": "7A430799-F711-4C7E-8E5B-1D685BD48607",
    "8341": "579536F8-6A33-4055-A95A-DF2D5E2C42A8",
    "8342": "D7D150D2-2A04-4A33-8F12-16651205FF7B",
    "8343": "16B417F8-3E06-4F57-8DD2-9B5232F41AA6",
    "8344": "D212A430-FBC5-49F9-A983-A7FEEF2B8D0E",
    "8345": "906BD944-4589-4AAE-A4E4-DD983917446A",
    "8346": "9225A9A3-3C19-4D89-B4F6-EEFF88F17631",
    "8347": "98CFE649-1588-46DC-B2F0-ADD147424925",
    "8348": "AE0253BE-1167-4007-AC68-43926C14C5DE",
    "8349": "B6ED5582-440B-4209-B8DA-5FF7C419EA3D",
    "834A": "7AC63B47-B25C-463B-8DF8-B4A94E6C90E1",
    "834B": "B325BFBE-C7BE-4AB8-8357-139E652D2F6B",
    "834C": "966061EC-28E4-4B2E-B4A5-1F0A825A1D84",
    "834D": "8CCE0D25-C0D0-4A44-BD87-46331BF1DF67",
    "834E": "FCA0598C-D880-4591-8C16-4EDA05C7347C",
    "834F": "F46B2C26-59AE-48F0-9106-C50ED47F673D",
    "8350": "6E5A1BC8-D223-49B7-BCA8-37A5FCCEB996",
    "8351": "81CF9D90-7458-4DF4-8DCF-C8A3A404F09B",
    "8352": "46B98D8D-B55C-4E8F-AAB3-37FCA7F80752",
    "8353": "3C3D61FE-B5F3-414D-BB71-8739A694A4EF",
    "8354": "5843D618-EC37-48D7-9F12-CEA8E08768B2",
    "8355": "EE2B9983-21E8-4153-86D9-B6901A54D1CE",
    "8356": "BDB528A5-A259-475F-A87D-DA53FA736A07",
    "8357": "DF765D00-270E-49E5-BC75-F47BB2118B09",
    "8358": "CB1EE4E3-8CD0-4136-A0A4-AA61A32E8730",
    "8359": "8F1056BE-9B05-47C4-81D6-BE53128E5B54",
    "835A": "B663C618-E7BC-4D6D-90AA-11B756BB1797",
    "835B": "31741CC4-1A2A-4111-A581-E00B447D2D06",
    "835C": "2FB4BF56-07FA-42DA-8132-6B139F2026AE",
    "835D": "D46495B7-A053-414F-80F7-700C99921EF8",
    "835E": "143A70BA-CBD3-4F06-919F-6C05683A78BC",
    "835F": "42B0455F-EB11-491D-98D3-56145BA9D037",
    "8360": "6DB69DE6-29F4-4758-A7A5-962190F00CE3",
    "8361": "E98B36EE-32BA-4882-9B12-0CE14655F46A",
    "8362": "5AFB67EB-ECC8-4F85-AE8E-AC1E7C50E7D0",
    "8363": "BBA210A2-9C5D-45EE-9E87-FF2CCBD002D0",
    "8364": "43CE94D4-0F3D-4999-8250-B9DEAFD98E6E",
    "8365": "C919CC1F-4456-4EFF-918C-F75E94525CA5",
    "8366": "904E58EF-5C65-4A31-9C57-6AF5FC7C5DE7",
    "8367": "15DE6170-65D3-431C-916E-B0DCD8393F25",
    "8368": "D4A236E7-E873-4C07-BF1D-BF6CF7F1C3C6",
    "8369": "F5E2C20C-45B2-4FFA-BCE9-2A60737E1AAF",
    "836A": "1B31B5AA-ADD9-463A-B2ED-BD467FC857E7",
    "836B": "3A112A75-8729-4380-B4CF-764D79934448",
    "836C": "EFE0F087-EA8D-4469-821A-4C2A96A8386A",
    "836D": "3482388E-4254-435A-A241-766A065F9960",
    "836E": "C80187A5-73A3-491A-901A-017C3FA953E9",
    "836F": "B3671439-97B0-4A53-90F7-2D5A8F3AD47B",
    "8370": "41092B05-9FC8-4523-994F-2DEF0408B176",
    "8371": "5996FC05-109C-48DE-808B-23FA0830B676",
    "8372": "5C6E1C76-076A-457A-A0FE-F3B4CD21CE6E",
    "8373": "94F9A9A1-9971-427A-A400-50CB297F0F35",
    "8374": "D7FF812F-37D1-4902-A810-D76BA57B975A",
    "8375": "C23CE4FF-44BD-4B00-B2D4-B41B3419E02A",
    "8376": "8DE58BC2-2A43-460D-B14E-A76E4A17B47F",
    "8377": "B024F315-D330-444C-8461-44BBDE524E99",
    "8378": "97AE158D-F216-497B-8057-F7F905770F54",
    "8379": "05816CE2-DD40-4AC6-A61D-37D32DC1BA7D",
    "837A": "3E23CA0B-A4BC-4B4E-8087-5AB6A26AA8A9",
    "837B": "F2C2C7EE-ADCC-4351-B5C6-EE9816B66E16",
    "837C": "450DD7D1-3224-45EC-9CF2-A43A346D71EE",
    "837D": "C8BFBD1E-268E-4521-8BBA-BF314C399557",
    "837E": "0B888863-D7F8-4D9E-9766-239FCE4D58AF",
    "837F": "7007891D-D371-4A80-86A4-5CB875B9302E",
    "8380": "C3836A13-3137-45BA-B583-B16C50FE5EB4",
    "8381": "D2F9000A-7A18-453F-B5CD-4D32F77A7B32",
    "8382": "17440E4F-A8D0-467F-A46E-3912AE6EF2C5",
    "8383": "3F324816-667B-46AE-86EE-9B0C0C6C11B4",
    "8384": "4EDE75E2-6CCC-4CC8-B9C7-70334B087510",
    "8385": "E7BB33FB-06CF-4E81-8273-E543B413E2E2",
    "8386": "974A71C0-DE41-43C3-BE5D-5C5CCD1AD2C0",
    "8400": "D3BFE2DE-3DAF-11DF-BA40-E3A556D89593",
    "8401": "7C5222BD-8F5D-4087-9C00-BF9843C7B58C",
    "8500": "5DFBF5F4-2848-4BAC-AA5E-0D9A20B745A6",
    "8501": "3884DD41-8582-4404-B9A8-E9B84F2DF50E",
    "8502": "C95DC21A-DF0E-4340-8D7B-26CBFA9A03E0",
    "8503": "BE9067B9-EA49-4F15-B4F6-F36F8C9E1818",
    "8E00": "E6D6D379-F507-44C2-A23C-238F2A3DF928",
    "A000": "2568845D-2332-4675-BC39-8FA5A4748D15",
    "A001": "114EAFFE-1552-4022-B26E-9B053604CF84",
    "A002": "49A4D17F-93A3-45C1-A0DE-F50B2EBE2599",
    "A003": "4177C722-9E92-4AAB-8644-43502BFD5506",
    "A004": "EF32A33B-A409-486C-9141-9FFB711F6266",
    "A005": "20AC26BE-20B7-11E3-84C5-6CFDB94711E9",
    "A006": "38F428E6-D326-425D-9140-6E0EA133647C",
    "A007": "A893EF21-E428-470A-9E55-0668FD91A2D9",
    "A008": "DC76DDA9-5AC1-491C-AF42-A82591580C0D",
    "A009": "EBC597D0-2053-4B15-8B64-E0AAC75F4DB1",
    "A00A": "8F68CC74-C5E5-48DA-BE91-A0C8C15E9C80",
    "A00B": "767941D0-2085-11E3-AD3B-6CFDB94711E9",
    "A00C": "AC6D7924-EB71-4DF8-B48D-E267B27148FF",
    "A00D": "C5A0AEEC-13EA-11E5-A1B1-001E67CA0C3C",
    "A00E": "BD59408B-4514-490D-BF12-9878D963F378",
    "A00F": "9FDAA6EF-4B3F-40D2-BA8D-BFF16BFB887B",
    "A010": "19A710A2-B3CA-11E4-B026-10604B889DCF",
    "A011": "193D1EA4-B3CA-11E4-B075-10604B889DCF",
    "A012": "DEA0BA2C-CBDD-4805-B4F9-F428251C3E98",
    "A013": "8C6B52AD-8A9E-4398-AD09-AE916E53AE2D",
    "A014": "05E044DF-92F1-4325-B69E-374A82E97D6E",
    "A015": "400FFDCD-22E0-47E7-9A23-F16ED9382388",
    "A016": "A053AA7F-40B8-4B1C-BA08-2F68AC71A4F4",
    "A017": "E1A6A689-0C8D-4CC6-B4E8-55A4320FBD8A",
    "A018": "098DF793-D712-413D-9D4E-89D711772228",
    "A019": "D4E0D938-B7FA-48C1-9D21-BC5ED5C4B203",
    "A01A": "20A0C19C-286A-42FA-9CE7-F64C3226A794",
    "A01B": "A19F205F-CCD8-4B6D-8F1E-2D9BC24CFFB1",
    "A01C": "66C9B323-F7FC-48B6-BF96-6F32E335A428",
    "A01D": "303E6AC3-AF15-4C54-9E9B-D9A8FBECF401",
    "A01E": "C00EEF24-7709-43D6-9799-DD2B411E7A3C",
    "A01F": "82ACC91F-357C-4A68-9C8F-689E1B1A23A1",
    "A020": "E2802D54-0545-E8A1-A1E8-C7A3E245ACD4",
    "A021": "65ADDCF4-0C5C-4D9A-AC2D-D90B5CBFCD03",
    "A022": "E6E98DA2-E22A-4D12-AB33-169E7DEAA507",
    "A023": "ED9E8101-05FA-46B7-82AA-8D58770D200B",
    "A024": "11406F35-1173-4869-807B-27DF71802812",
    "A025": "9D72D4E4-9958-42DA-AC26-BEA7A90B0434",
    "A026": "6C95E238-E343-4BA8-B489-8681ED22AD0B",
    "A027": "EBBEADAF-22C9-E33B-8F5D-0E81686A68CB",
    "A028": "0A288B1F-22C9-E33B-8F5D-0E81686A68CB",
    "A029": "57B90A16-22C9-E33B-8F5D-0E81686A68CB",
    "A02A": "638FF8E2-22C9-E33B-8F5D-0E81686A68CB",
    "A02B": "2013373E-1AC4-4131-BFD8-B6A7AC638772",
    "A02C": "2C86E742-745E-4FDD-BFD8-B6A7AC638772",
    "A02D": "DE7D4029-0F5B-41C8-AE7E-F6C023A02B33",
    "A02E": "323EF595-AF7A-4AFA-8060-97BE72841BB9",
    "A02F": "45864011-CF89-46E6-A445-85262E065604",
    "A030": "8ED8AE95-597F-4C8A-A5BD-A7FF8E4DFAA9",
    "A031": "DF24E5ED-8C96-4B86-B00B-79667DC6DE11",
    "A032": "7C29D3AD-78B9-452E-9DEB-D098D542F092",
    "A033": "379D107E-229E-499D-AD4F-61F5BCF87BD4",
    "A034": "0DEA65E5-A676-4CDF-823C-77568B577ED5",
    "A035": "4627AE27-CFEF-48A1-88FE-99C3509ADE26",
    "A036": "20117F86-E985-4357-B9EE-374BC1D8487D",
    "A037": "86A7CB80-84E1-408C-99AB-694F1A410FC7",
    "A038": "97D7B011-54DA-4835-B3C4-917AD6E73D74",
    "A039": "5594C694-C871-4B5F-90B1-690A6F68E0F7",
    "A03A": "1B81E7E6-F50D-419B-A739-2AEEF8DA3335",
    "A03B": "98523EC6-90FE-4C67-B50A-0FC59ED6F56D",
    "A03C": "2644BCC0-F36A-4792-9533-1738BED53EE3",
    "A03D": "DD7C91E9-38C9-45C5-8A12-4A80F7E14057",
    "A03E": "7696D5B6-43FD-4664-A228-C563C4A1E8CC",
    "A03F": "0D802D54-058D-4A20-AD2D-C7A362CEACD4",
    "A040": "10A0C19C-516A-5444-5CE3-664C3226A794",
    "A200": "734E5AFE-F61A-11E6-BC64-92361F002671",
    "A500": "516E7CB4-6ECF-11D6-8FF8-00022D09712B",
    "A501": "83BD6B9D-7F41-11DC-BE0B-001560B84F0F",
    "A502": "516E7CB5-6ECF-11D6-8FF8-00022D09712B",
    "A503": "516E7CB6-6ECF-11D6-8FF8-00022D09712B",
    "A504": "516E7CBA-6ECF-11D6-8FF8-00022D09712B",
    "A505": "516E7CB8-6ECF-11D6-8FF8-00022D09712B",
    "A506": "74BA7DD9-A689-11E1-BD04-00E081286ACF",
    "A580": "85D5E45A-237C-11E1-B4B3-E89A8F7FC3A7",
    "A581": "85D5E45E-237C-11E1-B4B3-E89A8F7FC3A7",
    "A582": "85D5E45B-237C-11E1-B4B3-E89A8F7FC3A7",
    "A583": "0394EF8B-237E-11E1-B4B3-E89A8F7FC3A7",
    "A584": "85D5E45D-237C-11E1-B4B3-E89A8F7FC3A7",
    "A585": "85D5E45C-237C-11E1-B4B3-E89A8F7FC3A7",
    "A600": "824CC7A0-36A8-11E3-890A-952519AD3F61",
    "A800": "55465300-0000-11AA-AA11-00306543ECAC",
    "A900": "516E7CB4-6ECF-11D6-8FF8-00022D09712B",
    "A901": "49F48D32-B10E-11DC-B99B-0019D1879648",
    "A902": "49F48D5A-B10E-11DC-B99B-0019D1879648",
    "A903": "49F48D82-B10E-11DC-B99B-0019D1879648",
    "A904": "2DB519C4-B10F-11DC-B99B-0019D1879648",
    "A905": "2DB519EC-B10F-11DC-B99B-0019D1879648",
    "A906": "49F48DAA-B10E-11DC-B99B-0019D1879648",
    "AB00": "426F6F74-0000-11AA-AA11-00306543ECAC",
    "AF00": "48465300-0000-11AA-AA11-00306543ECAC",
    "AF01": "52414944-0000-11AA-AA11-00306543ECAC",
    "AF02": "52414944-5F4F-11AA-AA11-00306543ECAC",
    "AF03": "4C616265-6C00-11AA-AA11-00306543ECAC",
    "AF04": "5265636F-7665-11AA-AA11-00306543ECAC",
    "AF05": "53746F72-6167-11AA-AA11-00306543ECAC",
    "AF06": "B6FA30DA-92D2-4A9A-96F1-871EC6486200",
    "AF07": "2E313465-19B9-463F-8126-8A7993773801",
    "AF08": "FA709C7E-65B1-4593-BFD5-E71D61DE9B02",
    "AF09": "BBBA6DF5-F46F-4A89-8F59-8765B2727503",
    "AF0A": "7C3457EF-0000-11AA-AA11-00306543ECAC",
    "AF0B": "69646961-6700-11AA-AA11-00306543ECAC",
    "AF0C": "52637672-7900-11AA-AA11-00306543ECAC",
    "B000": "3DE21764-95BD-54BD-A5C3-4ABE786F38A8",
    "B300": "CEF5A9AD-73BC-4601-89F3-CDEEEEE321A1",
    "BB00": "4778ED65-BF42-45FA-9C5B-287A1DC4AAB1",
    "BC00": "0311FC50-01CA-4725-AD77-9ADBB20ACE98",
    "BE00": "6A82CB45-1DD2-11B2-99A6-080020736631",
    "BF00": "6A85CF4D-1DD2-11B2-99A6-080020736631",
    "BF01": "6A898CC3-1DD2-11B2-99A6-080020736631",
    "BF02": "6A87C46F-1DD2-11B2-99A6-080020736631",
    "BF03": "6A8B642B-1DD2-11B2-99A6-080020736631",
    "BF04": "6A8EF2E9-1DD2-11B2-99A6-080020736631",
    "BF05": "6A90BA39-1DD2-11B2-99A6-080020736631",
    "BF06": "6A9283A5-1DD2-11B2-99A6-080020736631",
    "BF07": "6A945A3B-1DD2-11B2-99A6-080020736631",
    "BF08": "6A9630D1-1DD2-11B2-99A6-080020736631",
    "BF09": "6A980767-1DD2-11B2-99A6-080020736631",
    "BF0A": "6A96237F-1DD2-11B2-99A6-080020736631",
    "BF0B": "6A8D2AC7-1DD2-11B2-99A6-080020736631",
    "C001": "75894C1E-3AEB-11D3-B7C1-7B03A0000000",
    "C002": "E2A1E728-32E3-11D6-A682-7B03A0000000",
    "E100": "7412F7D5-A156-4B13-81DC-867174929325",
    "E101": "D4E6E2CD-4469-46F3-B5CB-1BFF57AFC149",
    "E900": "8C8F8EFF-AC95-4770-814A-21994F2DBC8F",
    "EA00": "BC13C2FF-59E6-4262-A352-B275FD6F7172",
    "EB00": "42465331-3BA3-10F1-802A-4861696B7521",
    "ED00": "F4019732-066E-4E12-8273-346C5641494F",
    "ED01": "BFBFAFE7-A34F-448A-9A5B-6213EB736C22",
    "EF00": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
    "EF01": "024DEE41-33E7-11D3-9D69-0008C781F39F",
    "EF02": "21686148-6449-6E6F-744E-656564454649",
    "F100": "FE8A2634-5E2E-46BA-99E3-3A192091A350",
    "F101": "D9FD4535-106C-4CEC-8D37-DFC020CA87CB",
    "F102": "A409E16B-78AA-4ACC-995C-302352621A41",
    "F103": "F95D940E-CABA-4578-9B93-BB6C90F29D3E",
    "F104": "10B8DBAA-D2BF-42A9-98C6-A7C5DB3701E7",
    "F105": "49FD7CB8-DF15-4E73-B9D9-992070127F0F",
    "F106": "421A8BFC-85D9-4D85-ACDA-B64EEC0133E9",
    "F107": "9B37FFF6-2E58-466A-983A-F7926D0B04E0",
    "F108": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
    "F109": "606B000B-B7C7-4653-A7D5-B737332C899D",
    "F10A": "08185F0C-892D-428A-A789-DBEEC8F55E6A",
    "F10B": "48435546-4953-2041-494E-5354414C4C52",
    "F10C": "2967380E-134C-4CBB-B6DA-17E7CE1CA45D",
    "F10D": "41D0E340-57E3-954E-8C1E-17ECAC44CFF5",
    "F10E": "DE30CC86-1F4A-4A31-93C4-66F147D33E05",
    "F10F": "23CC04DF-C278-4CE7-8471-897D1A4BCDF7",
    "F110": "A0E5CF57-2DEF-46BE-A80C-A2067C37CD49",
    "F111": "4E5E989E-4C86-11E8-A15B-480FCF35F8E6",
    "F112": "5A3A90BE-4C86-11E8-A15B-480FCF35F8E6",
    "F113": "5ECE94FE-4C86-11E8-A15B-480FCF35F8E6",
    "F114": "8B94D043-30BE-4871-9DFA-D69556E8C1F3",
    "F115": "A13B4D9A-EC5F-11E8-97D8-6C3BE52705BF",
    "F116": "A288ABF2-EC5F-11E8-97D8-6C3BE52705BF",
    "F117": "6A2460C3-CD11-4E8B-80A8-12CCE268ED0A",
    "F118": "1D75395D-F2C6-476B-A8B7-45CC1C97B476",
    "F119": "900B0FC5-90CD-4D4F-84F9-9F8ED579DB88",
    "F11A": "B2B2E8D1-7C10-4EBC-A2D0-4614568260AD",
    "F800": "4FBD7E29-9D25-41B8-AFD0-062C0CEFF05D",
    "F801": "4FBD7E29-9D25-41B8-AFD0-5EC00CEFF05D",
    "F802": "45B0969E-9B03-4F30-B4C6-B4B80CEFF106",
    "F803": "45B0969E-9B03-4F30-B4C6-5EC00CEFF106",
    "F804": "89C57F98-2FE5-4DC0-89C1-F3AD0CEFF2BE",
    "F805": "89C57F98-2FE5-4DC0-89C1-5EC00CEFF2BE",
    "F806": "CAFECAFE-9B03-4F30-B4C6-B4B80CEFF106",
    "F807": "30CD0809-C2B2-499C-8879-2D6B78529876",
    "F808": "5CE17FCE-4087-4169-B7FF-056CC58473F9",
    "F809": "FB3AABF9-D25F-47CC-BF5E-721D1816496B",
    "F80A": "4FBD7E29-8AE0-4982-BF9D-5A8D867AF560",
    "F80B": "45B0969E-8AE0-4982-BF9D-5A8D867AF560",
    "F80C": "CAFECAFE-8AE0-4982-BF9D-5A8D867AF560",
    "F80D": "7F4A666A-16F3-47A2-8445-152EF4D03F6C",
    "F80E": "EC6D6385-E346-45DC-BE91-DA2A7C8B3261",
    "F80F": "01B41E1B-002A-453C-9F17-88793989FF8F",
    "F810": "CAFECAFE-9B03-4F30-B4C6-5EC00CEFF106",
    "F811": "93B0052D-02D9-4D8A-A43B-33A3EE4DFBC3",
    "F812": "306E8683-4FE2-4330-B7C0-00A917C16966",
    "F813": "45B0969E-9B03-4F30-B4C6-35865CEFF106",
    "F814": "CAFECAFE-9B03-4F30-B4C6-35865CEFF106",
    "F815": "166418DA-C469-4022-ADF4-B30AFD37F176",
    "F816": "86A32090-3647-40B9-BBBD-38D8C573AA86",
    "F817": "4FBD7E29-9D25-41B8-AFD0-35865CEFF05D",
    "FB00": "AA31E02A-400F-11DB-9590-000C2911D1B8",
    "FB01": "9198EFFC-31C0-11DB-8F78-000C2911D1B8",
    "FC00": "9D275380-40AD-11DB-BF97-000C2911D1B8",
    "FD00": "A19D880F-05FC-4D3B-A006-743F0F84911E",
}


def check_partition_gpt_layout_sgdisk(device, layout):
    prt_cmd = ["sgdisk", "-p", device]
    try:
        out, _err = subp.subp(prt_cmd, update_env=LANG_C_ENV)
    except Exception as e:
        raise RuntimeError(
            "Error running partition command on %s\n%s" % (device, e)
        ) from e

    out_lines = iter(out.splitlines())
    # Skip header.  Output looks like:
    # ***************************************************************
    # Found invalid GPT and valid MBR; converting MBR to GPT format
    # in memory.
    # ***************************************************************
    #
    # Disk /dev/vdb: 83886080 sectors, 40.0 GiB
    # Logical sector size: 512 bytes
    # Disk identifier (GUID): 8A7F11AD-3953-491B-8051-077E01C8E9A7
    # Partition table holds up to 128 entries
    # First usable sector is 34, last usable sector is 83886046
    # Partitions will be aligned on 2048-sector boundaries
    # Total free space is 83476413 sectors (39.8 GiB)
    #
    # Number Start (sector) End (sector) Size       Code  Name
    # 1      2048           206847       100.0 MiB  0700  Microsoft basic data
    for line in out_lines:
        if line.strip().startswith("Number"):
            break

    return [line.strip().split()[5] for line in out_lines]


def check_partition_gpt_layout_sfdisk(device, layout):
    # Use sfdisk's JSON output for reliability
    prt_cmd = ["sfdisk", "-l", "-J", device]
    _err = None
    try:
        out, _err = subp.subp(prt_cmd, update_env=LANG_C_ENV, rcs=[0, 1])
        # Check if the error indicates no partition table exists
        if _err and "does not contain a recognized partition table" in _err:
            # Device has no partition table yet, return empty list
            return []
        # Try to parse JSON output
        ptable = json.loads(out)["partitiontable"]
        if "partitions" in ptable:
            partitions = ptable["partitions"]
        else:
            partitions = []

    except Exception as e:
        raise RuntimeError(
            "Error running partition command on %s\n%s" % (device, e)
        ) from e

    return [p["type"] for p in partitions]


def check_partition_gpt_layout(device, layout):
    if subp.which("sgdisk"):
        return check_partition_gpt_layout_sgdisk(device, layout)
    return check_partition_gpt_layout_sfdisk(device, layout)


def partition_type_matches(found_type, expected_type):
    """
    Check if the observed partition type matches the expectation which
    can either be a two digit legacy code, a four digit 'sgdisk' type or
    a GPT UUID.
    """
    found_type = str(found_type).upper()
    if len(found_type) not in [2, 4, 36]:
        raise RuntimeError("Unknown partition type found: %s" % found_type)

    expected_type = str(expected_type).upper()
    if len(expected_type) not in [2, 4, 36]:
        raise RuntimeError("Unknown partition type specified: %s" % found_type)

    # Promote 2-digit codes to 4-digit
    if len(found_type) == 2:
        found_type += "00"
    if len(expected_type) == 2:
        expected_type += "00"

    # Check if four digit codes match
    if len(found_type) == len(expected_type):
        return found_type == expected_type

    # Promote four digit codes to GPT partition GUIDs
    if len(found_type) == 4:
        if found_type in sgdisk_to_gpt_id:
            found_type = sgdisk_to_gpt_id[found_type]
        else:
            raise RuntimeError(
                "Cannot find GPT GUID for found type %s" % found_type
            )
    if len(expected_type) == 4:
        if expected_type in sgdisk_to_gpt_id:
            expected_type = sgdisk_to_gpt_id[expected_type]
        else:
            raise RuntimeError(
                "Cannot find GPT GUID for expected type %s" % found_type
            )

    # Both codes are GPT UUIDs now
    return found_type == expected_type


def check_partition_layout(table_type, device, layout):
    """
    See if the partition lay out matches.

    This is future a future proofing function. In order
    to add support for other disk layout schemes, add a
    function called check_partition_%s_layout
    """
    if "gpt" == table_type:
        found_layout = check_partition_gpt_layout(device, layout)
    elif "mbr" == table_type:
        found_layout = check_partition_mbr_layout(device, layout)
    else:
        raise RuntimeError("Unable to determine table type")

    LOG.debug(
        "called check_partition_%s_layout(%s, %s), returned: %s",
        table_type,
        device,
        layout,
        found_layout,
    )
    if isinstance(layout, bool):
        # if we are using auto partitioning, or "True" be happy
        # if a single partition exists.
        if layout and len(found_layout) >= 1:
            return True
        return False

    elif len(found_layout) == len(layout):
        # This just makes sure that the number of requested
        # partitions and the type labels are right
        layout_types = [
            str(x[1]) if isinstance(x, (tuple, list)) else None for x in layout
        ]
        LOG.debug(
            "Layout types=%s. Found types=%s", layout_types, found_layout
        )
        for itype, ftype in zip(layout_types, found_layout):
            if itype is not None and not partition_type_matches(itype, ftype):
                return False
        return True

    return False


def get_partition_mbr_layout(size, layout):
    """
    Calculate the layout of the partition table. Partition sizes
    are defined as percentage values or a tuple of percentage and
    partition type.

    For example:
        [ 33, [66: 82] ]

    Defines the first partition to be a size of 1/3 the disk,
    while the remaining 2/3's will be of type Linux Swap.
    """

    if not isinstance(layout, list) and isinstance(layout, bool):
        # Create a single partition, default to Linux
        return ",,83"

    if ((not layout) and isinstance(layout, list)) or not isinstance(
        layout, list
    ):
        raise RuntimeError("Partition layout is invalid")

    last_part_num = len(layout)
    if last_part_num > 4:
        raise RuntimeError("Only simply partitioning is allowed.")

    part_definition = []
    part_num = 0
    for part in layout:
        part_type = 83  # Default to Linux
        percent = part
        part_num += 1

        if isinstance(part, list):
            if len(part) != 2:
                raise RuntimeError(
                    "Partition was incorrectly defined: %s" % part
                )
            percent, part_type = part

        part_size = int(float(size) * (float(percent) / 100))

        if part_num == last_part_num:
            part_definition.append(",,%s" % part_type)
        else:
            part_definition.append(",%s,%s" % (part_size, part_type))

    sfdisk_definition = "\n".join(part_definition)
    if len(part_definition) > 4:
        raise RuntimeError(
            "Calculated partition definition is too big\n%s"
            % sfdisk_definition
        )

    return sfdisk_definition


def get_partition_gpt_layout(size, layout):
    if isinstance(layout, bool):
        return [(None, [0, 0])]

    partition_specs = []
    for partition in layout:
        if isinstance(partition, list):
            if len(partition) != 2:
                raise RuntimeError(
                    "Partition was incorrectly defined: %s" % partition
                )
            percent, partition_type = partition
        else:
            percent = partition
            partition_type = None

        part_size = int(float(size) * (float(percent) / 100))
        partition_specs.append((partition_type, [0, "+{}".format(part_size)]))

    # The last partition should use up all remaining space
    partition_specs[-1][-1][-1] = 0
    return partition_specs


def purge_disk_ptable(device):
    # wipe the first and last megabyte of a disk (or file)
    # gpt stores partition table both at front and at end.
    null = b"\0"
    start_len = 1024 * 1024
    end_len = 1024 * 1024
    with open(device, "rb+") as fp:
        fp.write(null * (start_len))
        fp.seek(-end_len, os.SEEK_END)
        fp.write(null * end_len)
        fp.flush()

    read_parttbl(device)


def purge_disk(device):
    """
    Remove partition table entries
    """

    # wipe any file systems first
    for d in enumerate_disk(device):
        if d["type"] not in ["disk", "crypt"]:
            wipefs_cmd = ["wipefs", "--all", "/dev/%s" % d["name"]]
            try:
                LOG.info("Purging filesystem on /dev/%s", d["name"])
                subp.subp(wipefs_cmd)
            except Exception as e:
                raise RuntimeError(
                    "Failed FS purge of /dev/%s" % d["name"]
                ) from e

    purge_disk_ptable(device)


def get_partition_layout(table_type, size, layout):
    """
    Call the appropriate function for creating the table
    definition. Returns the table definition

    This is a future proofing function. To add support for
    other layouts, simply add a "get_partition_%s_layout"
    function.
    """
    if "mbr" == table_type:
        return get_partition_mbr_layout(size, layout)
    elif "gpt" == table_type:
        return get_partition_gpt_layout(size, layout)
    raise RuntimeError("Unable to determine table type")


def read_parttbl(device):
    """
    `Partprobe` is preferred over `blkdev` since it is more reliably
    able to probe the partition table.
    """
    partprobe = "partprobe"
    if subp.which(partprobe):
        probe_cmd = [partprobe, device]
    else:
        probe_cmd = ["blockdev", "--rereadpt", device]
    util.udevadm_settle()
    try:
        subp.subp(probe_cmd)
    except Exception as e:
        util.logexc(LOG, "Failed reading the partition table %s" % e)

    util.udevadm_settle()


def exec_mkpart_mbr(device, layout):
    """
    Break out of mbr partition to allow for future partition
    types, i.e. gpt
    """
    # Create the partitions
    prt_cmd = ["sfdisk", "--force", device]
    try:
        subp.subp(prt_cmd, data="%s\n" % layout)
    except Exception as e:
        raise RuntimeError(
            "Failed to partition device %s\n%s" % (device, e)
        ) from e

    read_parttbl(device)


def exec_mkpart_gpt_sgdisk(device, layout):
    try:
        subp.subp(["sgdisk", "-Z", device])
        for index, (partition_type, (start, end)) in enumerate(layout):
            index += 1
            subp.subp(
                [
                    "sgdisk",
                    "-n",
                    "{}:{}:{}".format(index, start, end),
                    device,
                ]
            )
            if partition_type is not None:
                # convert to a 4 char (or more) string right padded with 0
                # 82 -> 8200.  'Linux' -> 'Linux'
                pinput = str(partition_type).ljust(4, "0")
                subp.subp(
                    ["sgdisk", "-t", "{}:{}".format(index, pinput), device]
                )
    except Exception:
        LOG.warning("Failed to partition device %s", device)
        raise


def exec_mkpart_gpt_sfdisk(device, layout):
    cmd = ""
    # Promote partition types to GPT partition GUIDs
    for partition_type, (_, end) in layout:
        partition_type = str(partition_type).ljust(4, "0")
        if len(partition_type) == 4 and partition_type in sgdisk_to_gpt_id:
            partition_type = sgdisk_to_gpt_id[partition_type]
        if len(partition_type) != 36:
            if partition_type != "None":
                LOG.warning(
                    "Unknown GPT partition type %s, using Linux",
                    partition_type,
                )
            partition_type = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
        if str(end) != "0":
            cmd += ",%s,%s\n" % (end, partition_type)
        else:
            cmd += ",,%s\n" % partition_type
    try:
        subp.subp(["sfdisk", "-X", "gpt", "--force", device], data="%s" % cmd)
    except Exception:
        LOG.warning("Failed to partition device %s", device)
        raise


def exec_mkpart_gpt(device, layout):
    if subp.which("sgdisk"):
        exec_mkpart_gpt_sgdisk(device, layout)
    else:
        exec_mkpart_gpt_sfdisk(device, layout)

    read_parttbl(device)


def assert_and_settle_device(device):
    """Assert that device exists and settle so it is fully recognized."""
    if not os.path.exists(device):
        util.udevadm_settle()
        if not os.path.exists(device):
            raise RuntimeError(
                "Device %s did not exist and was not created "
                "with a udevadm settle." % device
            )

    # Whether or not the device existed above, it is possible that udev
    # events that would populate udev database (for reading by lsdname) have
    # not yet finished. So settle again.
    util.udevadm_settle()


def mkpart(device, definition):
    """
    Creates the partition table.

    Parameters:
        definition: dictionary describing how to create the partition.

            The following are supported values in the dict:
                overwrite: Should the partition table be created regardless
                            of any pre-existing data?
                layout: the layout of the partition table
                table_type: Which partition table to use, defaults to MBR
                device: the device to work on.
    """
    # ensure that we get a real device rather than a symbolic link
    assert_and_settle_device(device)
    device = os.path.realpath(device)

    LOG.debug("Checking values for %s definition", device)
    overwrite = definition.get("overwrite", False)
    layout = definition.get("layout", False)
    table_type = definition.get("table_type", "mbr")

    # Check if the default device is a partition or not
    LOG.debug("Checking against default devices")

    if (isinstance(layout, bool) and not layout) or not layout:
        LOG.debug("Device is not to be partitioned, skipping")
        return  # Device is not to be partitioned

    # This prevents you from overwriting the device
    LOG.debug("Checking if device %s is a valid device", device)
    if not is_device_valid(device):
        raise RuntimeError(
            "Device {device} is not a disk device!".format(device=device)
        )

    # Remove the partition table entries
    if isinstance(layout, str) and layout.lower() == "remove":
        LOG.debug("Instructed to remove partition table entries")
        purge_disk(device)
        return

    LOG.debug("Checking if device layout matches")
    if check_partition_layout(table_type, device, layout):
        LOG.debug("Device partitioning layout matches")
        return True

    LOG.debug("Checking if device is safe to partition")
    if not overwrite and (is_disk_used(device) or is_filesystem(device)):
        LOG.debug("Skipping partitioning on configured device %s", device)
        return

    LOG.debug("Checking for device size of %s", device)
    device_size = get_hdd_size(device)

    LOG.debug("Calculating partition layout")
    part_definition = get_partition_layout(table_type, device_size, layout)
    LOG.debug("   Layout is: %s", part_definition)

    LOG.debug("Creating partition table on %s", device)
    if "mbr" == table_type:
        exec_mkpart_mbr(device, part_definition)
    elif "gpt" == table_type:
        exec_mkpart_gpt(device, part_definition)
    else:
        raise RuntimeError("Unable to determine table type")

    LOG.debug("Partition table created for %s", device)


def lookup_force_flag(fs):
    """
    A force flag might be -F or -F, this look it up
    """
    flags = {
        "ext": "-F",
        "btrfs": "-f",
        "xfs": "-f",
        "reiserfs": "-f",
        "swap": "-f",
    }

    if "ext" in fs.lower():
        fs = "ext"

    if fs.lower() in flags:
        return flags[fs]

    LOG.warning("Force flag for %s is unknown.", fs)
    return ""


def mkfs(fs_cfg):
    """
    Create a file system on the device.

        label: defines the label to use on the device
        fs_cfg: defines how the filesystem is to look
            The following values are required generally:
                device: which device or cloud defined default_device
                filesystem: which file system type
                overwrite: indiscriminately create the file system
                partition: when device does not define a partition,
                            setting this to a number will mean
                            device + partition. When set to 'auto', the
                            first free device or the first device which
                            matches both label and type will be used.

                            'any' means the first filesystem that matches
                            on the device.

            When 'cmd' is provided then no other parameter is required.
    """
    label = fs_cfg.get("label")
    device = fs_cfg.get("device")
    partition = str(fs_cfg.get("partition", "any"))
    fs_type = fs_cfg.get("filesystem")
    fs_cmd = fs_cfg.get("cmd", [])
    fs_opts = fs_cfg.get("extra_opts", [])
    fs_replace = fs_cfg.get("replace_fs", False)
    overwrite = fs_cfg.get("overwrite", False)

    # ensure that we get a real device rather than a symbolic link
    assert_and_settle_device(device)
    device = os.path.realpath(device)

    # This allows you to define the default ephemeral or swap
    LOG.debug("Checking %s against default devices", device)

    if not partition or partition.isdigit():
        # Handle manual definition of partition
        if partition.isdigit():
            # nvme support
            # https://github.com/torvalds/linux/blob/45db3ab/block/partitions
            # /core.c#L330
            if device[-1].isdigit():
                device = f"{device}p"
            device = "%s%s" % (device, partition)
            if not Path(device).is_block_device():
                LOG.warning(
                    "Path %s does not exist or is not a block device", device
                )
                return
            LOG.debug(
                "Manual request of partition %s for %s", partition, device
            )

        # Check to see if the fs already exists
        LOG.debug("Checking device %s", device)
        check_label, check_fstype, _ = check_fs(device)
        LOG.debug(
            "Device '%s' has check_label='%s' check_fstype=%s",
            device,
            check_label,
            check_fstype,
        )

        if check_label == label and check_fstype == fs_type:
            LOG.debug("Existing file system found at %s", device)

            if not overwrite:
                LOG.debug("Device %s has required file system", device)
                return
            else:
                LOG.debug("Destroying filesystem on %s", device)

        else:
            LOG.debug("Device %s is cleared for formatting", device)

    elif partition and str(partition).lower() in ("auto", "any"):
        # For auto devices, we match if the filesystem does exist
        odevice = device
        LOG.debug("Identifying device to create %s filesystem on", label)

        # 'any' means pick the first match on the device with matching fs_type
        label_match = True
        if partition.lower() == "any":
            label_match = False

        device, reuse = find_device_node(
            device,
            fs_type=fs_type,
            label=label,
            label_match=label_match,
            replace_fs=fs_replace,
        )
        LOG.debug("Automatic device for %s identified as %s", odevice, device)

        if reuse:
            LOG.debug("Found filesystem match, skipping formatting.")
            return

        if not reuse and fs_replace and device:
            LOG.debug("Replacing file system on %s as instructed.", device)

        if not device:
            LOG.debug(
                "No device available that matches request. "
                "Skipping fs creation for %s",
                fs_cfg,
            )
            return
    elif not partition or str(partition).lower() == "none":
        LOG.debug("Using the raw device to place filesystem %s on", label)

    else:
        LOG.debug("Error in device identification handling.")
        return

    LOG.debug(
        "File system type '%s' with label '%s' will be created on %s",
        fs_type,
        label,
        device,
    )

    # Make sure the device is defined
    if not device:
        LOG.warning("Device is not known: %s", device)
        return

    # Check that we can create the FS
    if not (fs_type or fs_cmd):
        raise RuntimeError(
            "No way to create filesystem '{label}'. fs_type or fs_cmd "
            "must be set.".format(label=label)
        )

    # Create the commands
    shell = False
    if fs_cmd:
        fs_cmd = fs_cfg["cmd"] % {
            "label": label,
            "filesystem": fs_type,
            "device": device,
        }
        shell = True

        if overwrite:
            LOG.warning(
                "fs_setup:overwrite ignored because cmd was specified: %s",
                fs_cmd,
            )
        if fs_opts:
            LOG.warning(
                "fs_setup:extra_opts ignored because cmd was specified: %s",
                fs_cmd,
            )
    else:
        # Find the mkfs command
        mkfs_cmd = subp.which("mkfs.%s" % fs_type)
        if not mkfs_cmd:
            # for "mkswap"
            mkfs_cmd = subp.which("mk%s" % fs_type)

        if not mkfs_cmd:
            LOG.warning(
                "Cannot create fstype '%s'.  No mkfs.%s command",
                fs_type,
                fs_type,
            )
            return

        fs_cmd = [mkfs_cmd]

        if label:
            fs_cmd.extend(["-L", label])

        # File systems that support the -F flag
        if overwrite or device_type(device) == "disk":
            force_flag = lookup_force_flag(fs_type)
            if force_flag:
                fs_cmd.append(force_flag)

        # Add the extends FS options
        if fs_opts:
            fs_cmd.extend(fs_opts)

        fs_cmd.append(device)

    LOG.debug("Creating file system %s on %s", label, device)
    try:
        subp.subp(fs_cmd, shell=shell)
    except Exception as e:
        raise RuntimeError("Failed to exec of '%s':\n%s" % (fs_cmd, e)) from e
