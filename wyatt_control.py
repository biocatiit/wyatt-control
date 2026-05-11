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
from enum import Enum

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

class Status(Enum):
    NEW = 'Loading'
    READY = 'Ready'
    WAIT_FOR_TRIG = 'Waiting for trigger'
    RUN = 'Running'

class Experiment(object):
    """
    """
    def __init__(self, astra, comm_lock, method):
        self.astra = astra
        self.comm_lock = comm_lock
        self._method = method

        with self.comm_lock:
            self._exp_id = int(self.astra.NewExperimentFromTemplate(method))

    def get_exp_id(self):
        return self._exp_id

    def get_method(self):
        return self._method

    def get_flow_rate(self):
        """
        Gets the experiment method flow rate.

        Returns
        -------
        flow_rate: float
           The experiment method flow rate in mL/min. Returns None if
           the flow rate is not set or an error occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetPumpFlowRate(self._exp_id))
        except ValueError:
            logger.exception('Failed to get flow rate for experiment ID %s, '
                'value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get flow rate for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_inj_vol(self):
        """
        Gets the experiment method injected volume.

        Returns
        -------
        inj_vol: float
           The experiment method injected volume in mL. Returns None if
           the injected volume is not set or an error occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetInjectedVolume(self._exp_id))
        except ValueError:
            logger.exception('Failed to get injected volume for experiment ID %s, '
                'value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get injected volume for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_sample_name(self):
        """
        Gets the experiment method sample name. As seen in the experiment
        Configuration Injector node.

        Returns
        -------
        name: str
           The experiment method sample name. Returns None if
           an error occurs.
        """
        try:
            with self.comm_lock:
                val = str(self.astra.GetSampleName(self._exp_id))
        except Exception:
            logger.exception('Failed to get sample name for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_sample_descrip(self):
        """
        Gets the experiment method sample description. As seen in the experiment
        Configuration Injector node.

        Returns
        -------
        descrip: str
           The experiment method sample description. Returns None if
           an error occurs.
        """
        try:
            with self.comm_lock:
                val = str(self.astra.GetSampleDescription(self._exp_id))
        except Exception:
            logger.exception('Failed to get sample description for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_dn_dc(self):
        """
        Gets the experiment method dn/dc.

        Returns
        -------
        dn_dc: float
           The experiment method dn/dc in mL/g. Returns None if
           the dn/dc is not set or an error occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetSampleDndc(self._exp_id))
        except ValueError:
            logger.exception('Failed to get dn/dc for experiment ID %s, '
                'value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get dn/dc for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_A2(self):
        """
        Gets the experiment method A2.

        Returns
        -------
        a2: float
           The experiment method A2 in mol*mL/g^2. Returns None if
           the A2 value is not set or an error occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetSampleA2(self._exp_id))
        except ValueError:
            logger.exception('Failed to get A2 for experiment ID %s, '
                'value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get A2 for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_uv_ext(self):
        """
        Gets the experiment method UV extinction coefficient.

        Returns
        -------
        uv_ext: float
           The experiment method UV extinction coefficient in mL/(g*cm).
           Returns None if the coefficient is not set or an error occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetSampleUvExtinction(self._exp_id))
        except ValueError:
            logger.exception('Failed to get UV extinction coefficient for '
                'experiment ID %s, value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get UV extinction coefficient for '
                'experiment ID %s.', self._exp_id)
            val = None

        return val

    def get_conc(self):
        """
        Gets the experiment method injected sample concentration.

        Returns
        -------
        conc: float
           The experiment method injected sample concentration in g/mL.
           Returns None if the coefficient is not set or an error occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetSampleConcentration(self._exp_id))
        except ValueError:
            logger.exception('Failed to get injected sample concentration for '
                'experiment ID %s, value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get injected sample concentration for '
                'experiment ID %s.', self._exp_id)
            val = None

        return val

    def set_flow_rate(self, flow_rate):
        """
        Sets the experiment method flow rate.

        Parameters
        ----------
        flow_rate: float
           The experiment method flow rate in mL/min.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(flow_rate)
        except ValueError:
            logger.exception('Failed to set flow rate for experiment ID %s, '
                'value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetPumpFlowRate(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set flow rate for experiment ID %s.',
                    self._exp_id)

        return success

    def set_inj_vol(self, inj_vol):
        """
        Sets the experiment method injected volume.

        Parameters
        ----------
        inj_vol: float
           The experiment method injected volume in mL.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(inj_vol)
        except ValueError:
            logger.exception('Failed to set injected volume for experiment '
                'ID %s, value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetInjectedVolume(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set injected volume for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_sample_name(self, name):
        """
        Sets the experiment method sample description. Gets set in the experiment
        Configuration Injector node.

        Parameters
        ----------
        name: str
           The experiment method sample name.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = str(name)
        except ValueError:
            logger.exception('Failed to set sample name for experiment '
                'ID %s, value is not a string.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetSampleName(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set sample name for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_sample_descrip(self, descrip):
        """
        Sets the experiment method sample description. Gets set in the experiment
        Configuration Injector node.

        Parameters
        ----------
        descrip: str
           The experiment method sample description.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = str(descrip)
        except ValueError:
            logger.exception('Failed to set sample description for experiment '
                'ID %s, value is not a string.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetSampleDescription(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set sample description for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_dn_dc(self, dn_dc):
        """
        Sets the experiment method dn/dc.

        Parameters
        ----------
        dn_dc: float
           The experiment method dn/dc in mL/g.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(dn_dc)
        except ValueError:
            logger.exception('Failed to set dn/dc for experiment '
                'ID %s, value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetSampleDndc(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set dn/dc for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_A2(self, a2):
        """
        Sets the experiment method A2.

        Parameters
        ----------
        a2: float
           The experiment method A2 in mol*mL/g^2.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(a2)
        except ValueError:
            logger.exception('Failed to set A2 for experiment '
                'ID %s, value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetSampleA2(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set A2 for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_uv_ext(self, uv_ext):
        """
        Sets the experiment method UV extinction coefficient.

        Parameters
        ----------
        uv_ext: float
           The experiment method UV extinction coefficient in mL/(g*cm).

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(uv_ext)
        except ValueError:
            logger.exception('Failed to set UV extinction coefficient for '
                'experiment ID %s, value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetSampleUvExtinction(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set UV extinction coefficient '
                    'for experiment ID %s.',
                    self._exp_id)

        return success

    def set_conc(self, conc):
        """
        Sets the experiment method sample concentration.

        Parameters
        ----------
        conc: float
           The experiment method sample concentration in g/mL.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(conc)
        except ValueError:
            logger.exception('Failed to set sample concentration for experiment '
                'ID %s, value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetSampleConcentration(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set sample concentration for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def get_experiment_name(self):
        """
        Gets the experiment name (e.g. as displayed in Astra).

        Returns
        -------
        name: str
           The experiment name. Returns None if an error occurs.
        """
        try:
            with self.comm_lock:
                val = str(self.astra.GetExperimentName(self._exp_id))
        except Exception:
            logger.exception('Failed to get experiment name for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_experiment_descrip(self):
        """
        Gets the experiment description. As seen in the top level configuration
        node for the experiment.

        Returns
        -------
        descrip: str
           The experiment description. Returns None if an error occurs.
        """
        try:
            with self.comm_lock:
                val = self.astra.GetExperimentDescription(self._exp_id)
        except Exception:
            logger.exception('Failed to get experiment description for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def get_total_runtime(self):
        """
        Gets the experiment method total run time

        Returns
        -------
        run_time: float
           The experiment total run time in min. Returns None if an error
           occurs.
        """
        try:
            with self.comm_lock:
                val = float(self.astra.GetCollectionDuration(self._exp_id))
        except ValueError:
            logger.exception('Failed to get total run time for experiment ID %s, '
                'value is not a number.', self._exp_id)
            val = None
        except Exception:
            logger.exception('Failed to get total run time for experiment ID %s.',
                self._exp_id)
            val = None

        return val

    def set_experiment_descrip(self, descrip):
        """
        Sets the experiment description. Shows up in the top level configuration
        node for the experiment.

        Parameters
        ----------
        descrip: str
           The experiment description.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = str(descrip)
        except ValueError:
            logger.exception('Failed to set experiment description for experiment '
                'ID %s, value is not a string.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetExperimentDescription(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set experiment description for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_total_runtime(self, run_time):
        """
        Sets the experiment method total run time.

        Parameters
        ----------
        run_time: float
           The experiment method total run time in min.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        try:
            val = float(run_time)
        except ValueError:
            logger.exception('Failed to set total run time for experiment '
                'ID %s, value is not a number.', self._exp_id)
            val = None

        success = False

        if val is not None:
            try:
                with self.comm_lock:
                    self.astra.SetCollectionDuration(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set total run time for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

    def set_use_instrument_calibration(self, use_inst_cal):
        """
        If the instrument calibration constant varies between the experimental
        configuration and the one stored on the physical instrument, define
        whether the one in the experimental method or on the instrument should
        be used. By default the one on the instrument is used.

        Parameters
        ----------
        use_inst_cal: bool
           If True, use the calibration constant from the physical instrument.
           If False, use the calibration constant in the experimental method.

        Returns
        -------
        success: bool
            True if the value is successfully set.
        """
        success = False

        if (not isinstance(use_inst_cal, bool)
            and not (use_inst_cal == 1 or use_inst_cal == 0)):
            logger.error('Failed to set use instrument calibration for '
                'experiment ID %s, value is not a boolean', self._exp_id)

        else:
            if use_inst_cal:
                val = True
            else:
                val = False

            try:
                with self.comm_lock:
                    self.astra.UseInstrumentCalibrationConstant(self._exp_id, val)
                success = True
            except Exception:
                logger.exception('Failed to set total run time for '
                    'experiment ID %s.',
                    self._exp_id)

        return success

class WyattControl(object):
    """
    """
    def __init__(self, show_astra=True):
        logger.info('Starting Wyatt control')
        self.comm_lock = threading.RLock()

        # Seems to be something weird with the .NET callbacks,
        # so move them back to python in a thread
        self._callback_stop = threading.Event()
        self._callback_queue = deque()
        self._callback_cmds = {
            'on_instrument'         : self._on_instrument,
            'on_experiment_read'    : self._on_experiment_read,
            'on_experiment_run'     : self._on_experiment_run,
            'on_generic'            : self._on_generic,
            }

        self._callback_thread = threading.Thread(target=self._run_from_callback,
            name='WyattCallback')
        self._callback_thread.daemon = True
        self._callback_thread.start()

        self.instrument_detected_evt = threading.Event()

        self._exp_lock = threading.RLock()
        self._experiments = {}

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

        self._wait_for_instruments()

        if show_astra:
            with self.comm_lock:
                self.astra.Show(True)

        self._get_methods()

        logger.info('Waytt control started')

    def _connect_callbacks(self):
        with self.comm_lock:
            self.astra.InstrumentDetectionCompleted += self._on_instrument_callback
            self.astra.ExperimentRead += self._on_experiment_read_callback
            self.astra.ExperimentRun += self._on_experiment_run_callback

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

    def _on_experiment_read_callback(self, *args, **kwargs):
        self._callback_queue.append(['on_experiment_read', args ,kwargs])

    def _on_experiment_read(self, args, kwargs):
        exp_id = args[0]
        # Turns out this isn't useful because you need to wait for the
        # experiment run event triggered right after the read in order to
        # modify the experiment

    def _on_experiment_run_callback(self, *args, **kwargs):
        self._callback_queue.append(['on_experiment_run', args ,kwargs])

    def _on_experiment_run(self, args, kwargs):
        exp_id = args[0]

        with self._exp_lock:
            if self._experiments[exp_id]['status'] == Status.NEW:
                self._experiments[exp_id]['status'] = Status.READY

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

    def _wait_for_instruments(self):
        logger.info('Waiting to detect instruments')
        while not self.instrument_detected_evt.wait(1):
            pass

    def _get_methods(self):
        logger.info('Getting all experiment methods')
        with self.comm_lock:
            self.methods = self.astra.GetExperimentTemplates()

    def get_available_methods(self):
        """
        Returns a list of the available methods. Note that this list of methods
        is only updated when the control object is started.

        Returns
        -------
        methods: list
            A list of availble methods with the full method path.
        """
        return self.methods

    def create_utility_experiment(self, method):
        """
        Creates a new Astra experiment for a utility method.

        Parameters
        ----------
        method: str
            The path to the method to be used, as returned by get_available_methods.

        Returns
        -------
        exp_id: int
            The experimental id. Required to start an experment. Returns None
            if method is not a valid method.
        exp: Experiment object
            The experiment object that carries around the experiment's properties
            and allows getting/setting of the properties. Returns None
            if method is not a valid method.
        """
        logger.info('Creating utility expeirment')
        exp_id, exp = self._create_experiment(method)
        return exp_id, exp

    def create_experiment(self, method, run_time=None, name=None,
        descrip=None, flow_rate=None, inj_vol=None, conc=None, dn_dc=None,
        uv_ext=None, a2=None, use_inst_cal=None):
        """
        Creates a new Astra experiment for a standard method.

        Parameters
        ----------
        method: str
            The path to the method to be used, as returned by get_available_methods.
        run_time: float
            The method runtime in minutes. Optional. If not provided, the
            method default is retained.
        name: str
            The sample name. Optional. If not provided, the method default
            is retained.
        descrip: str
            The sample description. Optional. If not provided, the method
            default is retained.
        flow_rate: float
            The pump flow rate in mL/min. Optional. If not provided, the
            method default is retained.
        inj_vol: float
            The injected volume in mL. Optional. If not provided, the
            method default is retained.
        conc: float
            The injected sample concentration in g/mL. Optional. If not provided,
            the method default is retained.
        dn_dc: float
            The sample dn/dc in mL/g. Optional. If not provided, the method default
            is retained.
        uv_ext: float
            The sample UV extinction coefficient in mL/(g*cm). Optional. If
            not provided, the method default is retained.
        a2: float
            The sample A2 coefficient in mol*mL/g^2. Optional. If not provided,
            the method default is retained.
        use_inst_cal: bool
            If True, use the physical instrument calibration value if it differs
            from the experimental method configuration value. If False, use
            the method value if the two differ.Optional. If not provided,
            the physical instrument calibration value is used if there is a
            difference.

        Returns
        -------
        exp_id: int
            The experimental id. Required to start an experiment. Returns None
            if method is not a valid method.
        exp: Experiment object
            The experiment object that carries around the experiment's properties
            and allows getting/setting of the properties. Returns None
            if method is not a valid method.
        """
        logger.info('Creating experiment')

        exp_id, exp = self._create_experiment(method)

        if exp_id is not None:
            self._wait_for_exp_read(exp_id)

            if run_time is not None:
                exp.set_total_runtime(run_time)

            if name is not None:
                exp.set_sample_name(name)

            if descrip is not None:
                exp.set_sample_descrip(descrip)

            if flow_rate is not None:
                exp.set_flow_rate(flow_rate)

            if inj_vol is not None:
                exp.set_inj_vol(inj_vol)

            if conc is not None:
                exp.set_conc(conc)

            if dn_dc is not None:
                exp.set_dn_dc(dn_dc)

            if uv_ext is not None:
                exp.set_uv_ext(uv_ext)

            if a2 is not None:
                exp.set_A2(a2)

            if use_inst_cal is not None:
                exp.set_use_instrument_calibration(use_inst_cal)

        return exp_id, exp

    def _create_experiment(self, method):
        if method in self.methods:
            try:
                exp = Experiment(self.astra, self.comm_lock, method)
                exp_id = exp.get_exp_id()
            except Exception:
                logger.exception('Error creating a new experiment from method %s', method)
                exp = None
                exp_id = None
        else:
            logger.error('Method %s is not a valid method. Experiment '
                'cannot be created.', method)
            exp = None
            exp_id = None

        if exp_id is not None and exp is not None:
            with self._exp_lock:
                self._experiments[exp_id] = {
                    'exp'       : exp,
                    'status'    : Status.NEW,
                    }

        return exp_id, exp

    def _check_exp_id(self, exp_id):
        logger.debug('Validating experiment id %s', exp_id)
        try:
            exp_id = int(exp_id)
        except Exception:
            logger.exception('Experiment ID must be an integer.')
            exp_id = None

        if exp_id is not None:
            with self._exp_lock:
                if exp_id in self._experiments:
                    exp = self._experiments[exp_id]
                else:
                    logger.error('Experiment ID %s is not an active experiment, '
                        'experiment.', exp_id)
                    exp = None
        else:
            exp = None

        return exp_id, exp

    def _wait_for_exp_read(self, exp_id):
        logger.debug('Waiting for experiment to be read/created')
        while True:
            with self._exp_lock:
                if self._experiments[exp_id]['status'] == Status.READY:
                    break
            time.sleep(0.1)

    def validate_experiemt(self, exp_id):
        """
        Validates experiment prior to data collection

        Maybe doesn't work for utility methods? Test on a real method to see if
        this is working

        Parameters
        ----------
        exp_id: int
            The experimental id.

        Returns
        -------
        valid: bool
            Whether the experiment is valid. Note that if the experiment
            validates with warnings but no errors, valid will return true.
        error: str
            A string that provides error and warning text.
        """
        logger.info('Validating experiment with exp ID %s', exp_id)
        exp_id, exp = self._check_exp_id(exp_id)

        if exp is not None:
            try:
                with self.comm_lock:
                    # Note: return value order seems to reversed from documentation
                    valid, error = self.astra.ValidateExperiment(exp_id)

                    if valid:
                        valid = True
                    else:
                        valid = False

            except Exception:
                logger.exception('Error running Astra validate experiment method.')
                error = ''
                valid = False

        else:
            error = ''
            valid = False

        return valid, error

    def start_experiment(self, exp_id, wait_for_autoinject=False,
        wait_for_collection=False):
        """
        Starts experment (e.g. for normal experiments, sends them to waiting
        for trigger).

        Parameters
        ----------
        exp_id: int
            The experimental id.

        wait_for_autoinject: bool
            If True, the method will wait for the experiment to reach the
            waiting for autoinject stage before returning.

        wait_for_collection: bool
            If True, the method will wait for the experiment to start
            collecting before returning. Note that this overrides the
            wait_for_autoinject flag. If you wait for collection, then
            the method will wait to return until collection, regardless
            of how you set wait_for_autoinject.

        Returns
        -------
        success: bool
            True if experiment started without errors.
        """
        logger.info('Starting experiment with exp ID %s', exp_id)
        exp_id, exp = self._check_exp_id(exp_id)

        success = False

        if exp is not None:
            try:
                with self.comm_lock:
                    self.astra.StartCollection(exp_id)
                success = True
            except Exception:
                logger.exception('Error running Astra start collection method.')


        # Waiting stuff goes here

        return success

    def _disconnect_callbacks(self):
        with self.comm_lock:
            self.astra.InstrumentDetectionCompleted -= self._on_instrument_callback
            self.astra.ExperimentRead -= self._on_experiment_read_callback
            self.astra.ExperimentRun -= self._on_experiment_run_callback

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

    # exp_id, exp = wc.create_utility_experiment(
    #     '//dbf/System/Methods/RI Measurement/Utilities/Purge On')

    # print(exp_id)
    # print(exp)

    # valid, errors = wc.validate_experiemt(exp_id)

    # print(valid)
    # print(errors)

    # success = wc.start_experiment(exp_id)

    # print(success)

    ###################################################
    # Create a standard experiment
    exp_id, exp = wc.create_experiment('//dbf/User/Methods/LS+DLS+UV+dRI HPLC1 20240216',
        run_time=45, name='Sample1', descrip='My sample', flow_rate=0.6,
        inj_vol=0.3, conc=0.12, dn_dc=0.185, uv_ext=1, a2=1, use_inst_cal=True)

    valid, errors = wc.validate_experiemt(exp_id)

    print('Valid:')
    print(valid)
    print('Errors:')
    print(errors)

    # success = wc.start_experiment(exp_id)

    # print(success)

    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     wc.close()
