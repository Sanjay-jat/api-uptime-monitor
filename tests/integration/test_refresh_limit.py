async def test_refresh_is_rate_limited_per_ip(client, rate_on):
    body = {"refresh_token": "x" * 43}
    for _ in range(20):
        r = await client.post("/auth/refresh", json=body)
        assert r.status_code == 401
    r = await client.post("/auth/refresh", json=body)
    assert r.status_code == 429
