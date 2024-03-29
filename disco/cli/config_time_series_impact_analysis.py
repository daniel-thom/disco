#!/usr/bin/env python

"""Creates JADE configuration for stage 1 of pydss_simulation pipeline."""

import logging
import os
import sys

import click

from jade.common import CONFIG_FILE
from jade.loggers import setup_logging
from jade.jobs.job_post_process import JobPostProcess
from jade.utils.utils import load_data
from PyDSS.reports.pv_reports import PF1_SCENARIO, CONTROL_MODE_SCENARIO
import disco
from disco.enums import SimulationType
from disco.extensions.pydss_simulation.pydss_configuration import PyDssConfiguration

ESTIMATED_EXEC_SECS_PER_JOB = 3 * 60 * 60

logger = logging.getLogger(__name__)


@click.command()
@click.argument("inputs")
@click.option(
    "-c",
    "--config-file",
    default=CONFIG_FILE,
    show_default=True,
    help="JADE config file to create",
)
@click.option(
    "-r",
    "--reports-filename",
    default=os.path.join(
        os.path.dirname(getattr(disco, "__path__")[0]),
        "disco",
        "extensions",
        "pydss_simulation",
        "time_series_impact_analysis_reports.toml",
    ),
    show_default=True,
    help="PyDSS report options",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging",
)
def time_series_impact_analysis(
    inputs,
    config_file,
    reports_filename=None,
    verbose=False,
):
    """Create JADE configuration for time series impact analysis."""
    level = logging.DEBUG if verbose else logging.INFO
    setup_logging(__name__, None, console_level=level)
    post_process = JobPostProcess("disco.analysis", "TimeSeriesImpactAnalysis")

    simulation_config = PyDssConfiguration.get_default_pydss_simulation_config()
    simulation_config["Project"]["Simulation Type"] = SimulationType.QSTS.value
    simulation_config["Reports"] = load_data(reports_filename)["Reports"]

    scenarios = [
        PyDssConfiguration.make_default_pydss_scenario(PF1_SCENARIO),
        PyDssConfiguration.make_default_pydss_scenario(CONTROL_MODE_SCENARIO),
    ]
    config = PyDssConfiguration.auto_config(
        inputs,
        simulation_config=simulation_config,
        job_post_process=post_process,
        scenarios=scenarios,
        estimated_exec_secs_per_job=ESTIMATED_EXEC_SECS_PER_JOB,
    )

    config.dump(filename=config_file)
    print(f"Created {config_file} for TimeSeriesImpactAnalysis")
