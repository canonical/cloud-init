from textwrap import dedent

from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module is able to configure simple partition tables and filesystems.

.. note::
    for more detail about configuration options for disk setup, see the disk
    setup example

For convenience, aliases can be specified for disks using the
``device_aliases`` config key, which takes a dictionary of alias: path
mappings. There are automatic aliases for ``swap`` and ``ephemeral<X>``, where
``swap`` will always refer to the active swap partition and ``ephemeral<X>``
will refer to the block device of the ephemeral image.

Disk partitioning is done using the ``disk_setup`` directive. This config
directive accepts a dictionary where each key is either a path to a block
device or an alias specified in ``device_aliases``, and each value is the
configuration options for the device. File system configuration is done using
the ``fs_setup`` directive. This config directive accepts a list of
filesystem configs.
"""

PROPERTY_DESCRIPTIONS = {
    "alias_name": """\
Path to disk to be aliased by this name
""",
    "table_type": """\
Specifies the partition table type, either ``mbr`` or ``gpt``.
Default: ``mbr``
""",
    "layout": """\
If set to ``true``, a single partition using all the space on the device will
be created. If set to ``false``, no partitions will be created. Partitions can
be specified by providing a list to ``layout``, where each entry in the list is
either a size or a list containing a size and the numerical value for a
partition type. The size for partitions is specified in **percentage** of disk
space, not in bytes (e.g. a size of 33 would take up 1/3 of the disk space).
Default: ``false``
""",
    "overwrite_disk": """\
Controls whether this module tries to be safe about
writing partition tables or not. If ``overwrite: false`` is set, the device
will be checked for a partition table and for a file system and if either is
found, the operation will be skipped. If ``overwrite: true`` is set, no checks
will be performed. Using ``overwrite: true`` is **dangerous** and can lead to
data loss, so double check that the correct device has been specified if
using this option. Default: ``false``
""",
    "label": """\
Label for the filesystem.
""",
    "filesystem": """\
Filesystem type to create. E.g., ``ext4`` or ``btrfs``
""",
    "device": """\
Specified either as a path or as an alias in the format ``<alias name>.<y>``
where ``<y>`` denotes the partition number on the device. If specifying
device using the ``<device name>.<partition number>`` format, the value
of ``partition`` will be overwritten.
""",
    "partition": """\
The partition can be specified by setting ``partition`` to the desired
partition number. The ``partition`` option may also be set to ``auto``, in
which this module will search for the existence of a filesystem matching the
``label``, ``type`` and ``device`` of the ``fs_setup`` entry and will skip
creating the filesystem if one is found. The ``partition`` option may also be
set to ``any``, in which case any file system that matches ``type`` and
``device`` will cause this module to skip filesystem creation for the
``fs_setup`` entry, regardless of ``label`` matching or not. To write a
filesystem directly to a device, use ``partition: none``. ``partition: none``
will **always** write the filesystem, even when the ``label`` and
``filesystem`` are matched, and ``overwrite`` is ``false``.
""",
    "overwrite_fs": """\
If ``true``, overwrite any existing filesystem. Using ``overwrite: true``
for filesystems is **dangerous** and can lead to data loss, so double check
the entry in ``fs_setup``. Default: ``false``
""",
    "replace_fs": """\
Ignored unless ``partition`` is ``auto`` or ``any``. Default ``false``.
""",
    "extra_opts": """\
Optional options to pass to the filesystem creation command.
Ignored if you using ``cmd`` directly.
""",
    "cmd": """\
Optional command to run to create the filesystem.
Can include string substitutions of the other ``fs_setup`` config keys.
This is only necessary if you need to override the default command.
""",
}

meta = {
    "id": "cc_disk_setup",
    "name": "Disk Setup",
    "title": "Configure partitions and filesystems",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            device_aliases:
              my_alias: /dev/sdb
            disk_setup:
              my_alias:
                table_type: gpt
                layout: [50, 50]
                overwrite: True
            fs_setup:
            - label: fs1
              filesystem: ext4
              device: my_alias.1
              cmd: mkfs -t %(filesystem)s -L %(label)s %(device)s
            - label: fs2
              device: my_alias.2
              filesystem: ext4
            mounts:
            - ["my_alias.1", "/mnt1"]
            - ["my_alias.2", "/mnt2"]
            """
        )
    ],
}

schema = {
    "type": "object",
    "properties": {
        "device_aliases": {
            "type": "object",
            "patternProperties": {
                "^.+$": {
                    "label": "<alias_name>",
                    "type": "string",
                    "description": PROPERTY_DESCRIPTIONS["alias_name"],
                }
            },
        },
        "disk_setup": {
            "type": "object",
            "patternProperties": {
                "^.+$": {
                    "label": "<alias name/path>",
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "table_type": {
                            "type": "string",
                            "enum": ["mbr", "gpt"],
                            "description": PROPERTY_DESCRIPTIONS["table_type"],
                        },
                        "layout": {
                            "type": ["string", "boolean", "array"],
                            "oneOf": [
                                {"type": "string", "enum": ["auto", "remove"]},
                                {
                                    "type": "boolean",
                                },
                                {
                                    "type": "array",
                                    "items": {
                                        "oneOf": [
                                            {"type": "integer"},
                                            {
                                                "type": "array",
                                                "items": {"type": "integer"},
                                            },
                                        ]
                                    },
                                },
                            ],
                            "description": PROPERTY_DESCRIPTIONS["layout"],
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": PROPERTY_DESCRIPTIONS[
                                "overwrite_disk"
                            ],
                        },
                    },
                },
            },
        },
        "fs_setup": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {
                        "type": "string",
                        "description": PROPERTY_DESCRIPTIONS["label"],
                    },
                    "filesystem": {
                        "type": "string",
                        "description": PROPERTY_DESCRIPTIONS["filesystem"],
                    },
                    "device": {
                        "type": "string",
                        "description": PROPERTY_DESCRIPTIONS["device"],
                    },
                    "partition": {
                        "type": ["string", "integer"],
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["auto", "any", "none"],
                            },
                            {"type": "integer"},
                        ],
                        "description": PROPERTY_DESCRIPTIONS["partition"],
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": PROPERTY_DESCRIPTIONS["overwrite_fs"],
                    },
                    "replace_fs": {
                        "type": "string",
                        "description": PROPERTY_DESCRIPTIONS["replace_fs"],
                    },
                    "extra_opts": {
                        "type": ["array", "string"],
                        "items": {"type": "string"},
                        "description": PROPERTY_DESCRIPTIONS["extra_opts"],
                    },
                    "cmd": {
                        "type": ["array", "string"],
                        "items": {"type": "string"},
                        "description": PROPERTY_DESCRIPTIONS["cmd"],
                    },
                },
            },
        },
    },
}
