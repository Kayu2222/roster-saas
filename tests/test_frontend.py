"""The React app is served from the same origin without ever shadowing the API."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import register_frontend


def _site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app shell</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')")
    (tmp_path.parent / "secret.txt").write_text("do not serve")

    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    register_frontend(app, tmp_path)
    return TestClient(app)


def test_client_routes_get_the_app_shell(tmp_path):
    client = _site(tmp_path)
    for path in ["/", "/roster", "/roster/setup", "/people"]:
        res = client.get(path)
        assert res.status_code == 200 and "app shell" in res.text


def test_assets_are_served(tmp_path):
    assert "console.log" in _site(tmp_path).get("/assets/app.js").text


def test_api_routes_win_and_unknown_api_paths_404(tmp_path):
    client = _site(tmp_path)
    assert client.get("/api/ping").json() == {"pong": True}
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404 and "app shell" not in res.text


def test_no_files_outside_the_web_folder(tmp_path):
    res = _site(tmp_path).get("/..%2Fsecret.txt")
    assert "do not serve" not in res.text


def test_api_only_when_no_build(tmp_path):
    app = FastAPI()
    register_frontend(app, None)
    assert TestClient(app).get("/").status_code == 404
