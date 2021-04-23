#!/usr/bin/env python

"""Creates JADE configuration for stage 1 of pydss_simulation pipeline."""

import logging
import os
import sys
from datetime import timedelta

import click

from jade.common import CONFIG_FILE
from jade.loggers import setup_logging
from jade.jobs.job_post_process import JobPostProcess
from jade.utils.utils import load_data
from PyDSS.reports.pv_reports import PF1_SCENARIO, CONTROL_MODE_SCENARIO

import disco
from disco.enums import SimulationType
from disco.extensions.pydss_simulation.pydss_configuration import PyDssConfiguration

ESTIMATED_EXEC_SECS_PER_JOB = 10

logger = logging.getLogger(__name__)


@click.command()
@click.argument("inputs")
@click.option(
    "-c", "--config-file",
    default=CONFIG_FILE,
    show_default=True,
    help="JADE config file to create",
)
@click.option(
    "-h", "--hosting-capacity",
    is_flag=True,
    default=False,
    show_default=True,
    help="Enable hosting capacity computations",
)
@click.option(
    "-i", "--impact-analysis",
    is_flag=True,
    default=False,
    show_default=True,
    help="Enable impact analysis computations",
)
@click.option(
    "--impact-analysis-inputs-filename",
    default=os.path.join(
        os.path.dirname(getattr(disco, "__path__")[0]),
        "disco",
        "analysis",
        "impact_analysis_inputs.toml",
    ),
    show_default=True,
    help="impact analysis inputs",
)
@click.option(
    "-e", "--exports-filename",
    default=os.path.join(
        os.path.dirname(getattr(disco, "__path__")[0]),
        "disco",
        "pydss",
        "config",
        "Exports.toml",
    ),
    show_default=True,
    help="PyDSS export options",
)
@click.option(
    "-r", "--reports-filename",
    default=os.path.join(
        os.path.dirname(getattr(disco, "__path__")[0]),
        "disco",
        "extensions",
        "pydss_simulation",
        "snapshot_reports.toml",
    ),
    show_default=True,
    help="PyDSS report options.",
)
@click.option(
    "--order-by-penetration/--no-order-by-penetration",
    default=False,
    show_default=True,
    help="Make jobs with higher penetration levels blocked by those with lower levels.",
)
@click.option(
    "--with-loadshape/--no-with-loadshape",
    default=False,
    show_default=True,
    help="Configure snapshot simulation with loashape profile."
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging",
)
def snapshot(
    inputs,
    config_file,
    hosting_capacity,
    impact_analysis,
    impact_analysis_inputs_filename,
    exports_filename,
    reports_filename,
    order_by_penetration=False,
    with_loadshape=False,
    verbose=False,
):
    """Create JADE configuration for snapshot simulations."""
    level = logging.DEBUG if verbose else logging.INFO
    setup_logging(__name__, None, console_level=level)

    if hosting_capacity and impact_analysis:
        print("hosting_capacity and impact_analysis cannot both be set")
        sys.exit(1)
    
    simulation_config = PyDssConfiguration.get_default_pydss_simulation_config()
    if with_loadshape:
        simulation_config["Project"]["Simulation Type"] = SimulationType.QSTS.value
        simulation_config["Reports"] = load_data(reports_filename)["Reports"]
        scenarios = [
            PyDssConfiguration.make_default_pydss_scenario(CONTROL_MODE_SCENARIO),
            PyDssConfiguration.make_default_pydss_scenario(PF1_SCENARIO),
        ]
    else:
        exports = {} if exports_filename is None else load_data(exports_filename)
        simulation_config["Project"]["Simulation Type"] = SimulationType.SNAPSHOT.value
        scenarios = [
            PyDssConfiguration.make_default_pydss_scenario(
                "scenario",
                exports=exports,
            )
        ]
    
    config = PyDssConfiguration.auto_config(
        inputs,
        simulation_config=simulation_config,
        scenarios=scenarios,
        order_by_penetration=order_by_penetration,
        estimated_exec_secs_per_job=ESTIMATED_EXEC_SECS_PER_JOB,
    )
    
    if with_loadshape:
        config = switch_snapshot_to_qsts(config)

    if hosting_capacity or impact_analysis:
        ia_inputs = load_data(impact_analysis_inputs_filename)
        config.add_user_data("impact_analysis_inputs", ia_inputs)

        ia_jobs = config.add_impact_analysis_jobs(SimulationType.SNAPSHOT)
        if hosting_capacity:
            config.add_hosting_capacity_job(SimulationType.SNAPSHOT, ia_jobs)

    config.dump(filename=config_file)
    print(f"Created {config_file} for Snapshot Analysis")


def switch_snapshot_to_qsts(config):
    """Use QSTS at one time point to perform SNAPSHOT simulation with loadshape profile"""
    for job in config.iter_pydss_simulation_jobs():
        job.model.simulation.simulation_type = SimulationType.QSTS
        job.model.simulation.end_time = job.model.simulation.start_time + timedelta(
            seconds=job.model.simulation.step_resolution
        )
    return config
