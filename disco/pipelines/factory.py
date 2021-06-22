from jade.utils.utils import load_data
from disco.pipelines.base import PipelineTemplate
from disco.pipelines.creator import SnapshotPipelineCreator, TimeSeriesPipelineCreator
from disco.pipelines.enums import SimulationType
from disco.sources.factory import make_source_model


PIPELINE_CREATOR_MAPPING = {
    SimulationType.SNAPSHOT: SnapshotPipelineCreator,
    SimulationType.TIME_SERIES: TimeSeriesPipelineCreator
}


class PipelineCreatorFactory:
    """Factory class for getting pipeline creator"""
    
    @classmethod
    def create(cls, template_file):
        """Create pipeline creator"""
        template = PipelineTemplate(template_file)
        simulation_type = SimulationType(template.data["simulation_type"])
        pipeline_creator_class = PIPELINE_CREATOR_MAPPING[simulation_type]
        pipeline_creator = pipeline_creator_class(template_file)
        return pipeline_creator