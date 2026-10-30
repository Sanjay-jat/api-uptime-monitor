"""Regression index. One line per fixed bug: which test catches it now.

Tests live next to their feature, not copied here.
- 72-byte password crash       test_schemas::test_password_too_long_bytes
- token with non-numeric sub   test_auth::test_me_non_numeric_sub
- PATCH skipped SSRF await     test_endpoints::test_patch_private_url_rejected
- ping earlier than interval   test_scheduler_check::test_success_saves_ping_...
- WS bad token or non-JSON     test_ws::test_bad_first_message_closed_1008
- WS text after auth crash     test_ws::test_client_messages_after_auth_are_ignored
- double disconnect KeyError   test_ws_manager::test_double_disconnect_...
- webhook fixed HMAC key       test_alerts::test_sign_changes_with_secret
- purge placeholder swallowed  test_scheduler_purge::test_purge_uses_retention_days
- request log line twice       test_one_access_log_line_per_request
- DB connection held during ping  test_scheduler_check::test_no_open_transaction_while_pinging
- webhook reply body read into RAM  test_alerts_send::test_response_body_is_never_read
- webhook PUT had no rate limit   test_webhook::test_rate_limit_webhook_put_blocks_eleventh
- PATCH endpoint had no rate limit  test_endpoints::test_rate_limit_patch_blocks_eleventh
- prod image needed TEST_DATABASE_URL  test_config::test_test_database_url_is_optional
- timed-out WS client never closed  test_ws_manager::test_dead_socket_is_closed_...
- /health said ok with DB down  test_health_db::test_health_is_503_when_db_is_down
- JWT_SECRET length was not enforced  test_config::test_short_jwt_secret_is_rejected
- WS binary frame crashed route  test_ws::test_binary_message_after_auth_is_ignored
- shorter interval ignored by schedule  test_endpoints::test_patch_shorter_interval_...
- paused endpoint kept old status  test_endpoints::test_pause_removes_endpoint_from_status_cache
- webhook send held DB connection  test_alert_connection::test_no_open_transaction_...
- 429 had no Retry-After header  test_retry_after::test_429_has_retry_after_header
- expired refresh tokens never cleaned  test_token_purge::test_run_purge_also_cleans_...
- /auth/refresh had no rate limit  test_refresh_limit::test_refresh_is_rate_limited_per_
- refresh token had no max length  test_refresh_in::test_refresh_token_too_long_rejectedip
- .env.example secret passed validation  test_config::test_env_example_secret_is_not_usable
- empty DNS label gave 500  test_endpoints::test_create_url_with_empty_dns_label_is_422_not_500
- missing runtime deps         no pytest test. CI docker job catches it (import inside image).

Test below: httpx INFO log leaked the monitored URL query string.
"""

import logging

import httpx
import respx

from app import main  # noqa: F401  (import sets the httpx log level)


@respx.mock
async def test_httpx_does_not_log_url_with_secret_query(caplog):
    """httpx INFO log used to print full monitored URL, leaking ?token=..."""
    respx.get("https://example.com/").respond(200)
    caplog.set_level(logging.INFO)
    async with httpx.AsyncClient() as c:
        await c.get("https://example.com/?token=SECRET")
    assert "SECRET" not in caplog.text
