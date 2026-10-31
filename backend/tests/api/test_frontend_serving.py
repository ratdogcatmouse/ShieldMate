"""API tests for serving the built React app from FastAPI (main._serve_frontend).

The backend serves ``frontend/dist`` at ``/``: real files first, ``index.html`` for every other
non-API path (the React router owns /staff/*, /owner, /drill/* and /backstage), and a JSON 404
for ``/api/*`` misses. Most tests use a small fake ``dist`` in a temp folder, so they run
without a frontend build; the last one checks the real build when there is one.
"""
import re

import pytest

INDEX_HTML = '<!doctype html><html><body><div id="root"></div><script src="/assets/app.js"></script></body></html>'


@pytest.fixture
def fake_dist(tmp_path):
    """A minimal built frontend: index.html, one asset and one root-level file.

    ``secret.txt`` sits next to the dist folder, not inside it, so the path-traversal test
    has something outside the folder to try to reach.
    """
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML)
    (dist / "assets" / "app.js").write_text("console.log('shieldmate');")
    (dist / "robots.txt").write_text("User-agent: *")
    (tmp_path / "secret.txt").write_text("TOP-SECRET")
    return dist


@pytest.fixture
def web(make_app, fake_dist):
    """A TestClient for an app serving the fake dist."""
    return make_app(frontend_dist=fake_dist).client


def test_root_serves_the_app(web):
    r = web.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text


@pytest.mark.parametrize("path", ["/staff/1", "/owner", "/drill/1234", "/backstage", "/no/such/page"])
def test_client_side_routes_fall_back_to_index(web, path):
    # A phone that reloads or opens a deep link must still get the app, not a 404.
    r = web.get(path)
    assert r.status_code == 200
    assert r.text == INDEX_HTML


def test_assets_and_root_files_are_served_as_files(web):
    assets = web.get("/assets/app.js")
    assert assets.status_code == 200
    assert assets.text == "console.log('shieldmate');"
    # A real file at the dist root wins over the index.html fallback.
    robots = web.get("/robots.txt")
    assert robots.status_code == 200
    assert robots.text == "User-agent: *"


def test_missing_asset_is_a_404_not_the_app(web):
    # A broken script URL should fail loudly instead of returning HTML that the browser then
    # tries (and fails) to run as JavaScript.
    assert web.get("/assets/missing.js").status_code == 404


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/nope", "/api/alerts/not/a/route"])
def test_unknown_api_paths_are_json_404s(web, path):
    r = web.get(path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"] == "not_found"


def test_api_routes_are_not_shadowed_by_the_app(web):
    r = web.get("/api/status")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "alert_source" in r.json()


def test_path_traversal_cannot_read_files_outside_dist(web):
    # The encoded dots decode to "../secret.txt"; the server must answer with the app, not the file.
    for path in ("/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/%2e%2e/%2e%2e/secret.txt"):
        r = web.get(path)
        assert "TOP-SECRET" not in r.text, path


def test_without_a_build_the_api_still_works(make_app, tmp_path):
    # A fresh clone has no frontend/dist yet. The backend must start and serve /api anyway.
    h = make_app(frontend_dist=tmp_path / "not-built")
    assert h.get("/status").status_code == 200
    r = h.client.get("/")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_the_real_build_is_served_with_all_its_assets(make_app):
    """When ``frontend/dist`` exists (npm run build), every file its index.html loads is served."""
    h = make_app()                                   # default Config -> the real frontend/dist
    index = h.config.frontend_dist / "index.html"
    if not index.is_file():
        pytest.skip("frontend/dist is not built (run `make build`)")
    page = h.client.get("/")
    assert page.status_code == 200
    assert 'id="root"' in page.text
    urls = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page.text)
    assert urls, "the built index.html should load at least one /assets file"
    for url in urls:
        assert h.client.get(url).status_code == 200, url
