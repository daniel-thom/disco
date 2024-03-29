import fileinput
import logging
import os
import re
import shutil
from abc import ABC, abstractmethod

from jade.exceptions import InvalidParameter
from disco.enums import AnalysisType, SimulationType
from disco.models.base import OpenDssDeploymentModel


SOURCE_CONFIGURATION_FILENAME = "configurations.json"

DEFAULT_SNAPSHOT_IMPACT_ANALYSIS_PARAMS = {
    "simulation_params": {
        "start_time": "2020-06-17T15:00:00",
        "end_time": "2020-06-17T15:00:00",
        "simulation_type": SimulationType.SNAPSHOT.value,
    },
}

DEFAULT_TIME_SERIES_IMPACT_ANALYSIS_PARAMS = {
    "model_params": {
        "pv_profile": None,
    },
    "simulation_params": {
        "start_time": "2020-06-17T15:00:00",
        "end_time": "2020-06-24T15:00:00",
        "simulation_type": SimulationType.QSTS.value,
        "step_resolution": 900,
    },
}

DEFAULT_UPGRADE_COST_ANALYSIS_PARAMS = {
    "model_params": {
        "cost_database": "DISCO_cost_database.xlsx",
        "params_file": "upgrade-params.toml",
        "sequential_upgrade": False,
        "nearest_redirect": False,
    },
    "simulation_params": {
        "start_time": "2020-06-17T15:00:00",
        "end_time": "2020-06-17T15:00:00",
        "simulation_type": SimulationType.SNAPSHOT.value,
    },
}

DEFAULT_SELECTIONS_BY_TYPE = {
    AnalysisType.SnapshotImpactAnalysis: DEFAULT_SNAPSHOT_IMPACT_ANALYSIS_PARAMS,
    AnalysisType.TimeSeriesImpactAnalysis: DEFAULT_TIME_SERIES_IMPACT_ANALYSIS_PARAMS,
    AnalysisType.UpgradeCostAnalysis: DEFAULT_UPGRADE_COST_ANALYSIS_PARAMS,
}

logger = logging.getLogger(__name__)


class BaseSourceDataModel(ABC):
    """Base class for source data models"""

    @staticmethod
    def get_default_transformation_selections(analysis_type):
        """Return default selections for a transformation.

        Parameters
        ----------
        analysis_type : AnalysisType

        Returns
        -------
        dict

        """
        defaults = DEFAULT_SELECTIONS_BY_TYPE.get(analysis_type)
        if defaults is None:
            raise InvalidParameter(f"{analysis_type} is not supported")

        return defaults

    @classmethod
    @abstractmethod
    def transform(cls, config, simulation_model, output_path):
        """Transform the input data to a DISCO data model.

        Parameters
        ----------
        config : dict
        simulation_model : BaseAnalysisModel
        output_path : str

        """


class BaseOpenDssModel(BaseSourceDataModel, ABC):
    """Base model for a single OpenDSS configuration"""

    @property
    @abstractmethod
    def substation(self):
        """The substation name"""

    @property
    @abstractmethod
    def feeder(self):
        """The feeder name"""

    @property
    @abstractmethod
    def dc_ac_ratio(self):
        """The DC/AC ratio"""

    @property
    def kva_to_kw_rating(self):
        """The kva_to_kw_rating"""
        return 1.0

    @property
    @abstractmethod
    def name(self):
        """The name of the deployment"""

    @property
    @abstractmethod
    def loadshape_directory(self):
        """The directory containing load shapes"""

    @property
    @abstractmethod
    def opendss_directory(self):
        """The directory of OpenDSS model"""

    @property
    @abstractmethod
    def master_file(self):
        """Master file of OpenDSS model"""

    @property
    def project_data(self):
        """PyDSS controllers"""
        return {}

    @property
    @abstractmethod
    def pydss_controllers(self):
        """PyDSS controllers"""

    @property
    @abstractmethod
    def pv_locations(self):
        """PV systems file of OpenDSS model."""

    def _create_common_files(self, workspace):
        """Create files common to all deployments.

        Parameters
        ----------
        workspace : OpenDssFeederWorkspace

        """
        self._copy_files(
            src_dir=self.opendss_directory,
            dst_dir=workspace.opendss_directory,
        )
        # This may overwrite a file copied above.
        shutil.copyfile(self.master_file, workspace.master_file)
        self._comment_out_solve(workspace.master_file)
        if self.loadshape_directory is not None:
            self._copy_files(
                src_dir=self.loadshape_directory,
                dst_dir=workspace.loadshape_directory,
            )

    @staticmethod
    def _comment_out_solve(filename):
        with fileinput.input(files=[filename], inplace=True) as f_in:
            for line in f_in:
                if line.lower().startswith("solve"):
                    line = "!" + line
                print(line, end="")

    def create_deployment(self, name, outdir, pv_profile=None):
        """Create the deployment.

        Parameters
        ----------
        name : str
            The deployment name
        outdir : str
            The base directory of opendss feeder model.
        pv_profile : str
            Optional load shape profile name to apply to all PVSystems

        Returns
        -------
        OpenDssDeploymentModel

        """
        workspace = OpenDssFeederWorkspace(outdir)
        if not os.path.exists(workspace.master_file):
            self._create_common_files(workspace)
        deployment_file = self._create_deployment_file(
            name, workspace, pv_profile=pv_profile)
        return OpenDssDeploymentModel.validate(
            dict(
                deployment_file=deployment_file,
                substation=self.substation,
                feeder=self.feeder,
                dc_ac_ratio=self.dc_ac_ratio,
                directory=outdir,
                kva_to_kw_rating=self.kva_to_kw_rating,
                project_data=self.project_data,
                pydss_controllers=self.pydss_controllers,
            )
        )

    @staticmethod
    def _copy_files(src_dir, dst_dir, exclude=None):
        """Copy files from src to dst directory.

        Parameters
        ----------
        src_dir : str
            Source directory
        dst_dir : str
            Destination directory
        exclude : list | str, optional
            Excluded file names from copy, by default None
        """
        if not exclude:
            exclude = []

        if isinstance(exclude, str):
            exclude = [exclude]

        for name in os.listdir(src_dir):
            if name in exclude or os.path.isdir(os.path.join(src_dir, name)):
                continue
            src_file = os.path.join(src_dir, name)
            dst_file = os.path.join(dst_dir, name)
            shutil.copyfile(src_file, dst_file)
            if os.path.splitext(dst_file)[1] in (".dss", ".txt"):
                BaseOpenDssModel.fix_data_file_references(os.path.abspath(src_dir), dst_file)

    def _create_deployment_file(self, name, workspace, pv_profile=None):
        """Create deployment dss file.

        Parameters
        ----------
        name : str
            Name of deployment.
        workspace : OpenDssFeederWorkspace
            Instance of OpenDssFeederWorkspace
        pv_profile : str | dict
            Optional load shape profile name to apply to PVSystems.
            If str, apply the name to all PVSystems.
            If dict, keys are PVSystem names and values are profile names.

        """
        deployment_file = os.path.join(workspace.pv_deployments_directory, name + ".dss")
        if not self.pv_locations:
            with open(deployment_file, "w") as fw:
                fw.write(f"Redirect {workspace.master_file}\n\n")
                fw.write("\nSolve\n")
            return deployment_file

        regex = re.compile(r"new pvsystem\.([^\s]+)")
        with open(deployment_file, "w") as fw, fileinput.input(self.pv_locations) as fr:
            fw.write(f"Redirect {workspace.master_file}\n\n")
            for line in fr:
                if pv_profile is not None:
                    lowered = line.lower()
                    if "new pvsystem" in lowered and "yearly" not in lowered:
                        if isinstance(pv_profile, str):
                            profile = pv_profile
                        else:
                            match = regex.search(lowered)
                            assert match, lowered
                            pv_system = match.group(1)
                            profile = pv_profile.get(pv_system)
                            if profile is None:
                                raise Exception(f"no profile found for {pv_system}")
                        line = line.strip() + f" yearly={profile}\n"
                fw.write(line)
            fw.write("\nSolve\n")

        return deployment_file

    @staticmethod
    def fix_data_file_references(src_dir, filename):
        """Change the path to any data file referenced in a .dss file to its
        absolute path."""
        # Example line:
        # New Loadshape.Residential1234 npts=123456 minterval=5 mult=[file=../BuildingData/Dataset_12_34/Residential/RES1234/LoadProfiles/12345.csv]
        regex = re.compile(r"file=([\.\w/\\-]+)")
        def replace_func(match):
            path = os.path.normpath(match.group(1).replace("\\", "/"))
            new_path = "file=" + os.path.normpath(os.path.join(src_dir, path))
            return new_path

        with fileinput.input(files=[filename], inplace=True) as f_in:
            for line in f_in:
                line = re.sub(regex, replace_func, line)
                print(line, end="")
                logger.debug("line=%s", line)

class OpenDssFeederWorkspace:
    """Defines a feeder and all dependent OpenDSS files."""
    def __init__(self, feeder_directory):
        #self._substation = substation
        self._feeder_directory = feeder_directory
        self._create_directories()

    def _create_directories(self):
        os.makedirs(self.feeder_directory, exist_ok=True)
        os.makedirs(self.loadshape_directory, exist_ok=True)
        os.makedirs(self.opendss_directory, exist_ok=True)
        os.makedirs(self.pv_deployments_directory, exist_ok=True)

    @property
    def feeder_directory(self):
        return self._feeder_directory

    @property
    def loadshape_directory(self):
        return os.path.join(self.feeder_directory, "LoadShapes")

    @property
    def opendss_directory(self):
        return os.path.join(self.feeder_directory, "OpenDSS")

    @property
    def pv_deployments_directory(self):
        return os.path.join(self.feeder_directory, "PVDeployments")

    @property
    def master_file(self):
        return os.path.join(self.opendss_directory, "Master.dss")
