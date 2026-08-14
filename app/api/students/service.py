from typing import Optional
from sqlalchemy.orm import Session
from app.api.students.schemas import StudentCreate, StudentResponse, StudentUpdate
from app.core.exceptions import NotFoundException, ValidationException
from app.models.student import Student
from app.repositories.student import StudentRepository
from app.utils.pagination import create_paginated_response, PaginatedResponse, PaginationParams


class StudentService:
    def __init__(self, db: Session):
        self.student_repo = StudentRepository(db)

    def create_student(
        self, student_in: StudentCreate, tenant_id: Optional[str] = None
    ) -> StudentResponse:
        existing = self.student_repo.get_by_email(student_in.email)
        if existing:
            raise ValidationException(
                message=f"Student with email '{student_in.email}' already exists."
            )

        effective_tenant = tenant_id or student_in.tenant_id
        student = Student(
            first_name=student_in.first_name,
            last_name=student_in.last_name,
            email=student_in.email,
            phone=student_in.phone,
            department=student_in.department,
            gpa=student_in.gpa,
            tenant_id=effective_tenant,
        )
        created = self.student_repo.create(student)
        return StudentResponse.model_validate(created)

    def get_student(
        self, student_id: str, tenant_id: Optional[str] = None
    ) -> StudentResponse:
        student = self.student_repo.get_by_id(student_id, tenant_id=tenant_id)
        if not student:
            raise NotFoundException(resource="Student", identifier=student_id)
        return StudentResponse.model_validate(student)

    def list_students(
        self,
        params: PaginationParams,
        department: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> PaginatedResponse[StudentResponse]:
        students, total = self.student_repo.list_paginated(
            skip=params.skip,
            limit=params.page_size,
            department=department,
            tenant_id=tenant_id,
        )
        student_responses = [StudentResponse.model_validate(s) for s in students]
        return create_paginated_response(
            items=student_responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    def update_student(
        self,
        student_id: str,
        student_in: StudentUpdate,
        tenant_id: Optional[str] = None,
    ) -> StudentResponse:
        student = self.student_repo.get_by_id(student_id, tenant_id=tenant_id)
        if not student:
            raise NotFoundException(resource="Student", identifier=student_id)

        update_data = student_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(student, field, value)

        updated = self.student_repo.update(student)
        return StudentResponse.model_validate(updated)

    def delete_student(
        self, student_id: str, tenant_id: Optional[str] = None
    ) -> None:
        student = self.student_repo.get_by_id(student_id, tenant_id=tenant_id)
        if not student:
            raise NotFoundException(resource="Student", identifier=student_id)
        self.student_repo.delete(student)
