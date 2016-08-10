#!/usr/bin/python
# vi: ts=4 expandtab

import json
import os
import tempfile


def atomic_write_file(path, content, mode='w'):
    tf = None
    try:
        tf = tempfile.NamedTemporaryFile(dir=os.path.dirname(path),
                                         delete=False, mode=mode)
        tf.write(content)
        tf.close()
        os.rename(tf.name, path)
    except Exception as e:
        if tf is not None:
            os.unlink(tf.name)
        raise e


def atomic_write_json(path, data):
    return atomic_write_file(path, json.dumps(data, indent=1,
                                              sort_keys=True) + "\n")
