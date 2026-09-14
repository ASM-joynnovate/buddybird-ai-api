from fastapi import FastAPI

from core.fastapi.listener import register_handlers
from core.fastapi.router import register_routers


def create_app() -> FastAPI:
    app_ = FastAPI(title="BuddyBird AI API", version="0.1.0")

    register_routers(app_)
    register_handlers(app_)

    return app_


app = create_app()
