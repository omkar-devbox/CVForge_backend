from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.student import Student


class StudentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, student_id: str, tenant_id: Optional[str] = None) -> Optional[Student]:
        query = self.db.query(Student).filter(Student.id == student_id)
        if tenant_id:
            query = query.filter(Student.tenant_id == tenant_id)
        return query.first()

    def get_by_email(self, email: str) -> Optional[Student]:
        return self.db.query(Student).filter(Student.email == email).first()

    def list_paginated(
        self,
        skip: int = 0,
        limit: int = 20,
        department: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[List[Student], int]:
        query = self.db.query(Student)
        if tenant_id:
            query = query.filter(Student.tenant_id == tenant_id)
        if department:
            query = query.filter(Student.department == department)

        total = query.count()
        students = query.offset(skip).limit(limit).all()
        return students, total

    def create(self, student: Student) -> Student:
        self.db.add(student)
        self.db.commit()
        self.db.refresh(student)
        return student

    def update(self, student: Student) -> Student:
        self.db.commit()
        self.db.refresh(student)
        return student

    def delete(self, student: Student) -> None:
        self.db.delete(student)
        self.db.commit()
