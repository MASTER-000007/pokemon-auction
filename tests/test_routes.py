from app import create_app, db

def test_home_and_room_creation(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}"})
    client = app.test_client()
    assert client.get("/").status_code == 200
    response = client.post("/api/rooms")
    assert response.status_code == 201
    code = response.get_json()["code"]
    assert client.get(f"/api/rooms/{code}").status_code == 200
