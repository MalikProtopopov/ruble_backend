from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Health check", description="Проверка доступности сервиса")
async def health():
    return {"status": "ok"}
