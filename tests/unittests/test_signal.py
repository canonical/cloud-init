"""Tests for handling of signals within cloud init."""

import os
import subprocess
import sys
import time

from StringIO import StringIO

from mocker import MockerTestCase


class TestSignal(MockerTestCase):

    def test_signal_output(self):

        # This is done since nose/unittest is actually setting up
        # output capturing, signal handling itself, and its easier
        # to just call out to cloudinit with a loop and see what the result is
        run_what = [sys.executable, 
                    '-c', ('import time; from cloudinit import signal_handler;'
                           'signal_handler.attach_handlers(); time.sleep(120)')]

        pc_info = subprocess.Popen(run_what, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        # Let it start up
        time.sleep(0.5)
        dead = None
        while dead is None:
            pc_info.terminate()
            # Ok not dead yet. try again
            time.sleep(0.5)
            dead = pc_info.poll()

        outputs = StringIO()
        if pc_info.stdout:
            outputs.write(pc_info.stdout.read())
        if pc_info.stderr:
            outputs.write(pc_info.stderr.read())
        val = outputs.getvalue()
        print val

        # Check some of the outputs that should of happened
        self.assertEquals(1, pc_info.wait())
        self.assertTrue(len(val) != 0)
        self.assertTrue(val.find("terminated") != -1)
