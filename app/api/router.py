from fastapi import APIRouter
from app.api.files.router import router as files_router
from app.api.candidates.router import router as candidates_router

api_router = APIRouter()

api_router.include_router(files_router, prefix="/files", tags=["Files"])
api_router.include_router(candidates_router, prefix="/candidates", tags=["Candidates"])

