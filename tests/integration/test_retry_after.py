async def test_429_has_retry_after_header(client, rate_on):
    creds = {"email": "a@example.com", "password": "password123"}
    for _ in range(5):
        await client.post("/auth/login", json=creds)
    r = await client.post("/auth/login", json=creds)
    assert r.status_code == 429
    assert r.headers.get("retry-after") == "60"
