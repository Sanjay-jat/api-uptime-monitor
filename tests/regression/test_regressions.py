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
- missing runtime deps         no test. Found by hand (docker build). CI lacks it.

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
