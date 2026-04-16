from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dashboard_route_returns_html():
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Autonomous Repair Agent" in response.text


def test_ui_alias_route_returns_html():
    response = client.get("/ui")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
