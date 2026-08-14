from fastapi import APIRouter
from app.api.students.router import router as students_router

api_router = APIRouter()

api_router.include_router(students_router, prefix="/students", tags=["Students"])

