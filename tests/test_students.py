def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_student_crud(client):
    # 1. Create Student
    create_payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice.smith@university.edu",
        "phone": "+1234567890",
        "department": "Computer Science",
        "gpa": 3.85,
    }
    create_res = client.post("/api/v1/students", json=create_payload)
    assert create_res.status_code == 201
    created_student = create_res.json()["data"]
    student_id = created_student["id"]
    assert created_student["first_name"] == "Alice"

    # 2. List Students
    list_res = client.get("/api/v1/students")
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert list_data["meta"]["total"] == 1
    assert len(list_data["items"]) == 1

    # 3. Get Student by ID
    get_res = client.get(f"/api/v1/students/{student_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == student_id

    # 4. Update Student
    update_payload = {"gpa": 3.95, "department": "Data Science"}
    update_res = client.put(
        f"/api/v1/students/{student_id}", json=update_payload
    )
    assert update_res.status_code == 200
    assert update_res.json()["data"]["gpa"] == 3.95
    assert update_res.json()["data"]["department"] == "Data Science"

    # 5. Delete Student
    delete_res = client.delete(f"/api/v1/students/{student_id}")
    assert delete_res.status_code == 200

    # 6. Verify Deletion
    get_after_delete = client.get(f"/api/v1/students/{student_id}")
    assert get_after_delete.status_code == 404

