from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import matrix_testutil as mtu


def test_api_empty_body():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert mtu.api("GET", "http://hs/x") == {}


def test_api_get_parses_json():
    payload = {"ok": True}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as urlopen:
        out = mtu.api("GET", "http://hs/_matrix/client/v3/foo", token="tok")
    assert out == payload
    req = urlopen.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer tok"


def test_login_returns_token():
    with patch("matrix_testutil.api", return_value={"access_token": "abc"}) as api:
        assert mtu.login("http://hs", "user", "pass") == "abc"
    assert api.call_args[0][0] == "POST"


def test_wait_member_timeout():
    with (
        patch("matrix_testutil.api", return_value={"joined": {}}),
        patch("matrix_testutil.time.sleep"),
    ):
        assert mtu.wait_member("http://hs", "t", "!r:ex", "@u:ex", 0.01) is False


def test_wait_member_success():
    with (
        patch("matrix_testutil.api", side_effect=[{"joined": {}}, {"joined": {"@u:ex": {}}}]),
        patch("matrix_testutil.time.sleep"),
    ):
        assert mtu.wait_member("http://hs", "t", "!r:ex", "@u:ex", 5.0) is True


def test_fetch_messages():
    chunk = [{"type": "m.room.message"}]
    with patch("matrix_testutil.api", return_value={"chunk": chunk}):
        assert mtu.fetch_messages("http://hs", "t", "!r:ex") == chunk
