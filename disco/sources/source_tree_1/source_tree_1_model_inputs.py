"""Implements functionality for QSTS inputs."""


from collections import namedtuple
import enum
import logging
import os
import re

from jade.jobs.job_inputs_interface import JobInputsInterface
from jade.exceptions import InvalidParameter
from jade.utils.utils import handle_file_not_found, handle_key_error, load_data
from disco.enums import get_placement_from_value


logger = logging.getLogger(__name__)


class SourceTree1ModelInputs(JobInputsInterface):
    """Implements functionality for Source Type 1 inputs."""

    _DEPLOYMENTS_DIR = "hc_pv_deployments"
    _DEPLOYMENT_FILENAME = "PVSystems.dss"
    _LOAD_SHAPES_FILENAME = "LoadShapes.dss"
    _KEYS_TYPE = namedtuple(
        "SourceTree1Keys", "substation, feeder, placement"
    )
    _PV_CONFIG_FILENAME = "pv_config.json"
    SUBSTATION_DELIMITER = "--"

    def __init__(self, base_directory):
        """Constructs SourceTree1ModelInputs.

        Parameters
        ----------
        base_directory : str

        """
        self._base = base_directory

        if not os.path.exists(self._base):
            raise InvalidParameter("inputs directory does not exist: {}"
                                   .format(self._base))

        self._parameters = self._parse_directories()
        logger.debug("Created %s at %s", self.__class__.__name__, self._base)

    @property
    def base_directory(self):
        return self._base

    def create_key(self, substation, feeder, placement):
        """Create a parameter key for accessing deployments and penetration
        levels.

        Parameters
        ----------
        substation : str
        feeder : str
        placement : Placement

        Returns
        -------
        namedtuple

        """
        return self._KEYS_TYPE._make((substation, feeder, placement))

    def get_available_parameters(self):
        """Return a dictionary containing all available parameters.

        Returns
        -------
        dict
            dictionary layout::
                {
                    (Substation, Feeder, Placement) : {
                        deployments: Set(
                            penetration_levels,
                        )
                    }
                }

        """
        return self._parameters

    def get_deployment_file(self, key, deployment, penetration_level):
        """Get the path to an input deployment file for the given parameters.

        Parameters
        ----------
        key : namedtuple
        deployment : int
        penetration_level : int

        Returns
        -------
        str
            full path to file

        """
        filename = os.path.join(
            self._base,
            key.substation,
            self._feeder_dirname(key.substation, key.feeder),
            self._DEPLOYMENTS_DIR,
            key.placement.value,
            str(deployment),
            str(penetration_level),
            self._DEPLOYMENT_FILENAME,
        )

        if not os.path.exists(filename):
            raise InvalidParameter(f"file does not exist: {filename}")
        return filename

    def get_dss_filename(self, substation, feeder, filename):
        """Return the path to DSS file.

        Parameters
        ----------
        substation : str
        feeder : str
        filename : str

        Returns
        -------
        str
            path to file

        Raises
        ------
        InvalidParameter
            Raised if the file does not exist.

        """
        dss_filename = os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
            filename,
        )

        if not os.path.exists(dss_filename):
            raise InvalidParameter(f"file does not exist: {dss_filename}")

        return dss_filename

    def get_loadshapes_filename(self, substation, feeder):
        """Return the path to the load shapes file.

        Parameters
        ----------
        feeder : str

        Returns
        -------
        str

        """
        return os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
            self._LOAD_SHAPES_FILENAME,
        )

    def get_opendss_directory(self, substation, feeder):
        """Return the path to the OpenDSS files.

        Parameters
        ----------
        feeder : str

        Returns
        -------
        str

        """
        return os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
        )

    def list_substations(self):
        """List available substations.

        Returns
        -------
        list of str
            available substations

        """
        return self._list_available_params("substation")

    def list_feeders(self):
        """List available feeders.

        Returns
        -------
        list of str
            available feeders

        """
        return self._list_available_params("feeder")

    def list_placements(self):
        """List available placements.

        Returns
        -------
        list of Placement
            available placements

        """
        return self._list_available_params("placement")

    @handle_key_error
    def list_deployments(self, key):
        """List available deployments.

        Parameters
        ----------
        key : namedtuple

        Returns
        -------
        list of int
            available deployments

        """
        deployments = list(self._parameters[key].keys())
        deployments.sort()
        return deployments

    @handle_key_error
    def list_penetration_levels(self, key, deployment):
        """List available penetration levels.

        Parameters
        ----------
        key : namedtuple
        deployment : int

        Returns
        -------
        list of int
            available penetration levels

        """
        levels = list(self._parameters[key][deployment])
        levels.sort()
        return levels

    def list_pv_configs(self, substation, feeder, placement, deployment):
        """Return the configurations for each PVSystem.
        Parameters
        ----------
        substation : str
        feeder : str
        placement : Placement
        deployment : int
        Returns
        -------
        list
        """
        return load_data(os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
            self._DEPLOYMENTS_DIR,
            placement.value,
            str(deployment),
            self._PV_CONFIG_FILENAME,
        ))["pv_systems"]

    @staticmethod
    def _get_items_from_directory(path):
        """Strips out miscellaneous files"""
        return [x for x in os.listdir(path)
                if os.path.isdir(os.path.join(path, x))]

    @staticmethod
    def _feeder_dirname(substation, feeder):
        return SourceTree1ModelInputs.SUBSTATION_DELIMITER.join((substation, feeder))

    @staticmethod
    def _feeder_from_dirname(dirname):
        fields = dirname.split(SourceTree1ModelInputs.SUBSTATION_DELIMITER)
        assert len(fields) == 2
        return fields[1]

    def _list_available_params(self, param):
        params = set()
        is_enum = False
        for key in self._parameters:
            value = key._asdict()[param]
            assert value is not None
            params.add(value)
            if isinstance(value, enum.Enum):
                is_enum = True

        key = None
        if is_enum:
            key = lambda x: x.value
        return sorted(list(params), key=key)

    @handle_file_not_found
    def _list_substations(self):
        return self._get_items_from_directory(self._base)

    @handle_file_not_found
    def _list_feeders(self, substation):
        feeder_path = os.path.join(self._base, substation)
        return [self._feeder_from_dirname(x) for x in
                self._get_items_from_directory(feeder_path)]

    @handle_file_not_found
    def _list_placements(self, substation, feeder):
        placement_path = os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
            self._DEPLOYMENTS_DIR,
        )
        if not os.path.exists(placement_path):
            return []

        placements = [get_placement_from_value(x)
                      for x in self._get_items_from_directory(placement_path)]
        placements.sort(key=lambda x: x.value)
        return placements

    @handle_file_not_found
    def _list_deployments(self, substation, feeder, placement):
        deployment_path = os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
            self._DEPLOYMENTS_DIR,
            placement.value,
        )
        deployments = self._get_items_from_directory(deployment_path)
        return sorted([int(x) for x in deployments])

    @handle_file_not_found
    def _list_penetration_levels(self, substation, feeder, placement, deployment):
        penetration_path = os.path.join(
            self._base,
            substation,
            self._feeder_dirname(substation, feeder),
            self._DEPLOYMENTS_DIR,
            placement.value,
            str(deployment),
        )

        levels = []
        regex = re.compile(r"^(\d+)$")
        for item in os.listdir(penetration_path):
            if not os.path.isdir(os.path.join(penetration_path, item)):
                continue
            match = regex.search(item)
            if match:
                levels.append(int(match.group(1)))

        levels.sort()
        return levels

    def _parse_directories(self):
        data = {}
        for substation in self._list_substations():
            self._parse_feeders(data, substation)

        return data

    def _parse_feeders(self, data, substation):
        for feeder in self._list_feeders(substation):
            self._parse_placements(data, substation, feeder)

    def _parse_placements(self, data, substation, feeder):
        for placement in self._list_placements(substation, feeder):
            self._parse_deployments(data, substation, feeder, placement)

    def _parse_deployments(self, data, substation, feeder, placement):
        key = self._KEYS_TYPE(substation, feeder, placement)
        data[key] = {}
        for deployment in self._list_deployments(substation, feeder, placement):
            data[key][deployment] = set()
            self._parse_penetrations(data[key][deployment], substation, feeder,
                                     placement, deployment)

    def _parse_penetrations(self, data, substation, feeder, placement,
                            deployment):
        for level in self._list_penetration_levels(substation, feeder, placement, deployment):
            data.add(level)
