from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
from vqec.server.models.schemas import RegistryComponent, ValidateExperimentRequest, ValidateExperimentResponse
from vqec.server.services import registry as registry_service
from vqec.core.experiment import Experiment, ExperimentConfig
from vqec.core.validator import CompatibilityError

router = APIRouter()

@router.get("", response_model=Dict[str, List[str]])
async def get_registry():
    return registry_service.get_all_components()

@router.get("/{category}", response_model=List[RegistryComponent])
async def get_registry_category(
    category: str,
    circuit_constructor: str = None,
    noise_model: str = None,
    runner: str = None,
    limit: int = 100,
    offset: int = 0
):
    comps = registry_service.get_category_components(
        category, circuit_constructor, noise_model, runner, limit, offset
    )
    if comps is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return comps

@router.get("/{category}/{component_name}", response_model=RegistryComponent)
async def get_registry_component(category: str, component_name: str):
    comp = registry_service.get_component_detail(category, component_name)
    if comp is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return comp

@router.post("/validate-experiment", response_model=ValidateExperimentResponse)
async def validate_experiment(request: ValidateExperimentRequest):
    try:
        config = ExperimentConfig.model_validate(request.config)
        exp = Experiment(config)
        exp.validate_compatibility()
        jobs = exp.expand_jobs()
        return ValidateExperimentResponse(valid=True, jobs_count=len(jobs))
    except CompatibilityError as e:
        return ValidateExperimentResponse(valid=False, jobs_count=0, error=str(e))
    except Exception as e:
        return ValidateExperimentResponse(valid=False, jobs_count=0, error=str(e))
