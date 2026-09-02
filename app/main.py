from fastapi import Depends, FastAPI
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import get_current_user
from app.database import init_db
from app.routers import batches, inventory, settings

app = FastAPI(title="HighValley BrewLog")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/batches")


app.include_router(batches.router, dependencies=[Depends(get_current_user)])
app.include_router(inventory.router, dependencies=[Depends(get_current_user)])
app.include_router(settings.router, dependencies=[Depends(get_current_user)])
