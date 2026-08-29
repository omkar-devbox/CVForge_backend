from fastapi import APIRouter
from app.api.files.router import router as files_router
from app.api.students.router import router as students_router

api_router = APIRouter()

api_router.include_router(files_router, prefix="/files", tags=["Files & Manifest"])
api_router.include_router(students_router, prefix="/students", tags=["Students"])


