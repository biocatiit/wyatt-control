# coding: utf-8
#
#    Project: BioCAT user beamline control software (BioCON)
#             https://github.com/biocatiit/beamline-control-user
#
#
#    Principal author:       Jesse Hopkins
#
#    This is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This software is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this software.  If not, see <http://www.gnu.org/licenses/>.

import os
import glob
import time
import datetime
import logging
import sys
import threading
from collections import deque
import traceback
import copy
import pathlib
import functools
import uuid

if __name__ != '__main__':
    logger = logging.getLogger(__name__)

import numpy as np


try:
    import clr

    clr.AddReference(os.path.abspath('./AstraLib.dll'))

    import AstraLib

except Exception:
    # Note: the try/except is just to enable building documentation on systems
    # without the agilent dlls
    # logger.error('Failed to import the Wyatt DLLs!!')
    traceback.print_exc()


class WyattControl(object):
    """
    """
    def __init__(self, show_astra=True):
        logger.info('Starting Wyatt control')
        self.comm_lock = threading.Lock()

        # Seems to be something weird with the .NET callbacks,
        # so move them back to python in a thread
        self._callback_stop = threading.Event()
        self._callback_queue = deque()
        self._callback_cmds = {
            'on_instrument'         : self._on_instrument,
            'on_generic'            : self._on_generic,
            }

        self._callback_thread = threading.Thread(target=self._run_from_callback,
            name='WyattCallback')
        self._callback_thread.daemon = True
        self._callback_thread.start()

        self.instrument_detected_evt = threading.Event()

        self._connect(show_astra)

    def _connect(self, show_astra):

        with self.comm_lock:
            self.astra = AstraLib.Astra()

        logger.info('Starting Astra')
        pid = os.getpid()
        guid = str(uuid.uuid4())

        with self.comm_lock:
            self.astra.SetAutomationIdentity('WyattControl', '0.1', pid,
                guid, True, [])

        self._connect_callbacks()

        self.wait_for_instruments()

        if show_astra:
            with self.comm_lock:
                self.astra.Show(True)

        self.get_methods()

        logger.info('Waytt control started')

    def _connect_callbacks(self):
        self.astra.InstrumentDetectionCompleted += self._on_instrument_callback

    def _on_generic_callback(self, *args, **kwargs):
        self._callback_queue.append(['on_generic', args, kwargs])

    def _on_generic(self, args, kwargs):
        print(source)
        print(args)

        self.generic_data = [args, kwargs]

    def _on_instrument_callback(self, *args, **kwargs):
        self._callback_queue.append(['on_instrument', args ,kwargs])

    def _on_instrument(self, args, kwargs):
        self.instrument_detected_evt.set()


    def _run_from_callback(self):
        while True:
            if len(self._callback_queue) > 0:
                cmd, args, kwargs = self._callback_queue.popleft()
                try:
                    self._callback_cmds[cmd](args, kwargs)
                except Exception:
                    msg = ("Wyatt callback thread failed to run command '%s' "
                    "with args: %s and kwargs: %s" %(cmd,
                        ', '.join(['{}'.format(a) for a in args]),
                        ', '.join(['{}:{}'.format(kw, item) for kw, item in kwargs.items()])))
                    logger.exception(msg)

            else:
                time.sleep(0.1)

            if self._callback_stop.is_set():
                break

    def wait_for_instruments(self):
        logger.info('Waiting to detect instruments')
        while not self.instrument_detected_evt.wait(1):
            pass

    def get_methods(self):
        logger.info('Getting all experiment methods')
        with self.comm_lock:
            self.methods = self.astra.GetExperimentTemplates()
        for m in self.methods:
            print(m)

    def _disconnect_callbacks(self):
        self.astra.InstrumentDetectionCompleted -= self._on_instrument_callback

    def close(self):
        logger.info('Closing Wyatt control')

        self._disconnect_callbacks()

        with self.comm_lock:
            self.astra.RequestQuit()


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    h1 = logging.StreamHandler(sys.stdout)
    h1.setLevel(logging.DEBUG)
    h1.setLevel(logging.INFO)
    # h1.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s')
    h1.setFormatter(formatter)
    logger.addHandler(h1)


    wc = WyattControl()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        wc.close()
