"""Base functionality for running PyDSS simulations."""

import abc
import copy
import logging
import os

from PyDSS.pydss_project import update_pydss_controllers
from PyDSS.pydss_project import PyDssProject, PyDssScenario

from jade.events import StructuredLogEvent, EVENT_CATEGORY_ERROR
from jade.jobs.job_execution_interface import JobExecutionInterface
from jade.loggers import log_event
from jade.utils.utils import dump_data
from jade.utils.timing_utils import timed_info
from disco.pydss.common import ConfigType
from disco.events import EVENT_NO_CONVERGENCE
from disco.models.base import PyDSSControllerModel
from disco.pydss.pydss_utils import detect_convergence_problems


logger = logging.getLogger(__name__)


class PyDssSimulationBase(JobExecutionInterface):
    """Runs a PyDss simulation."""

    _CONTROLLERS_FILENAME = "PvController.toml"
    _EXPORTS_FILENAME = "Exports.toml"
    _PYDSS_PROJECT_NAME = "pydss_project"

    def __init__(self,
                 pydss_inputs,
                 deployment_params,
                 output,
                 # TODO: these two parameters should be config options
                 # and add_pct_pmpp should be required to be passed
                 add_pct_pmpp=True,
                 irradiance_scaling_factor=100):
        """Constructs a PyDssSimulation.

        Raises
        ------
        InvalidParameter
            Raised if any parameter is invalid.

        """
        self._pydss_inputs = copy.deepcopy(pydss_inputs)
        self._model = deployment_params.model
        self._output = output
        self._run_dir = os.path.join(
            self._output,
            self._model.name,
        )
        self._logs_dir = os.path.join(
            self._run_dir,
            "logs",
        )
        self._pydss_project = None
        self._dss_dir = None
        self._results_dir = None
        self._add_pct_pmpp = add_pct_pmpp
        self._irradiance_scaling_factor = irradiance_scaling_factor

    @abc.abstractmethod
    def _get_deployment_input_path(self):
        """Return the full path to the user input deployment filename."""

    @abc.abstractmethod
    def _get_deployment_input_filename(self):
        """Return the user input deployment filename."""

    @abc.abstractmethod
    def _get_scenario_names(self):
        """Return the scenario name."""

    @staticmethod
    @abc.abstractmethod
    def _is_dss_file_path_absolute():
        """Return True if the deployment file path is absolute."""

    @abc.abstractmethod
    def _modify_open_dss_parameters(self):
        """Modify parameters in OpenDSS file; can be a no-op."""

    def _setup_pydss_project(self, verbose=False):
        if self._is_dss_file_path_absolute():
            deployment_filename = self._get_deployment_input_path()
        else:
            # PyDSS will join the directories with the name.
            deployment_filename = self._get_deployment_input_filename()

        dss_args = {
            "Plots": {
                "Create dynamic plots": False,
                "Open plots in browser": False,
            },
            "Project": {
                "Project Path": os.path.abspath(self._run_dir),
                "DSS File": deployment_filename,
                "Return Results": False,
                "DSS File Absolute Path": self._is_dss_file_path_absolute(),
            },
            "Logging": {
                "Logging Level": "DEBUG" if verbose else "INFO",
                "Log to external file": True,
                "Display on screen": False,
                "Clear old log file": True,
            },
        }

        simulation_config = self._pydss_inputs[ConfigType.SIMULATION_CONFIG]
        self._modify_pydss_simulation_params(simulation_config["Project"])

        for category, params in simulation_config.items():
            if category in dss_args:
                dss_args[category].update(params)
            else:
                dss_args[category] = params

        logger.info("PyDSS args: %s", dss_args)
        scenarios = self._make_pydss_scenarios()
        self._pydss_project = PyDssProject.create_project(
            os.path.join(self._run_dir),
            self._PYDSS_PROJECT_NAME,
            scenarios,
            options=dss_args,
            master_dss_file=dss_args["Project"]["DSS File"],
        )
        self._apply_pydss_controllers(
            project_path=self._pydss_project.project_path,
            scenario_names=[s.name for s in scenarios]
        )
        self._dss_dir = self._pydss_project.dss_files_path
        self._results_dir = [
            self._pydss_project.export_path(scenario_name)
            for scenario_name in self._get_scenario_names()
        ]

        logger.info("Setup folders at %s", self._run_dir)

        self._modify_open_dss_parameters()

    def _apply_pydss_controllers(self, project_path, scenario_names):
        """Update PyDSS controllers."""
        controllers = self._model.deployment.pydss_controllers
        if not controllers:
            return

        if isinstance(controllers, PyDSSControllerModel):
            controllers = [controllers]

        for controller in controllers:
            targets = controller.targets
            targets = targets or self._model.deployment.deployment_file
            if not isinstance(targets, list):
                targets = [targets]
            for scenario_name in scenario_names:
                for target in targets:
                    update_pydss_controllers(
                        project_path=project_path,
                        scenario=scenario_name,
                        controller_type=controller.controller_type.value,
                        controller=controller.name,
                        dss_file=target
                    )

    # TODO: not in use?
    def _get_pydss_scenarios(self):
        """Return a list of PyDssScenario objects."""
        return [
            PyDssScenario(x, exports=self._make_pydss_exports(x))
            for x in self._get_scenario_names()
        ]

    @abc.abstractmethod
    def _modify_pydss_simulation_params(self, config):
        pass

    def _make_pydss_exports(self, scenario):
        filename = os.path.join(self._run_dir, self._EXPORTS_FILENAME)
        dump_data(scenario["exports"], filename)
        return filename

    def _make_pydss_scenarios(self):
        # TODO DT: how does this create different exports per scenario?
        return [
            PyDssScenario(
                x["name"],
                exports=self._make_pydss_exports(x),
                post_process_infos=x["post_process_infos"],
            )
            for x in self._pydss_inputs[ConfigType.SCENARIOS]
        ]

    @property
    def pydss_project_path(self):
        if self._pydss_project is None:
            self._pydss_project = PyDssProject.load_project(
                os.path.join(self._run_dir, self._PYDSS_PROJECT_NAME)
            )
        return self._pydss_project.project_path

    @property
    def results_directory(self):
        return self._results_dir

    def list_results_files(self):
        results_files = {}
        scenario_names = self._get_scenario_names()
        for scenario_name, results_dir in zip(scenario_names, self._results_dir):
            if os.path.exists(results_dir):
                files = os.listdir(results_dir)
            else:
                # Exports may be disabled.
                files = []
            logger.debug("Results files: %s", files)
            results_files[scenario_name] = [os.path.join(results_dir, x) for x in files]
        return results_files

    def post_process(self, **kwargs):
        """Run post-processing on the output files."""

    @timed_info
    def run(self, verbose=False):
        """Runs the simulation."""
        self._setup_pydss_project()
        logger.info("Run simulation name=%s", self._model.name)
        logger.debug("Run simulation %s", self)

        orig_dir = os.getcwd()
        ret = 0
        try:
            self._pydss_project.run(logging_configured=False, zip_project=True)
            ret = self.check_convergence_problems()
            # TODO DT:
            ret = 0
        finally:
            os.chdir(orig_dir)

        self.list_results_files()
        return ret

    def check_convergence_problems(self):
        """Logs events for convergence errors."""
        problems = detect_convergence_problems(self._pydss_project.project_path)
        if not problems:
            return 0

        for problem in problems:
            event = StructuredLogEvent(
                source=self._model.name,
                category=EVENT_CATEGORY_ERROR,
                name=EVENT_NO_CONVERGENCE,
                message="Detected convergence problem in PyDSS log.",
                **problem,
            )
            log_event(event)

        logger.error("Job failed with %s convergence problems", len(problems))

        return 1
