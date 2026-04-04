import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.urls import reverse

from config.views import healthcheck


@pytest.mark.django_db
class TestHealthcheckView:
    def test_returns_200_when_database_is_available(self, client):
        response = client.get(reverse("healthcheck"))

        assert response.status_code == 200

    def test_returns_ok_status_when_database_is_available(self, client):
        response = client.get(reverse("healthcheck"))
        data = json.loads(response.content)

        assert data["status"] == "ok"
        assert data["database"] == "ok"

    def test_returns_503_when_database_is_unavailable(self):
        from django.db.utils import OperationalError

        factory = RequestFactory()
        request = factory.get("/health/")

        with patch("config.views.connections") as mock_connections:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(side_effect=OperationalError)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_connections.__getitem__.return_value.cursor.return_value = mock_cursor

            response = healthcheck(request)

        assert response.status_code == 503

    def test_returns_error_status_when_database_is_unavailable(self):
        from django.db.utils import OperationalError

        factory = RequestFactory()
        request = factory.get("/health/")

        with patch("config.views.connections") as mock_connections:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(side_effect=OperationalError)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_connections.__getitem__.return_value.cursor.return_value = mock_cursor

            response = healthcheck(request)

        data = json.loads(response.content)
        assert data["status"] == "error"
        assert data["database"] == "unavailable"

    def test_response_is_json(self, client):
        response = client.get(reverse("healthcheck"))

        assert response["Content-Type"] == "application/json"
