import os
import time
import logging
import uuid
import sys
import threading

if __name__ != '__main__':
    logger = logging.getLogger(__name__)

import comtypes
import comtypes.client
from comtypes.client import GetEvents, PumpEvents, ShowEvents

# class WyattEventHandler(object):
#     def __init__(self):
#         logger.info('Starting Wyatt event handler')
#         self.instrument_detected_evt = threading.Event()
#         self._stop_poll = threading.Event()

#         self._polling_thread = threading.Thread(target=self._poll)
#         self._polling_thread.daemon = True
#         self._polling_thread.start()

#     def _IAstraEvents_InstrumentDetectionCompleted(self):
#         logger.info('Instrument detection completed')
#         self.instrument_detected_evt.set()

#     def _poll(self):
#         comtypes.CoInitializeEx()

#         try:
#             while not self._stop_poll.wait(1):
#                 PumpEvents(0.1)
#                 pass
#         finally:
#             comtypes.CoUninitialize()

#     def stop(self):
#         self._stop_poll.set()
#         self._polling_thread.join(5)

class WyattEventHandler(threading.Thread):
    def __init__(self):

        threading.Thread.__init__(self)
        self.daemon = True

        self.instrument_detected_evt = threading.Event()
        self._stop_poll = threading.Event()

    def run(self):
        logger.info('Starting Wyatt event handler')
        comtypes.CoInitialize()

        try:
            while not self._stop_poll.wait(1):
                PumpEvents(0.1)
                pass
        finally:
            comtypes.CoUninitialize()

    def _IAstraEvents_InstrumentDetectionCompleted(self):
        logger.info('Instrument detection completed')
        self.instrument_detected_evt.set()

    def stop(self):
        self._stop_poll.set()


class WyattControl(object):
    """
    """
    def __init__(self, show_astra=True):
        logger.info('Starting Wyatt control')
        self.astra_lock = threading.RLock()

        with self.astra_lock:
            self.astra_com = comtypes.client.CreateObject("WTC.ASTRA8.Application.1")

        logger.info('Starting Astra')
        pid = os.getpid()
        guid = str(uuid.uuid4())

        with self.astra_lock:
            self.astra_com.SetAutomationIdentity('WyattControl', '0.1', pid,
                guid, True, [])

        self.evt_handler = WyattEventHandler()
        self.evt_handler.start()
        self.evt_connection = GetEvents(self.astra_com, self.evt_handler)

        self.wait_for_instruments()

        if show_astra:
            with self.astra_lock:
                self.astra_com.Show(True)

        self.get_methods()

        logger.info('Waytt control started')

    def wait_for_instruments(self):
        logger.info('Waiting to detect instruments')
        while not self.evt_handler.instrument_detected_evt.wait(1):
            # PumpEvents(0.1)
            pass

        self.evt_handler.instrument_detected_evt.clear()

    def get_methods(self):
        logger.info('Getting all experiment methods')
        with self.astra_lock:
            self.methods = self.astra_com.GetExperimentTemplates()
        for m in self.methods:
            print(m)

    def close(self):
        logger.info('Closing Wyatt control')
        self.evt_handler.stop()
        self.evt_connection.disconnect()

        with self.astra_lock:
            self.astra_com.RequestQuit()


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    h1 = logging.StreamHandler(sys.stdout)
    h1.setLevel(logging.INFO)
    # h1.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s')
    h1.setFormatter(formatter)
    logger.addHandler(h1)


    wc = WyattControl()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        wc.close()

