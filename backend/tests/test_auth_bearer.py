"""Tests for Bearer JWT auth and login token response."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth.deps import _extract_bearer_token, get_current_user
from app.auth.session import UserSession
from app.auth.tokens import create_token, decode_token
from app.routes.auth import AuthLoginOut, LoginRequest, login


def _session() -> UserSession:
    return UserSession(
        uuid="11111111-2222-3333-4444-555555555555",
        login="gena",
        role="office",
        work_zones=[1, 2],
    )


class ExtractBearerTokenTests(unittest.TestCase):
    def test_extracts_bearer(self) -> None:
        self.assertEqual(_extract_bearer_token("Bearer abc.def"), "abc.def")
        self.assertEqual(_extract_bearer_token("bearer  xyz  "), "xyz")

    def test_rejects_non_bearer(self) -> None:
        self.assertIsNone(_extract_bearer_token(None))
        self.assertIsNone(_extract_bearer_token(""))
        self.assertIsNone(_extract_bearer_token("Basic abc"))
        self.assertIsNone(_extract_bearer_token("Bearer"))
        self.assertIsNone(_extract_bearer_token("Bearer "))


class GetCurrentUserBearerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = MagicMock()
        self.settings.auth_cookie_name = "monitor_session"
        self.settings.auth_secret_key = "test-secret-key-for-jwt-32bytes!!"
        self.settings.auth_token_ttl_hours = 12

    def _request(
        self,
        *,
        authorization: str | None = None,
        cookie: str | None = None,
    ) -> MagicMock:
        request = MagicMock()
        headers: dict[str, str] = {}
        if authorization is not None:
            headers["Authorization"] = authorization
        request.headers.get = lambda key, default=None: headers.get(key, default)
        cookies: dict[str, str] = {}
        if cookie is not None:
            cookies["monitor_session"] = cookie
        request.cookies.get = lambda key, default=None: cookies.get(key, default)
        return request

    @patch("app.auth.deps.get_settings")
    def test_prefers_bearer_over_cookie(self, get_settings_mock: MagicMock) -> None:
        get_settings_mock.return_value = self.settings
        with patch("app.auth.tokens.get_settings", return_value=self.settings):
            bearer = create_token(_session())
            cookie_session = UserSession(
                uuid="99999999-9999-9999-9999-999999999999",
                login="other",
                role="admin",
                work_zones=[],
            )
            cookie = create_token(cookie_session)
            request = self._request(
                authorization=f"Bearer {bearer}",
                cookie=cookie,
            )
            user = get_current_user(request)
        self.assertEqual(user.login, "gena")
        self.assertEqual(user.role, "office")

    @patch("app.auth.deps.get_settings")
    def test_falls_back_to_cookie(self, get_settings_mock: MagicMock) -> None:
        get_settings_mock.return_value = self.settings
        with patch("app.auth.tokens.get_settings", return_value=self.settings):
            cookie = create_token(_session())
            request = self._request(cookie=cookie)
            user = get_current_user(request)
        self.assertEqual(user.login, "gena")

    @patch("app.auth.deps.get_settings")
    def test_missing_credentials_401(self, get_settings_mock: MagicMock) -> None:
        get_settings_mock.return_value = self.settings
        request = self._request()
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(request)
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.auth.deps.get_settings")
    def test_invalid_bearer_401(self, get_settings_mock: MagicMock) -> None:
        get_settings_mock.return_value = self.settings
        request = self._request(authorization="Bearer not-a-jwt")
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(request)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Сессия", str(ctx.exception.detail))


class LoginTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = MagicMock()
        self.settings.auth_cookie_name = "monitor_session"
        self.settings.auth_secret_key = "test-secret-key-for-jwt-32bytes!!"
        self.settings.auth_token_ttl_hours = 12

    @patch("app.routes.auth.get_connection")
    @patch("app.routes.auth.authenticate")
    @patch("app.routes.auth.get_settings")
    def test_login_returns_token(
        self,
        get_settings_mock: MagicMock,
        authenticate_mock: MagicMock,
        get_connection_mock: MagicMock,
    ) -> None:
        get_settings_mock.return_value = self.settings
        authenticate_mock.return_value = _session()
        conn_cm = MagicMock()
        conn_cm.__enter__.return_value = MagicMock()
        conn_cm.__exit__.return_value = False
        get_connection_mock.return_value = conn_cm

        response = MagicMock()
        with patch("app.auth.tokens.get_settings", return_value=self.settings):
            result = login(LoginRequest(login="gena", password="x"), response)
            decoded = decode_token(result.token)

        self.assertIsInstance(result, AuthLoginOut)
        self.assertEqual(result.login, "gena")
        self.assertTrue(result.can_generate_letters)
        self.assertTrue(result.token)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.login, "gena")
        response.set_cookie.assert_called_once()
        cookie_kwargs = response.set_cookie.call_args.kwargs
        self.assertEqual(cookie_kwargs["value"], result.token)


if __name__ == "__main__":
    unittest.main()
