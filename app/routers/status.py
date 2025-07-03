from fastapi import APIRouter

status_router: APIRouter = APIRouter()


@status_router.get("/status")
def status() -> dict[str, str]:
    return {"status": "running"}
