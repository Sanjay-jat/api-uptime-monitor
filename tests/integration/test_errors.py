async def test_validation_error_shape(client):
    r = await client.post("/auth/register", json={"email": "a@example.com", "password": "zq9xk"})
    assert r.status_code == 422
    body = r.json()
    assert list(body) == ["detail"]
    assert body["detail"]
    for item in body["detail"]:
        assert set(item) == {"loc", "msg"}


async def test_validation_error_does_not_echo_input(client):
    r = await client.post("/auth/register", json={"email": "a@example.com", "password": "zq9xk"})
    assert r.status_code == 422
    assert "zq9xk" not in r.text


async def test_malformed_json_is_422_same_shape(client):
    r = await client.post(
        "/auth/register", content=b"{bad", headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    body = r.json()
    assert list(body) == ["detail"]
    for item in body["detail"]:
        assert set(item) == {"loc", "msg"}


async def test_validation_error_has_request_id_header(client):
    r = await client.post("/auth/register", json={})
    assert r.status_code == 422
    assert r.headers["x-request-id"]


async def test_rate_limit_body_is_generic(client, rate_on):
    for i in range(5):
        await client.post(
            "/auth/register", json={"email": f"u{i}@x.com", "password": "pass-1234-ok"}
        )
    r = await client.post("/auth/register", json={"email": "u5@x.com", "password": "pass-1234-ok"})
    assert r.status_code == 429
    assert r.json() == {"detail": "Rate limit exceeded"}
    assert r.headers["x-request-id"]
    assert "per 1 minute" not in r.text
