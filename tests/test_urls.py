from datetime import UTC, datetime, timedelta


def _create(client, code="demo1", **extra):
    body = {"target_url": "https://example.com/path", "custom_code": code, **extra}
    return client.post("/api/urls", json=body)


def test_create_redirect_and_analytics(client):
    assert _create(client).status_code == 201
    redirect = client.get("/demo1", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.com/path"
    analytics = client.get("/api/urls/demo1/analytics").json()
    assert analytics["clicks"] == 1
    assert analytics["last_clicked_at"] is not None


def test_every_redirect_is_counted(client):
    _create(client)
    for _ in range(15):
        client.get("/demo1", follow_redirects=False)
    assert client.get("/api/urls/demo1").json()["clicks"] == 15


def test_generated_code_when_none_supplied(client):
    response = client.post("/api/urls", json={"target_url": "https://example.com"})
    assert response.status_code == 201
    assert len(response.json()["code"]) == 7
    assert response.json()["short_url"].endswith(response.json()["code"])


def test_duplicate_code_is_rejected(client):
    assert _create(client, "same1").status_code == 201
    assert _create(client, "same1").status_code == 409


def test_disabled_url_returns_gone(client):
    _create(client, "off11")
    assert client.delete("/api/urls/off11").status_code == 204
    assert client.get("/off11", follow_redirects=False).status_code == 410


def test_unknown_code_returns_404(client):
    assert client.get("/nothere", follow_redirects=False).status_code == 404


def test_past_expiry_is_rejected(client):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert _create(client, "old11", expires_at=past).status_code == 422


def test_expired_url_returns_gone(client):
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert _create(client, "exp11", expires_at=future).status_code == 201

    from app.core.database import SessionLocal
    from app.models.url import ShortURL

    with SessionLocal() as db:
        item = db.query(ShortURL).filter_by(code="exp11").one()
        item.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert client.get("/exp11", follow_redirects=False).status_code == 410


def test_non_http_scheme_is_rejected(client):
    response = client.post("/api/urls", json={"target_url": "ftp://example.com/file"})
    assert response.status_code == 422


def test_redirect_loop_to_own_host_is_rejected(client):
    response = client.post("/api/urls", json={"target_url": "http://localhost:8000/abc"})
    assert response.status_code == 422


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
