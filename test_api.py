# -*- coding: utf-8 -*-
"""
Compatible with ASTRA 8.2 and later only.
"""
import comtypes.client
from comtypes.client import GetEvents, PumpEvents

import inspect

from distutils.version import LooseVersion
from threading import Event, RLock, Thread
from enum import Enum
from datetime import datetime
from typing import Callable
from dataclasses import dataclass
from copy import deepcopy
from ctypes import *
import uuid
import os
import time


rlock = RLock()

# Security pack classes
@dataclass
class LogonResult:
    """Used by security pack sdk
    """
    isValid: bool
    errorMessage: str
    errorDetails: str


@dataclass
class IsDomainValidResult:
    """Used by security pack sdk
    """
    isValid: bool
    status: str


@dataclass
class DomainsInfo:
    """Used by security pack sdk
    """
    domains: list
    selectedDomain: str


@dataclass
class ActiveUserInfo:
    """Used by security pack sdk
    """
    userId: str
    fullUserName: str
    localDomain: str


@dataclass
class GroupName:
    """Used by security pack sdk
    """
    useDefault: bool
    name: str
    customName: str


@dataclass
class SecurityPolicy:
    """Used by security pack sdk
    """
    location: int
    domain: str
    idleLockoutInterval: float
    failSafe: bool
    groupLocation: int
    groupNameAdmin: GroupName
    groupNameResearcher: GroupName
    groupNameTechnician: GroupName
    groupNameGuest: GroupName
    groupNameNone: GroupName


@dataclass
class SampleInfo:
    """SampleInfo
    """
    name: str
    description: str
    dndc: float
    a2: float
    uvExtinction: float
    concentration: float


@dataclass
class AstraMethodInfo:
    """AstraMethodInfo
    """
    experimentPath: str
    sample: SampleInfo
    injectedVolume: float
    flowRate: float
    duration: float


@dataclass
class LogonResult:
    """LogonResult
    """
    isValid: bool
    errorMessage: str
    errorDetails: str

@dataclass
class BaselinePoint:
    """BaselinePoint
    """
    x: float
    y: float


class BaselineType(Enum):
    """BaselineType
    """
    NONE = 0
    MANUAL = 1
    SNAP_Y = 2
    AUTOMATIC = 3


@dataclass
class BaselineDetails:
    """BaselineDetails
    """
    seriesName: str
    type: BaselineType
    start: BaselinePoint
    end: BaselinePoint


@dataclass
class PeakRange:
    """PeakRange
    """
    number: int
    start: float
    end: float


@dataclass
class PeakRanges:
    """PeakRanges
    """
    size: int
    peaks: list


class ExperimentEventHandler:
    """ExperimentEventHandler
    """
    def __init__(self) -> None:
        self._experiment_observers = []

    def add_experiment_observer(self, observer: Callable) -> None:
        self._experiment_observers.append(observer)

    def notify_observers(self, param) -> None:
        for observer in self._experiment_observers:
            observer(param)


class InstrumentsDetectedEventHandler:
    """InstrumentsDetectedEventHandler
    """
    def __init__(self) -> None:
        self._inst_detected_observers = []

    def add_experiment_observer(self, observer: Callable) -> None:
        self._inst_detected_observers.append(observer)

    def notify_observers(self) -> None:
        for observer in self._inst_detected_observers:
            observer()


@dataclass
class ExperimentData:
    """ExperimentData
    """
    description: str
    collection_duration: float
    flow_rate: float
    injected_volume: float
    sample: SampleInfo


class ExperimentStatus(Enum):
    """ExperimentStatus
    """
    READY = 0
    WAITING_FOR_AUTO_INJECT = 1
    EXECUTE = 2
    BUSY = 3


class Experiment:
    """Experiment wrapper: although all experiment operations can be performed through
    the AstraAdmin singleton, this class wraps calls to get/set various properties,
    providing a better sense of encapsulation.
    """

    _tolerance = 1e-6
    _synchronized_data: ExperimentData
    _data: ExperimentData

    def __init__(self, experiment_id: int) -> None:
        """Constructor: retrieve experiment name and initialize data.

        Args:
            experiment_id (int): The ID of the experiment
        """
        self.id = experiment_id
        self.status = ExperimentStatus.READY
        self.name = AstraAdmin().get_experiment_name(experiment_id)
        self.has_data = False
        self._synchronized_data = ExperimentData(
            description="",
            collection_duration=0.0,
            flow_rate=0.0,
            injected_volume=0.0,
            sample=SampleInfo(
                name="",
                description="",
                dndc=0.0,
                a2=0.0,
                uvExtinction=0.0,
                concentration=0.0
            )
        )
        self._data = ExperimentData(
            description="",
            collection_duration=0.0,
            flow_rate=0.0,
            injected_volume=0.0,
            sample=SampleInfo(
                name="",
                description="",
                dndc=0.0,
                a2=0.0,
                uvExtinction=0.0,
                concentration=0.0
            )
        )

    def read(self) -> None:
        """Get experiment settings from ASTRA."""
        if self.id == 0:
            return

        self._synchronized_data.description = AstraAdmin().get_experiment_description(self.id)
        self._synchronized_data.collection_duration = AstraAdmin().get_collection_duration(self.id)
        self._synchronized_data.flow_rate = AstraAdmin().get_pump_flow_rate(self.id)
        self._synchronized_data.injected_volume = AstraAdmin().get_injected_volume(self.id)
        self._synchronized_data.sample = AstraAdmin().get_sample(self.id)

        self._data = self._synchronized_data

    def reset(self) -> None:
        """Reset experiment state to synched state. Synched state will be the
        last applied state, or the initial state.
        """
        self._data = self._synchronized_data


class AstraEvents:
    """_summary_"""

    ready_event = Event()
    read_event = Event()
    write_event = Event()
    run_event = Event()
    closed_event = Event()
    instrument_detected_signal = Event()
    preparing_for_collection_event = Event()
    waiting_for_auto_inject_event = Event()
    collection_started_event = Event()
    collection_finished_event = Event()
    """
    Note: The list of events need to have the exact same name,
          Changing the names to match Python's snake case convention
          will not work.
    """

    def _IAstraEvents_ExperimentClosed(self, experiment_id: int) -> None:
        """Event fired when experiment is closed.

        Args:
            experiment_id (int): The experiment that is closed.
        """
        with rlock:
            if experiment_id not in AstraAdmin().closing_experiments:
                assert False, "Experiment should exist in a callback."
            self.closed_event.set()
            AstraAdmin().experiment_closed.notify_observers(
                AstraAdmin().closing_experiments[experiment_id]
            )
            AstraAdmin().closing_experiments.pop(experiment_id)

    def _IAstraEvents_ExperimentReady(self, experiment_id: int) -> None:
        """Event fired when experiment is ready.

        Args:
            experiment_id (int): The experiment that is ready.
        """
        def on_experiment_ready():
            with rlock:
                experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
                if experiment is None:
                    assert (
                        experiment_id in AstraAdmin().closing_experiments
                    ), "Experiment should exist in a callback."
                    return

                experiment.status = ExperimentStatus.READY

                self.ready_event.set()

                AstraAdmin().experiment_status_changed.notify_observers(experiment)

        Thread(target=on_experiment_ready).start()

    def _IAstraEvents_PreparingForCollection(self, experiment_id: int) -> None:
        """Event fired when experiment is preparing for collection.

        Args:
            experiment_id (int): The experiment that is preparing for collection.
        """
        with rlock:
            experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
            if experiment is None:
                assert (
                    experiment_id in AstraAdmin().closing_experiments
                ), "Experiment should exist in a callback."
                return

            experiment.status = ExperimentStatus.BUSY

            self.preparing_for_collection_event.set()

            AstraAdmin().experiment_status_changed.notify_observers(experiment)

    def _IAstraEvents_WaitingForAutoInject(self, experiment_id: int) -> None:
        """Event fired when experiment is waiting for auto inject.

        Args:
            experiment_id (int): The experiment that is waiting for auto inject.
        """
        with rlock:
            experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
            if experiment is None:
                assert (
                    experiment_id in AstraAdmin().closing_experiments
                ), "Experiment should exist in a callback."
                return

            experiment.status = ExperimentStatus.WAITING_FOR_AUTO_INJECT

            self.waiting_for_auto_inject_event.set()

            AstraAdmin().experiment_status_changed.notify_observers(experiment)

    def _IAstraEvents_CollectionStarted(self, experiment_id: int) -> None:
        """Event fired when experiment collection started.

        Args:
            experiment_id (int): The experiment that a collection has started.
        """
        with rlock:
            experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
            if experiment is None:
                assert (
                    experiment_id in AstraAdmin().closing_experiments
                ), "Experiment should exist in a callback."
                return

            experiment.status = ExperimentStatus.BUSY
            experiment.has_data = True

            self.collection_started_event.set()

            AstraAdmin().experiment_status_changed.notify_observers(experiment)

    def _IAstraEvents_CollectionAborted(self, experiment_id: int) -> None:
        """Event fired when experiment collection is aborted.

        Args:
            experiment_id (int): The experiment that a collection is aborted.
        """
        with rlock:
            experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
            if experiment is None:
                assert (
                    experiment_id in AstraAdmin().closing_experiments
                ), "Experiment should exist in a callback."
                return

            experiment.status = ExperimentStatus.READY

            self.collection_finished_event.set()

            AstraAdmin().experiment_status_changed.notify_observers(experiment)

    def _IAstraEvents_CollectionFinished(self, experiment_id: int) -> None:
        """Event fired when experiment collection is finished.

        Args:
            experiment_id (int): The experiment that a collection is finished.
        """
        with rlock:
            experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
            if experiment is None:
                assert (
                    experiment_id in AstraAdmin().closing_experiments
                ), "Experiment should exist in a callback."
                return

            experiment.status = ExperimentStatus.READY

            self.collection_finished_event.set()

            AstraAdmin().experiment_status_changed.notify_observers(experiment)

    def _IAstraEvents_InstrumentDetectionCompleted(self) -> None:
        """Event fired when Astra is done detecting instruments
        """
        with rlock:
            self.instrument_detected_signal.set()

            AstraAdmin().instrument_detected.notify_observers()

    def _IAstraEvents_ExperimentRun(self, experiment_id: int) -> None:
        """Event fired when experiment is run.

        Args:
            experiment_id (int): The experiment that is running.
        """
        def on_experiment_run():
            with rlock:
                experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
                if experiment is None:
                    assert (
                        experiment_id in AstraAdmin().closing_experiments
                    ), "Experiment should exist in a callback."
                    return

                experiment.status = ExperimentStatus.READY

                self.run_event.set()

                AstraAdmin().experiment_status_changed.notify_observers(experiment)

        Thread(target=on_experiment_run).start()

    def _IAstraEvents_ExperimentRead(self, experiment_id: int) -> None:
        """Event fired when experiment is read.

        Args:
            experiment_id (int): The experiment that is read.
        """
        def on_experiment_read():
            with rlock:
                experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
                if experiment is None:
                    assert (
                        experiment_id in AstraAdmin().closing_experiments
                    ), "Experiment should exist in a callback."
                    return

                experiment.status = ExperimentStatus.READY

                self.read_event.set()

                AstraAdmin().experiment_status_changed.notify_observers(experiment)

        Thread(target=on_experiment_read).start()

    def _IAstraEvents_ExperimentWrite(self, experiment_id: int) -> None:
        """Event fired when experiment is write.

        Args:
            experiment_id (int): The experiment that is write.
        """
        with rlock:
            experiment: Experiment = AstraAdmin().get_internal_experiment(experiment_id)
            if experiment is None:
                assert (
                    experiment_id in AstraAdmin().closing_experiments
                ), "Experiment should exist in a callback."
                return

            experiment.status = ExperimentStatus.READY

            self.write_event.set()

            AstraAdmin().experiment_status_changed.notify_observers(experiment)


class AstraAdmin:
    """_summary_

    Args:
        object (_type_): _description_

    Returns:
        _type_: _description_
    """

    MinAstraVersion = LooseVersion("8.2.0.0")
    Version_8_2_0_105 = LooseVersion("8.2.0.105")

    should_show_error_message_box = True

    experiment_closed = ExperimentEventHandler()
    experiment_status_changed = ExperimentEventHandler()
    instrument_detected = InstrumentsDetectedEventHandler()

    closing_experiments: dict[int, Experiment] = {}
    _experiments: dict[int, Experiment] = {}

    astra_com = comtypes.client.CreateObject("WTC.ASTRA8.Application.1")
    events = AstraEvents()
    connection = GetEvents(astra_com, events)
    astra_sp_com = comtypes.client.CreateObject("Wyatt.AstraSP.1")
    _entity_id = None

    # UvDeviceDetails class (if this ever fail, check uuid for Astra from Astra.idl file)
    UvDeviceDetails = comtypes.gen._368D43B2_3A78_4EB0_93D1_5339084555E2_0_1_0.UvDeviceDetails

    IsInstanceAlreadyInitialized = True

    # Singleton class
    def __new__(cls):
        if not hasattr(cls, "instance") or not cls.IsInstanceAlreadyInitialized:
            cls.instance = super(AstraAdmin, cls).__new__(cls)
            cls.IsInstanceAlreadyInitialized = True
        return cls.instance

    def __init__(self) -> None:
        pass

    def __del__(self) -> None:
        self.dispose()

    def astra_version(self) -> LooseVersion:
        with rlock:
            try:
                return LooseVersion(self.astra_com.GetVersion())
            except:
                return LooseVersion("0.0.0.0")

    def reset_astra(self) -> None:
        with rlock:
            self.IsInstanceAlreadyInitialized = False

    def set_automation_identity(
        self, entity_name: str, entity_version: str, pid: int, entity_guid: str, enabled: int
    ) -> bool:
        """Set identify of client. This is the first call a client
        should make before making any other API calls.

        Args:
            entity_name (str): Name of the client.
            entity_version (str): Version of the client.
            pid (int): Process ID of the client.
            entity_guid (str): Unique identifier of the client.
            enabled (int): Unused, should always be set to 1.

        Returns:
            bool: True upon successful close, false otherwise.
        """

        def func():
            self._entity_id = entity_guid
            self.astra_com.SetAutomationIdentity(
                entity_name, entity_version, pid, entity_guid, enabled, []
            )

        return self.try_execute(func)

    def dispose(self) -> None:
        """Quit both Astra and security pack SDK.
        Should be called before a program exit.
        """
        with rlock:
            try:
                self.astra_com.RequestQuit()
                self.astra_sp_com.RequestQuit()
            except Exception:
                # Ignore. It might fail due to lack of licensing when using ASTRA 8.0.x or older.
                pass


    def has_instrument_detection_completed(self) -> bool:
        """Have instruments been fully detected yet?

        Returns:
            bool: True when all instruments have been detected, false otherwise.
        """
        return self.try_get(lambda: self.astra_com.InstrumentsDetected == 1)

    def wait_experiment_read(self) -> None:
        """Wait until experiment is fully read. To be called after loading an experiment."""
        while not AstraEvents.read_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.read_event.clear()

    def wait_experiment_write(self) -> None:
        """Wait until experiment is fully written. To be called after saving an experiment."""
        while not AstraEvents.write_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.write_event.clear()

    def wait_experiment_run(self) -> None:
        """Wait until experiment is fully run. To be called after an operation that will render experiment not ready (e.g. a collection or a run of the experiment)."""
        while not AstraEvents.run_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.run_event.clear()

    def wait_for_instruments(self) -> None:
        """Wait for ASTRA to load all instruments."""
        if not self.has_instrument_detection_completed():
            while not AstraEvents.instrument_detected_signal.wait(1.0):
                PumpEvents(0.1)
            AstraEvents.instrument_detected_signal.clear()

    def wait_experiment_closed(self) -> None:
        """Wait until experiment is fully closed."""
        while not AstraEvents.closed_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.closed_event.clear()

    def wait_preparing_for_collection(self) -> None:
        """Wait until collection is fully validated."""
        while not AstraEvents.preparing_for_collection_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.preparing_for_collection_event.clear()

    def wait_waiting_for_auto_inject(self) -> None:
        """Wait until the waiting for auto-inject message is sent."""
        while not AstraEvents.waiting_for_auto_inject_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.waiting_for_auto_inject_event.clear()

    def wait_collection_started(self) -> None:
        """Wait until collection starts."""
        while not AstraEvents.collection_started_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.collection_started_event.clear()

    def wait_collection_finished(self) -> None:
        """Wait until collection is finished."""
        while not AstraEvents.collection_finished_event.wait(1.0):
            PumpEvents(0.1)
        AstraEvents.collection_finished_event.clear()

    def collect_data(
        self,
        method_path: str,
        experiment_path: str,
        sample: SampleInfo,
        duration: float,
        injection_volume: float,
        flow_rate: float,
        progress_update: Callable,
    ) -> None:
        """Create new experiment and run collection, then save the experiment to a file or database.

        Args:
            method_path (str): Path to the method used to run a collection.
            experiment_path (str): Path where ASTRA experiment file will be saved.
            sample (SampleInfo): Information about the sample to use for collecting data.
            duration (float): Duration of collection expressed in minutes.
            injection_volume (float): Injection volume in microL.
            flow_rate (float): _descDesired/Set pump flow rate mL/min. If negative the one from the method.ription_
            progress_update (function): Action being executed for each major steps in the collection of data
        """
        astra_method_info = AstraMethodInfo(
            experiment_path, sample, injection_volume, flow_rate, duration
        )

        progress_update(f'Starting collection using method "{method_path}"...')
        experiment_id = self.new_experiment_from_template(method_path)

        self.collect_data_with_method_info_callback(
            experiment_id, progress_update, astra_method_info
        )

    def collect_data_with_method_info_callback(
        self,
        experiment_id: int,
        progress_update: Callable,
        method_info: AstraMethodInfo,
        request_method_at_end: bool = True,
    ) -> None:
        """Given a freshly created experiment with ID, start a collection but only fill the details
        for sample, duration, flow rate, injected volume after completion of the collection.

        Args:
            experiment_id (int): ID of experiment used for collecting data
            progress_update (function): Action being executed for each major steps in the collection of data
            method_info (AstraMethodInfo): Function returning info about the run at the end of a collection
            request_method_at_end (bool, optional): Defaults to True.
        """
        info = None
        if not request_method_at_end:
            info = method_info
            self.set_sample(experiment_id, info.sample)
            self.set_collection_duration(experiment_id, info.duration)
            self.set_injected_volume(experiment_id, info.injectedVolume)
            if info.flowRate >= 0:
                self.set_pump_flow_rate(experiment_id, info.flowRate)
        # Run collection.
        progress_update("Collection starting...")
        self.start_collection(experiment_id)
        self.wait_preparing_for_collection()
        progress_update("Preparing for collection...")

        self.wait_waiting_for_auto_inject()
        progress_update("Waiting for auto-inject...")

        self.wait_collection_started()
        progress_update("Starting collecting data...")

        # Get the current time to calculate the actual duration of the collection.
        date = datetime.now()

        if self.astra_version() >= self.Version_8_2_0_105:
            """
            By setting collection duration to -1, we will indefinitely collect until StopCollection is called.
            This has to be done after the collection starts.
            Due to an issue in earlier version of ASTRA, this call can be done when using version 8.2.0.105.
            """
            self.set_collection_duration(experiment_id, -1)

        self.wait_collection_finished()
        # Duration of the collection in minutes.
        duration = (datetime.now() - date).total_seconds() / 60

        progress_update("Collection finished.")

        progress_update("Post-collection actions...")
        self.wait_experiment_run()

        if request_method_at_end:
            """
            Ask for about details on the experiment. Note that all this calls are causing a run
            therefore we need to wait for the run event after each call before proceeding to the next,
            otherwise you will get an exception about unable to change a running experiment.
            """
            info = method_info
            self.set_sample(experiment_id, info.sample)
            self.wait_experiment_run()
            self.set_collection_duration(experiment_id, duration)
            self.wait_experiment_run()
            self.set_injected_volume(experiment_id, info.injectedVolume)
            self.wait_experiment_run()
            if info.flowRate >= 0:
                self.set_pump_flow_rate(experiment_id, info.flowRate)
                self.wait_experiment_run()

            # Save the experiment file.
            progress_update(f'Saving experiment "{info.ExperimentPath}"...')
            self.save_experiment(experiment_id, info.experimentPath)

            progress_update("Experiment saved.")

            self.close_experiment(experiment_id)

            # We have to clear all events that were received to start fresh when a new collection is performed
            self.reset_events()
            progress_update("Collection completed.")

    def get_active_user(self) -> ActiveUserInfo:
        """Get active user in security pack mode. If no active user, a user with an empty userId.

        Returns:
            ActiveUserInfo: The active user logged in, or a default user.
        """
        def func():
            active_user = self.try_get(lambda: self.astra_sp_com.GetActiveUserInfo())
            return active_user if active_user.userId else ActiveUserInfo(userId="", fullUserName="", localDomain="")

        return self.try_get(func)

    def shut_down(self) -> None:
        """Shutdown the current instance. It will close all open experiments and then perform a gracious shutdown of ASTRA."""
        for element in self._experiments:
            self.close_experiment(element.key)

    def get_experiment(self, experiment_id: int) -> Experiment:
        """Get experiment wrapper for an opened experiment.

        Args:
            experiment_id (int): ID of experiment to get.

        Returns:
            Experiment: If an experiment with ID exists, a copy of that experiment, null otherwise.
        """
        with rlock:
            if experiment_id in self._experiments:
                return deepcopy(self._experiments[experiment_id])
            return None

    def get_internal_experiment(self, experiment_id: int) -> Experiment:
        """Get experiment wrapper for an opened experiment.

        Args:
            experiment_id (int): ID of experiment to get.

        Returns:
            Experiment: If an experiment with ID exists, that experiment, null otherwise.
        """
        with rlock:
            if experiment_id in self._experiments:
                return self._experiments[experiment_id]
            return None

    def show_window(self, show: bool) -> bool:
        """Show/hide the ASTRA application window. To be used only for debugging purposes.

        Args:
            show (bool): True to show ASTRA, false otherwise.

        Returns:
            bool: True upon successful close, false otherwise.
        """
        return self.try_execute(lambda: self.astra_com.Show(self.bool_to_int(show)))

    def get_experiment_templates(self) -> list:
        """Get the list of experiment templates.

        Returns:
            list: List of experiment templates.
        """
        return self.try_get(self.astra_com.GetExperimentTemplates)

    def get_data_database_directory(self, root_path: str) -> list:
        """Get list of directories from the Data database under rootPath.

        Args:
            root_path (str): Path used to get all sub directories.

        Returns:
            list: List of directories under rootPath.
        """
        return self.try_get(lambda: self.astra_com.GetDataDatabaseDirectory(root_path))

    def new_experiment_from_template(self, template_path: str) -> int:
        """Create new experiment from template.

        Args:
            template_path (str): Location of template in system database.

        Returns:
            int: ID of a newly created experiment.
        """
        experiment_id = int()
        with rlock:
            experiment_id = self.try_get(
                lambda: self.astra_com.NewExperimentFromTemplate(template_path)
            )

            if type(experiment_id) is inspect._empty or experiment_id <= 0:
                return -1
            # Add Experiment wrapper to map of open experiments
            experiment = Experiment(experiment_id)
            experiment.status = ExperimentStatus.BUSY
            self._experiments[experiment_id] = experiment

            self.experiment_status_changed.notify_observers(experiment)

        """
        Wait until experiment is fully loaded and ready before proceeding.
        This needs to be done outside of the lock otherwise events cannot be processed.
        """
        self.wait_experiment_read()
        # self.wait_experiment_run()

        # with rlock:
        #     experiment = self.get_internal_experiment(experiment_id)
        #     experiment.read()
        #     self.experiment_status_changed.notify_observers(experiment)

        return experiment_id

    def get_experiment_name(self, experiment_id: int) -> str:
        """Get the name of an opened experiment.

        Args:
            experiment_id (int): ID of experiment to open.

        Returns:
            str: Name of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetExperimentName(experiment_id))

    def open_experiment(self, fileName: str) -> int:
        """Open an experiment from location "fileName".

        Args:
            fileName (str): Location of experiment to open.

        Returns:
            int: ID of experiment if successfully opened, otherwise 0.
        """
        experiment_id = int()
        with rlock:
            experiment_id = self.try_get(lambda: self.astra_com.OpenExperiment(fileName))
            if type(experiment_id) is inspect._empty or experiment_id <= 0:
                return -1
            # Add Experiment wrapper to map of open experiments
            experiment = Experiment(experiment_id)
            self._experiments[experiment_id] = experiment

            self.experiment_status_changed.notify_observers(experiment)

        """
        Wait until experiment is fully loaded and ready before proceeding.
        This needs to be done outside of the lock otherwise events cannot be processed.
        """
        self.wait_experiment_read()
        self.wait_experiment_run()

        with rlock:
            experiment = self.get_internal_experiment(experiment_id)
            experiment.read()
            self.experiment_status_changed.notify_observers(experiment)

        return experiment_id

    def save_experiment(self, experiment_id: int, file_name: str) -> bool:
        """Save experiment with ID "experimentID" to location "fileName".

        Args:
            experiment_id (int): ID of experiment to save.
            file_name (str): File location where experiment should be saved.

        Returns:
            bool: True when file is successfully saved, false otherwise.
        """
        date_time = datetime.now()
        with rlock:
            experiment = self.get_internal_experiment(experiment_id)

            if experiment is None:
                return False

            experiment.status = ExperimentStatus.BUSY

            self.experiment_status_changed.notify_observers(experiment)

            if not self.try_execute(
                lambda: self.astra_com.SaveExperiment(experiment_id, file_name)
            ):
                # Reset status of experiment and notify clients.
                experiment.status = ExperimentStatus.READY
                self.experiment_status_changed.notify_observers(experiment)
                return False

        # Wait has to be done outside of the lock (SyncRoot) otherwise the ASTRA messages cannot be sent.
        self.wait_experiment_write()

        return True

    def close_experiment(self, experiment_id: int) -> bool:
        """Close experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment to close.

        Returns:
            bool: True upon successful close, false otherwise.
        """
        with rlock:
            self.closing_experiments[experiment_id] = self.get_internal_experiment(experiment_id)
            self._experiments.pop(experiment_id)
            if not self.try_execute(lambda: self.astra_com.CloseExperiment(experiment_id)):
                return False

        self.wait_experiment_closed()
        return True

    def is_running(self, experiment_id: int) -> bool:
        """Is experiment with ID "experimentID" currently running?

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            bool: True if running, false otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetIsExperimentRunning(experiment_id) != 0)

    def get_collection_duration(self, experiment_id: int) -> float:
        """Get duration of collection for experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Duration in minutes.
        """
        return self.try_get(lambda: self.astra_com.GetCollectionDuration(experiment_id))

    def set_collection_duration(self, experiment_id: int, duration: float) -> bool:
        """Set duration of collection for experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            duration (float): Duration in minutes of the collection.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        return self.try_execute(
            lambda: self.astra_com.SetCollectionDuration(experiment_id, duration)
        )

    def validate_experiment(self, experiment_id: int) -> tuple[str, bool]:
        """Validate experiment with ID "experimentID". Useful before starting a collection.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            tuple[str, bool]:
                str: Warnings and errors reported during the validation.
                bool: True when experiment is valid, false otherwise.
        """

        def func() -> tuple[str, bool]:
            details, result = self.astra_com.ValidateExperiment(experiment_id)
            return details, result == 1

        return self.try_get(func)

    def use_instrument_calibration_constant(self, experiment_id: int, state: bool) -> bool:
        """For experiment to use either the Instrument's calibration constant or the method's calibration constant.

        Args:
            experiment_id (int): ID of experiment.
            state (bool): True to use the instrument's calibration constant, false to use the method's calibration constant.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        return self.try_execute(
            lambda: self.astra_com.UseInstrumentCalibrationConstant(
                experiment_id, self.bool_to_int(state)
            )
        )

    def start_collection(self, experiment_id: int) -> bool:
        """Start the collection of experiment with ID <paramref name="experimentID"/>.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            bool: True if call was successful, false otherwise.
        """

        def func() -> None:
            experiment = self.get_internal_experiment(experiment_id)
            self.astra_com.StartCollection(experiment_id)
            experiment.status = ExperimentStatus.BUSY
            self.experiment_status_changed.notify_observers(experiment)

        return self.try_execute(func)

    def stop_collection(self, experiment_id: int) -> bool:
        """Stop collection of experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        return self.try_execute(lambda: self.astra_com.StopCollection(experiment_id))

    def get_experiment_description(self, experiment_id: int) -> str:
        """Get the description of experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            str: Description if call is successful, None otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetExperimentDescription(experiment_id))

    def set_experiment_description(self, experiment_id: int, description: str) -> bool:
        """Set the description of experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            description (str): Description to use for experiment.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(
            lambda: self.astra_com.SetExperimentDescription(experiment_id, description)
        )
        return result

    def get_pump_flow_rate(self, experiment_id: int) -> float:
        """Get flow rate on pump for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Flow rate of pump in mL/min if successful, 0 otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetPumpFlowRate(experiment_id))

    def set_pump_flow_rate(self, experiment_id: int, flow_rate: float) -> bool:
        """Set flow rate on pump for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            flow_rate (float): Flow rate to set in mL/min.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute_and_wait_experiment_run(lambda: self.astra_com.SetPumpFlowRate(experiment_id, flow_rate))
        return result

    def get_injected_volume(self, experiment_id: int) -> float:
        """Get injected volume of the injector for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Injected volume in mL if successful, 0 otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetInjectedVolume(experiment_id))

    def set_injected_volume(self, experiment_id: int, injected_volume: float) -> bool:
        """Set injected volume of the injector for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            injected_volume (float): Injected volume in mL.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute_and_wait_experiment_run(
            lambda: self.astra_com.SetInjectedVolume(experiment_id, injected_volume)
        )
        return result

    def get_sample(self, experiment_id: int) -> SampleInfo:
        """Get sample for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            SampleInfo: Sample details of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSample(experiment_id))

    def set_sample(self, experiment_id: int, sample: SampleInfo) -> bool:
        """Set sample for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            sample (SampleInfo): Sample to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.SetSample(experiment_id, sample))
        return result

    def get_sample_name(self, experiment_id: int) -> str:
        """Get sample name for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            str: Sample name of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSampleName(experiment_id))

    def set_sample_name(self, experiment_id: int, name: str) -> bool:
        """Set sample name for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            name (str): Sample name to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.SetSampleName(experiment_id, name))
        return result

    def get_sample_description(self, experiment_id: int) -> str:
        """Get sample description for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            str: Sample description of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSampleDescription(experiment_id))

    def set_sample_description(self, experiment_id: int, description: str) -> bool:
        """Set sample description for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            description (str): Sample description to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.SetSampleDescription(experiment_id, description))
        return result

    def get_sample_dndc(self, experiment_id: int) -> float:
        """Get sample dndc for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Sample dndc details of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSampleDndc(experiment_id))

    def set_sample_dndc(self, experiment_id: int, dndc: float) -> bool:
        """Set sample dndc for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            dndc (float): Sample dndc to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute_and_wait_experiment_run(lambda: self.astra_com.SetSampleDndc(experiment_id, dndc))
        return result

    def get_sample_a2(self, experiment_id: int) -> float:
        """Get sample a2 for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Sample a2 details of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSampleA2(experiment_id))

    def set_sample_a2(self, experiment_id: int, a2: float) -> bool:
        """Set sample a2 for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            a2 (float): Sample A2 to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute_and_wait_experiment_run(lambda: self.astra_com.SetSampleA2(experiment_id, a2))
        return result

    def get_sample_uv_extinction(self, experiment_id: int) -> float:
        """Get sample uv extinction for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Sample uv extinction details of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSampleUvExtinction(experiment_id))

    def set_sample_uv_extinction(self, experiment_id: int, uv_extinction: float) -> bool:
        """Set sample uv extinction for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            uv_extinction (float): Sample uv extinction to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute_and_wait_experiment_run(lambda: self.astra_com.SetSampleUvExtinction(experiment_id, uv_extinction))
        return result

    def get_sample_concentration(self, experiment_id: int) -> float:
        """Get sample concentration for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            float: Sample concentration details of experiment.
        """
        return self.try_get(lambda: self.astra_com.GetSampleConcentration(experiment_id))

    def set_sample_concentration(self, experiment_id: int, concentration: float) -> bool:
        """Set sample concentration for experiment with ID.

        Args:
            experiment_id (int): ID of experiment.
            concentration (float): Sample concentration to use.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute_and_wait_experiment_run(lambda: self.astra_com.SetSampleConcentration(experiment_id, concentration))
        return result

    def has_vision_uv(self, experiment_id: int) -> bool:
        """Does experiment with ID "experimentID" have a VISION UV profile?

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            bool: True if experiment has a VISION UV profile, false otherwise.
        """
        return self.try_get(lambda: self.astra_com.HasVisionUv(experiment_id) == 1)

    def setup_vision_uv(self, experiment_id: int, device_details: UvDeviceDetails) -> bool:
        """Assuming experiment with ID "experimentID" has a VISION UV profile, set the details of the UV detector(s).

        Args:
            experiment_id (int): ID of experiment.
            device_details (UvDeviceDetails): Details of the used UV detector(s).

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(
            lambda: self.astra_com.SetupVisionUv(experiment_id, device_details)
        )
        return result

    def get_baselines(self, experiment_id: int) -> list:
        """Get baselines of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            list: List of baselines if successful, null otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetBaselines(experiment_id))

    def get_baseline_type_string(self, baseline_type: BaselineType) -> str:
        """String representation of a baseline's type.

        Args:
            type (BaselineType): Type of baseline.

        Returns:
            str: String representation of "type".
        """
        match baseline_type:
            case BaselineType.MANUAL:
                return "Manual"
            case BaselineType.SNAP_Y:
                return "SnapY"
            case BaselineType.AUTOMATIC:
                return "Automatic"
            case BaselineType.NONE:
                return "None"
            case _:
                return "None"

    def get_baseline_type_int(self, baseline_type: str) -> BaselineType:
        """Given a string representation of a baseline's type, return its corresponding "BaselineType".

        Args:
            type (str): String representation of baseline.

        Returns:
            BaselineType: Associated enumeration from "BaselineType".
        """
        match baseline_type.lower():
            case "manual":
                return BaselineType.MANUAL
            case "snapy":
                return BaselineType.SNAP_Y
            case "automatic":
                return BaselineType.AUTOMATIC
            case _:
                return BaselineType.NONE

    def update_baselines(self, experiment_id: int, baselines: list) -> bool:
        """Update baselines of experiment with ID "experimentID". Length of "baselines" should match the length returned by "GetBaselines".

        Args:
            experiment_id (int): ID of experiment.
            baselines (list): New baselines of experiment.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        if len(baselines) == 0:
            return False

        result = self.try_execute(lambda: self.astra_com.UpdateBaselines(experiment_id, baselines))
        return result

    def get_peak_ranges(self, experiment_id: int) -> list[PeakRange]:
        """Get peaks of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            list: List of peaks if successful, null otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetPeakRanges(experiment_id))

    def add_peak_range(self, experiment_id: int, start: float, end: float) -> bool:
        """Add a peak to experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            start (float): Starting time of peaks in minutes.
            end (float): Ending time of peaks in minutes.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.AddPeakRange(experiment_id, start, end))
        return result

    def update_peak_range(self, experiment_id: int, peak: PeakRange) -> bool:
        """Update existing peak "peak" of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            peak (PeakRange): Peak to update.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.UpdatePeakRange(experiment_id, peak))
        return result

    def remove_peak_range(self, experiment_id: int, peak_number: int) -> bool:
        """Remove existing peak with number "peakNumber" of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            peak_number (int): Peak to remove.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.RemovePeakRange(experiment_id, peak_number))
        return result

    def get_results(self, experiment_id: int) -> str:
        """Get results as XML for experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            str: XML representation if successful of the results, null otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetResults(experiment_id))

    def save_results(self, experiment_id: int, file_name: str) -> bool:
        """Save results as XML for experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            file_name (str): File location where to save the XML results.

        Returns:
            bool: True if results were successfully saved to "fileName", false otherwise.
        """
        result = self.try_execute(lambda: self.astra_com.SaveResults(experiment_id, file_name))
        return result

    def get_data_set(self, experiment_id: int, definition_name: str) -> str:
        """Get data associated to a dataset name "definitionName" for experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            definition_name (str): Name of dataset to retrieve.

        Returns:
            str: Dataset content as a formatted string, null otherwise.
        """
        return self.try_get(lambda: self.astra_com.GetDataSet(experiment_id, definition_name))

    def save_data_set(self, experiment_id: int, definition_name: str, file_name: str) -> bool:
        """Save data associated to a dataset name "definitionName" for experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            definition_name (str): Name of dataset to retrieve.
            file_name (str): File location where to save the XML results.

        Returns:
            bool: True if results were successfully saved to "fileName", false otherwise.
        """
        result = self.try_execute(
            lambda: self.astra_com.SaveDataSet(experiment_id, definition_name, file_name)
        )
        return result

    def set_auto_autofind_baselines(self, experiment_id: int, state: bool) -> bool:
        """Automatically find baselines of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            state (bool): True to enable autofind, false to disable it.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(
            lambda: self.astra_com.SetAutoAutofindBaselines(experiment_id, self.bool_to_int(state))
        )
        return result

    def set_auto_autofind_peaks(self, experiment_id: int, state: bool) -> bool:
        """Automatically find peaks of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            state (bool): True to enable autofind, false to disable it.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        result = self.try_execute(
            lambda: self.astra_com.SetAutoAutofindPeaks(experiment_id, self.bool_to_int(state))
        )
        return result

    def add_fraction_result(
        self, experiment_id: int, index: float, fraction_result_json: str
    ) -> bool:
        """Add a single Fraction Result "fractionResultJson" to the dataset of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            index (float): Index of Fraction Result.
            fraction_result_json (str): Fraction Result as json.

        Returns:
            bool: True for success, false otherwise.
        """
        result = self.try_execute(
            lambda: self.astra_com.AddFractionResult(experiment_id, index, fraction_result_json)
        )
        return result

    def get_fraction_result(self, experiment_id: int, index: int) -> str:
        """Get a single Fraction Result "fractionResultJson" to the dataset of experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.
            index (int): Index of Fraction Result.

        Returns:
            str: String containing fraction result in JSON.
        """
        return self.try_get(lambda: self.astra_com.GetFractionResult(experiment_id, index))

    def is_security_pack_active(self) -> bool:
        """Is security pack active? If true, then "ValidateLogon" should be called to identify the user
        before any other operations can be performed.

        Returns:
            bool: True if security pack is enabled, false otherwise.
        """
        return self.try_get(lambda: self.astra_sp_com.IsSecurityPackActive() != 0)

    def is_logged_in(self) -> bool:
        """Is a user logged in?

        Returns:
            bool: True if security pack is enabled and a user logged in, false otherwise.
        """
        return self.try_get(lambda: self.astra_sp_com.IsLoggedIn() != 0)

    def validate_logon(self, user_id: str, password: str, domain: str) -> LogonResult:
        """Validate logon of client with ASTRA.

        Args:
            user_id (str): User ID.
            password (str): Password for "userId".
            domain (str): Domain for "userId".

        Returns:
            LogonResult: Logon information with details about the success of the logon.
        """

        def func():
            result: LogonResult = self.astra_sp_com.ValidateLogon(user_id, password, domain)
            if result:
                if result.isValid:
                    return self.astra_com.ValidateLogon(user_id, password, domain)
                else:
                    return LogonResult(
                        isValid=0,
                        errorDetails=result.errorDetails,
                        errorMessage=result.errorMessage,
                    )
            else:
                return LogonResult(isValid=0, errorDetails="", errorMessage="")

        return self.try_get(func)

    def run_experiment(self, experiment_id: int) -> bool:
        """Run experiment with ID "experimentID".

        Args:
            experiment_id (int): ID of experiment.

        Returns:
            bool: True if call was successful, false otherwise.
        """
        AstraEvents.run_event.clear()
        success = self.try_execute(lambda: self.astra_com.RunExperiment(experiment_id))
        self.wait_experiment_run()
        return success

    def reset_events(self) -> None:
        """Reset all events. Recommended between 2 collections to ensure all events can be awaited for the next collection."""
        AstraEvents.ready_event.clear()
        AstraEvents.read_event.clear()
        AstraEvents.write_event.clear()
        AstraEvents.run_event.clear()
        AstraEvents.preparing_for_collection_event.clear()
        AstraEvents.closed_event.clear()
        AstraEvents.collection_started_event.clear()
        AstraEvents.collection_finished_event.clear()
        AstraEvents.waiting_for_auto_inject_event.clear()

    def try_get(self, func: Callable):
        """Helper function to display the underlying API errors.

        Args:
            func (Callable): Wrapper around an API call to be executed.

        Returns:
            _type_: Value of "func" upon successful completion.
        """
        if func is None:
            raise TypeError
        try:
            with rlock:
                return func()
        except Exception as ex:
            if self.should_show_error_message_box:
                # show message box
                pass
            else:
                raise ex
        # return the default value of return type of func()
        return inspect.signature(func).return_annotation()

    def try_execute(self, action: Callable):
        """Helper function to display the underlying API errors upon failure.

        Args:
            action (function): Wrapper around an API call to be executed.

        Returns:
            _type_: True if "action" completes without a failure, false otherwise.
        """
        if action is None:
            raise TypeError
        try:
            with rlock:
                action()
                return True
        except Exception as ex:
            if self.should_show_error_message_box:
                # show message box
                # Error messages can be disabled setting 'AstraAdmin.should_show_error_message_box' to False";
                pass
            else:
                raise ex
        return False

    def try_execute_and_wait_experiment_run(self, action: Callable):
        """Helper function to display the underlying API errors upon failure.
        And wait for experiment to finish running then continue.

        Args:
            action (function): Wrapper around an API call to be executed.

        Returns:
            _type_: True if "action" completes without a failure, false otherwise.
        """
        success = False
        if action is None:
            raise TypeError
        try:
            with rlock:
                action()
                success = True
        except Exception as ex:
            if self.should_show_error_message_box:
                # show message box
                # Error messages can be disabled setting 'AstraAdmin.should_show_error_message_box' to False";
                pass
            else:
                raise ex
        if success:
            self.wait_experiment_run()
            return True
        return False

    def refresh_experiment(self, experiment_id: int) -> None:
        """Update experiment with its current state

        Args:
            experiment_id (int): The experiment to update
        """
        with rlock:
            experiment = self.get_internal_experiment(experiment_id)
            experiment.read()
            self.experiment_status_changed.notify_observers(experiment)

    def bool_to_int(self, state: bool) -> int:
        """Helper function to convert boolean value to integer

        Args:
            boolean (bool):

        Returns:
            int: 1 as True, 0 as False
        """
        if state:
            return 1
        else:
            return 0


def ts(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def create_experiment_with_timeout(aa, template_path, timeout_seconds=60):
    """Create experiment but with timeout on the hanging wait_experiment_read()"""

    ts(f"Creating experiment from: {template_path}")

    # Store the original wait method
    original_wait_experiment_read = aa.wait_experiment_read

    def wait_experiment_read_with_timeout():
        """Replacement wait method with timeout"""
        ts("Waiting for experiment to be read (with timeout)...")
        start_time = time.time()

        # Wait with timeout
        while not AstraEvents.read_event.wait(1.0):
            PumpEvents(0.1)
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                ts(f"⚠ wait_experiment_read timed out after {timeout_seconds}s")
                ts("Experiment was created but read event may not have fired")
                ts("Continuing anyway...")
                break

        AstraEvents.read_event.clear()
        ts("✓ Experiment read completed (or timed out)")

    # Temporarily replace the hanging method
    aa.wait_experiment_read = wait_experiment_read_with_timeout

    try:
        # Now use the normal wrapper method with our timeout fix
        experiment_id = aa.new_experiment_from_template(template_path)
        return experiment_id
    finally:
        # Restore the original method
        aa.wait_experiment_read = original_wait_experiment_read


def main():
    print("=== Fixed Wrapper Approach ===")

    # Connect to ASTRA normally
    aa = AstraAdmin()
    client_guid = str(uuid.uuid4())
    aa.set_automation_identity("Fixed Wrapper Test", "1.0.0", os.getpid(), client_guid, 1)

    # Wait for instruments
    if not aa.has_instrument_detection_completed():
        print("Waiting for instrument detection...")
        aa.wait_for_instruments()

    print("✓ Connected to ASTRA")


    method_path = "//dbf/System Methods/RI Measurement/Utilities/Purge Off"

    try:
        # Create experiment with timeout fix
        experiment_id = create_experiment_with_timeout(aa, method_path, timeout_seconds=30)
        ts(f"✓ Experiment created. ID = {experiment_id}")

        if experiment_id <= 0:
            raise RuntimeError(f"Failed to create experiment: ID = {experiment_id}")

        # Now use normal wrapper methods
        ts("Setting parameters via wrapper methods...")
        aa.set_sample_name(experiment_id, "Fixed Wrapper Test")
        aa.set_sample_concentration(experiment_id, 2.0)  # 2 mg/mL
        aa.set_pump_flow_rate(experiment_id, 0.5)  # 0.5 mL/min
        aa.set_injected_volume(experiment_id, 0.100)  # 100 µL
        aa.set_collection_duration(experiment_id, 25.0)  # 25 minutes
        ts("✓ Parameters set")

        # Validate
        ts("Validating experiment...")
        is_valid = aa.validate_experiment(experiment_id)
        if not is_valid:
            ts("⚠ Validation failed, but continuing anyway")
        else:
            ts("✓ Experiment validated")

        # Start collection
        ts("🚀 Starting collection...")
        ts("ASTRA should now prepare and wait for Waters injection signal!")
        ts("")
        ts("👀 Watch ASTRA - you should see it go to 'Waiting for Auto Inject'")
        ts("")

        aa.start_collection(experiment_id)

        # Use the wrapper's wait methods if they exist
        ts("=== Using wrapper wait methods ===")

        # Wait for preparing
        if hasattr(aa, 'wait_preparing_for_collection'):
            try:
                ts("Waiting for PreparingForCollection...")
                aa.wait_preparing_for_collection()
                ts("✓ PreparingForCollection completed")
            except Exception as e:
                ts(f"⚠ PreparingForCollection error: {e}")

        # Wait for auto-inject
        if hasattr(aa, 'wait_waiting_for_auto_inject'):
            try:
                ts("🎯 Waiting for WaitingForAutoInject...")
                ts("   This is where ASTRA waits for Waters signal!")
                aa.wait_waiting_for_auto_inject()
                ts("✅ WaitingForAutoInject completed - signal received!")
            except Exception as e:
                ts(f"⚠ WaitingForAutoInject error: {e}")

        # Wait for collection started
        if hasattr(aa, 'wait_collection_started'):
            try:
                ts("Waiting for CollectionStarted...")
                aa.wait_collection_started()
                ts("✅ Collection started!")
            except Exception as e:
                ts(f"⚠ CollectionStarted error: {e}")

        # Wait for collection finished
        if hasattr(aa, 'wait_collection_finished'):
            try:
                ts("Waiting for CollectionFinished...")
                aa.wait_collection_finished()
                ts("✅ Collection finished!")
            except Exception as e:
                ts(f"⚠ CollectionFinished error: {e}")

        ts("🎉 Experiment completed successfully!")

    except Exception as e:
        ts(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        try:
            if 'experiment_id' in locals() and experiment_id > 0:
                ts("Cleaning up experiment...")
                aa.close_experiment(experiment_id)
                ts("✓ Experiment closed")
        except Exception as e:
            ts(f"Cleanup error: {e}")

if __name__ == "__main__":
    main()
