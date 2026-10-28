from typing import Annotated

from fastapi import APIRouter, Depends

from app.llm.gateway import Gateway, get_gateway
from app.schemas.conversation import ModelResponse, ModelsResponse

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelsResponse)
async def list_models(gateway: Annotated[Gateway, Depends(get_gateway)]) -> ModelsResponse:
    return ModelsResponse(
        default=gateway.default_model,
        models=[ModelResponse(id=m.id, provider=m.provider) for m in gateway.list_models()],
    )
