from fastapi import APIRouter, FastAPI


def register_routers(app: FastAPI) -> None:
    api_router = APIRouter(prefix="/api")

    @api_router.get("/healthz", tags=["공통"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
