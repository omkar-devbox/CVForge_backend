from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session
from app.api.students.schemas import StudentCreate, StudentResponse, StudentUpdate
from app.api.students.service import StudentService
from app.core.database import get_db
from app.utils.pagination import PaginatedResponse, PaginationParams
from app.utils.response import standard_response, StandardResponse

router = APIRouter()


@router.post(
    "",
    response_model=StandardResponse[StudentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new student record",
)
def create_student(
    student_in: StudentCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> StandardResponse[StudentResponse]:
    tenant_id = getattr(request.state, "tenant_id", None)
    service = StudentService(db)
    student = service.create_student(student_in, tenant_id=tenant_id)
    return standard_response(data=student, message="Student created successfully")


@router.get(
    "",
    response_model=StandardResponse[PaginatedResponse[StudentResponse]],
    summary="List paginated students",
)
def list_students(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    department: Optional[str] = Query(None, description="Filter by department"),
    db: Session = Depends(get_db),
) -> StandardResponse[PaginatedResponse[StudentResponse]]:
    tenant_id = getattr(request.state, "tenant_id", None)
    params = PaginationParams(page=page, page_size=page_size)
    service = StudentService(db)
    result = service.list_students(
        params=params, department=department, tenant_id=tenant_id
    )
    return standard_response(data=result)


@router.get(
    "/{student_id}",
    response_model=StandardResponse[StudentResponse],
    summary="Get student details by ID",
)
def get_student(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StandardResponse[StudentResponse]:
    tenant_id = getattr(request.state, "tenant_id", None)
    service = StudentService(db)
    student = service.get_student(student_id, tenant_id=tenant_id)
    return standard_response(data=student)


@router.put(
    "/{student_id}",
    response_model=StandardResponse[StudentResponse],
    summary="Update an existing student record",
)
def update_student(
    student_id: str,
    student_in: StudentUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> StandardResponse[StudentResponse]:
    tenant_id = getattr(request.state, "tenant_id", None)
    service = StudentService(db)
    updated = service.update_student(student_id, student_in, tenant_id=tenant_id)
    return standard_response(data=updated, message="Student updated successfully")


@router.delete(
    "/{student_id}",
    response_model=StandardResponse[None],
    summary="Delete a student record",
)
def delete_student(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StandardResponse[None]:
    tenant_id = getattr(request.state, "tenant_id", None)
    service = StudentService(db)
    service.delete_student(student_id, tenant_id=tenant_id)
    return standard_response(message="Student deleted successfully")

