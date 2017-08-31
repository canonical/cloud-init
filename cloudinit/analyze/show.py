#   Copyright (C) 2016 Canonical Ltd.
#
#   Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import datetime
import json
import os

from cloudinit import util

#  An event:
'''
{
        "description": "executing late commands",
        "event_type": "start",
        "level": "INFO",
        "name": "cmd-install/stage-late"
        "origin": "cloudinit",
        "timestamp": 1461164249.1590767,
},

    {
        "description": "executing late commands",
        "event_type": "finish",
        "level": "INFO",
        "name": "cmd-install/stage-late",
        "origin": "cloudinit",
        "result": "SUCCESS",
        "timestamp": 1461164249.1590767
    }

'''
format_key = {
    '%d': 'delta',
    '%D': 'description',
    '%E': 'elapsed',
    '%e': 'event_type',
    '%I': 'indent',
    '%l': 'level',
    '%n': 'name',
    '%o': 'origin',
    '%r': 'result',
    '%t': 'timestamp',
    '%T': 'total_time',
}

formatting_help = " ".join(["{0}: {1}".format(k.replace('%', '%%'), v)
                           for k, v in format_key.items()])


def format_record(msg, event):
    for i, j in format_key.items():
        if i in msg:
            # ensure consistent formatting of time values
            if j in ['delta', 'elapsed', 'timestamp']:
                msg = msg.replace(i, "{%s:08.5f}" % j)
            else:
                msg = msg.replace(i, "{%s}" % j)
    return msg.format(**event)


def dump_event_files(event):
    content = dict((k, v) for k, v in event.items() if k not in ['content'])
    files = content['files']
    saved = []
    for f in files:
        fname = f['path']
        fn_local = os.path.basename(fname)
        fcontent = base64.b64decode(f['content']).decode('ascii')
        util.write_file(fn_local, fcontent)
        saved.append(fn_local)

    return saved


def event_name(event):
    if event:
        return event.get('name')
    return None


def event_type(event):
    if event:
        return event.get('event_type')
    return None


def event_parent(event):
    if event:
        return event_name(event).split("/")[0]
    return None


def event_timestamp(event):
    return float(event.get('timestamp'))


def event_datetime(event):
    return datetime.datetime.utcfromtimestamp(event_timestamp(event))


def delta_seconds(t1, t2):
    return (t2 - t1).total_seconds()


def event_duration(start, finish):
    return delta_seconds(event_datetime(start), event_datetime(finish))


def event_record(start_time, start, finish):
    record = finish.copy()
    record.update({
        'delta': event_duration(start, finish),
        'elapsed': delta_seconds(start_time, event_datetime(start)),
        'indent': '|' + ' ' * (event_name(start).count('/') - 1) + '`->',
    })

    return record


def total_time_record(total_time):
    return 'Total Time: %3.5f seconds\n' % total_time


def generate_records(events, blame_sort=False,
                     print_format="(%n) %d seconds in %I%D",
                     dump_files=False, log_datafiles=False):

    sorted_events = sorted(events, key=lambda x: x['timestamp'])
    records = []
    start_time = None
    total_time = 0.0
    stage_start_time = {}
    stages_seen = []
    boot_records = []

    unprocessed = []
    for e in range(0, len(sorted_events)):
        event = events[e]
        try:
            next_evt = events[e + 1]
        except IndexError:
            next_evt = None

        if event_type(event) == 'start':
            if event.get('name') in stages_seen:
                records.append(total_time_record(total_time))
                boot_records.append(records)
                records = []
                start_time = None
                total_time = 0.0

            if start_time is None:
                stages_seen = []
                start_time = event_datetime(event)
                stage_start_time[event_parent(event)] = start_time

            # see if we have a pair
            if event_name(event) == event_name(next_evt):
                if event_type(next_evt) == 'finish':
                    records.append(format_record(print_format,
                                                 event_record(start_time,
                                                              event,
                                                              next_evt)))
            else:
                # This is a parent event
                records.append("Starting stage: %s" % event.get('name'))
                unprocessed.append(event)
                stages_seen.append(event.get('name'))
                continue
        else:
            prev_evt = unprocessed.pop()
            if event_name(event) == event_name(prev_evt):
                record = event_record(start_time, prev_evt, event)
                records.append(format_record("Finished stage: "
                                             "(%n) %d seconds ",
                                             record) + "\n")
                total_time += record.get('delta')
            else:
                # not a match, put it back
                unprocessed.append(prev_evt)

    records.append(total_time_record(total_time))
    boot_records.append(records)
    return boot_records


def show_events(events, print_format):
    return generate_records(events, print_format=print_format)


def load_events(infile, rawdata=None):
    if rawdata:
        data = rawdata.read()
    else:
        data = infile.read()

    j = None
    try:
        j = json.loads(data)
    except ValueError:
        pass

    return j, data
