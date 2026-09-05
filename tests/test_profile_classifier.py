"""Unit tests for Candidate ProfileClassifier."""

import pytest
from app.services.file_manifest.profile_classifier import ProfileClassifier
from app.services.file_manifest.schemas import (
    EducationItem,
    ExperienceItem,
    ExtractedDocument,
)


def test_mechanical_classification_with_cad_tools():
    doc = ExtractedDocument(
        file_name="mechanical_resume.pdf",
        file_stem="mechanical_resume",
        name="Sunil Patil",
        email=["sunil.patil@example.com"],
        skills=["ActCAD", "AutoCAD", "SolidWorks", "CATIA", "GD&T", "CNC Programming"],
        experience=[
            ExperienceItem(
                role="Mechanical Design Engineer",
                company="Kirloskar Brothers",
                duration="2021 - Present",
                highlights=["Drafted 3D CAD models and sheet metal enclosures using ActCAD and SolidWorks"],
            )
        ],
        education=[
            EducationItem(
                degree="B.E. Mechanical Engineering",
                institution="Government College of Engineering Pune",
                duration="2021",
            )
        ],
    )
    result = ProfileClassifier.classify(doc)
    assert result["overall_profile"] == "Mechanical"
    assert result["name"] == "Sunil Patil"
    assert result["email"] == "sunil.patil@example.com"
    assert "Mechanical Design Engineer" in (result["role"] or "")
    assert "Mechanical Engineering" in (result["education"] or "")


def test_software_classification():
    doc = ExtractedDocument(
        file_name="software_engineer.pdf",
        file_stem="software_engineer",
        name="Sneha Kulkarni",
        email=["sneha@example.com"],
        skills=["Python", "FastAPI", "React", "PostgreSQL", "Docker", "Git"],
        experience=[
            ExperienceItem(
                role="Backend Developer",
                company="Cognizant",
                duration="2022 - 2024",
                highlights=["Built RESTful microservices architecture"],
            )
        ],
        education=[
            EducationItem(
                degree="B.Tech Computer Science",
                institution="VJTI Mumbai",
                duration="2022",
            )
        ],
    )
    result = ProfileClassifier.classify(doc)
    assert result["overall_profile"] == "Software"
    assert result["name"] == "Sneha Kulkarni"
    assert "Backend Developer" in (result["role"] or "")


def test_civil_classification():
    doc = ExtractedDocument(
        file_name="civil_engineer.pdf",
        file_stem="civil_engineer",
        name="Ramesh Joshi",
        email=["ramesh@example.com"],
        skills=["STAAD Pro", "Revit", "AutoCAD Civil", "RCC Design", "BIM"],
        experience=[
            ExperienceItem(
                role="Structural Site Engineer",
                company="Shapoorji Pallonji",
                duration="2019 - Present",
                highlights=["Managed structural concrete casting and reinforcement verification"],
            )
        ],
        education=[
            EducationItem(
                degree="B.E. Civil Engineering",
                institution="MIT Pune",
                duration="2019",
            )
        ],
    )
    result = ProfileClassifier.classify(doc)
    assert result["overall_profile"] == "Civil"


def test_electrical_classification():
    doc = ExtractedDocument(
        file_name="electrical_engineer.pdf",
        file_stem="electrical_engineer",
        name="Nitin Deshmukh",
        email=["nitin@example.com"],
        skills=["PLC", "SCADA", "MATLAB", "Switchgear", "Substation", "Electrical CAD"],
        experience=[
            ExperienceItem(
                role="Electrical Control Engineer",
                company="Siemens",
                duration="2021 - Present",
                highlights=["Programmed Allen Bradley PLCs and commissioned SCADA systems"],
            )
        ],
        education=[
            EducationItem(
                degree="B.E. Electrical Engineering",
                institution="COEP Pune",
                duration="2021",
            )
        ],
    )
    result = ProfileClassifier.classify(doc)
    assert result["overall_profile"] == "Electrical"


def test_data_science_classification():
    doc = ExtractedDocument(
        file_name="data_scientist.pdf",
        file_stem="data_scientist",
        name="Ananya Roy",
        email=["ananya@example.com"],
        skills=["Machine Learning", "PyTorch", "NLP", "Pandas", "Computer Vision", "Tableau"],
        experience=[
            ExperienceItem(
                role="Data Scientist",
                company="Fractal Analytics",
                duration="2022 - Present",
                highlights=["Trained transformer models for automated document classification"],
            )
        ],
        education=[
            EducationItem(
                degree="M.Tech Data Science",
                institution="IIT Bombay",
                duration="2022",
            )
        ],
    )
    result = ProfileClassifier.classify(doc)
    assert result["overall_profile"] == "Data Science"
