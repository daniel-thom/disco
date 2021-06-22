import logging
import os

import disco
from disco.pipelines.enums import AnalysisType, TemplateSection
from disco.pipelines.base import PipelineCreatorBase
from jade.models.pipeline import PipelineConfig

logger = logging.getLogger(__name__)


# NOTE: If user needs to customize these configs, then make them to be click options.
REPORTS_FILENAME = os.path.join(
    os.path.dirname(getattr(disco, "__path__")[0]),
    "disco",
    "extensions",
    "pydss_simulation",
    "snapshot_reports.toml",
)
EXPORTS_FILENAME = os.path.join(
    os.path.dirname(getattr(disco, "__path__")[0]),
    "disco",
    "pydss",
    "config",
    "Exports.toml",
)


class SnapshotPipelineCreator(PipelineCreatorBase):

    def create_pipeline(self, config_file):
        """Make snapshot pipeline config file"""
        stages = [self.make_simulation_stage()]
        if self.template.contains_postprocess():
            stages.append(self.make_postprocess_stage())
        
        config = PipelineConfig(stages=stages, stage_num=1)
        with open(config_file, "w") as f:
            f.write(config.json(indent=2))
        logger.info("Created pipeline config file - %s", config_file)

    def make_model_transform_command(self):
        options = self.template.get_transform_options(TemplateSection.MODEL)
        command = f"disco transform-model {self.template.inputs} snapshot {options}"
        logger.info("Make command - '%s'", command)
        return command

    def make_disco_config_command(self, section):
        if self.template.preconfigured:
            model_inputs = self.template.inputs
        else:
            model_inputs = self.template.get_model_transform_output()
        options = self.template.get_config_options(section)
        command = (
            f"disco config snapshot {model_inputs} "
            f"--reports-filename={REPORTS_FILENAME} --exports-filename={EXPORTS_FILENAME} {options}"
        )
        return command
    
    def make_prescreen_create_command(self):
        pass
    
    def make_prescreen_filter_command(self):
        pass
    
    def make_postprocess_command(self):
        command = ""
        impact_analysis = self.template.analysis_type == AnalysisType.IMAPCT_ANALYSIS.value
        hosting_capacity = self.template.analysis_type == AnalysisType.HOSTING_CAPACITY.value
        if impact_analysis or hosting_capacity:
            inputs = os.path.join("$JADE_PIPELINE_OUTPUT_DIR", f"output-stage{self.stage_num-1}")
            command += f"disco-internal make-summary-tables {inputs}"
            if hosting_capacity:
                config_params = self.template.get_config_params(TemplateSection.SIMULATION)
                with_loadshape = config_params["with_loadshape"]
                pf1 = config_params["pf1"]
                if with_loadshape:
                    command += f"\ndisco-internal compute-hosting-capacity {inputs} --scenario=control_mode"
                    if pf1:
                        command += f"\ndisco-internal compute-hosting-capacity {inputs} --scenario=pf1"
                else:
                    command += f"\ndisco-internal compute-hosting-capacity {inputs} --scenario=scenario"
        return command


class TimeSeriesPipelineCreator(PipelineCreatorBase):
    """Time-series pipeline creator class"""

    def create_pipeline(self, config_file):
        """Make time-series pipeline config file"""
        stages = []
        if self.template.contains_prescreen():
            stages.append(self.make_prescreen_stage())
        stages.append(self.make_simulation_stage())
        if self.template.contains_postprocess():
            stages.append(self.make_postprocess_stage())
        
        config = PipelineConfig(stages=stages, stage_num=1)
        with open(config_file, "w") as f:
            f.write(config.json(indent=2))
        logger.info("Created pipeline config file - %s", config_file)

    def make_model_transform_command(self):
        options = self.template.get_transform_options(TemplateSection.MODEL)
        command = f"disco transform-model {self.template.inputs} time-series {options}"
        logger.info("Make command - '%s'", command)
        return command

    def make_disco_config_command(self, section):
        if self.template.preconfigured:
            model_inputs = self.template.inputs
        else:
            model_inputs = self.template.get_model_transform_output()
        options = self.template.get_config_options(section)
        command = (
            f"disco config time-series {model_inputs} "
            f"--reports-filename={REPORTS_FILENAME} {options}"
        )
        logger.info("Make command - '%s'", command)
        return command

    def make_prescreen_create_command(self):
        config_params = self.template.get_config_params(TemplateSection.PRESCREEN)
        config_file = config_params["config_file"]
        prescreen_params = self.template.get_prescreen_params(TemplateSection.PRESCREEN)
        command = (
            f"disco prescreen-pv-penetration-levels {config_file} "
            f"create --config-file={prescreen_params['prescreen_config_file']}"
        )
        logger.info("Make command - '%s'", command)
        return command

    def make_prescreen_filter_command(self):
        config_params = self.template.get_config_params(TemplateSection.PRESCREEN)
        config_file = config_params["config_file"]
        
        prescreen_params = self.template.get_prescreen_params(TemplateSection.PRESCREEN)
        prescreen_output = os.path.join("$JADE_PIPELINE_OUTPUT_DIR", f"output-stage{self.stage_num-1}")
        command = (
            f"disco prescreen-pv-penetration-levels {config_file} "
            f"filter-config {prescreen_output} "
            f"--config-file={prescreen_params['filtered_config_file']}"
        )
        logger.info("Make command - '%s'", command)
        return command

    def make_postprocess_command(self):
        command = ""
        impact_analysis = self.template.analysis_type == AnalysisType.IMAPCT_ANALYSIS.value
        hosting_capacity = self.template.analysis_type == AnalysisType.HOSTING_CAPACITY.value
        if impact_analysis or hosting_capacity:
            inputs = os.path.join("$JADE_PIPELINE_OUTPUT_DIR", f"output-stage{self.stage_num-1}")
            command += f"disco-internal make-summary-tables {inputs}"
            if hosting_capacity:
                command += f"\ndisco-internal compute-hosting-capacity {inputs} --scenario=control_mode"
        return command