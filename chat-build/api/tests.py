from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


class AgentApiTests(APITestCase):
    def test_health_endpoint_legacy(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'ok')

    def test_health_endpoint_v1(self):
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'ok')

    def test_openapi_schema_is_available(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('openapi', response.data)

    def test_openapi_schema_has_auth_schemes(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        components = response.data.get('components', {})
        security_schemes = components.get('securitySchemes', {})
        self.assertIn('BearerAuth', security_schemes)
        self.assertIn('ApiKeyAuth', security_schemes)

    @override_settings(AGENT_API_KEY='test-key')
    def test_agent_query_requires_auth_header(self):
        response = self.client.post('/api/v1/agent/query/', {'question': 'Hello'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(AGENT_API_KEY='test-key')
    def test_agent_query_rejects_invalid_payload(self):
        response = self.client.post(
            '/api/v1/agent/query/',
            {'question': ''},
            format='json',
            HTTP_X_API_KEY='test-key',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @override_settings(AGENT_API_KEY='test-key')
    def test_agent_query_accepts_api_key(self):
        fake_service = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='ok', cache_hit=False)
        )
        with patch('api.views.SERVICE', fake_service):
            response = self.client.post(
                '/api/v1/agent/query/',
                {'question': 'What is new?', 'user_id': 'u-1'},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('answer'), 'ok')
        self.assertIn('request_id', response.data)

    @override_settings(AGENT_API_KEY='test-key')
    def test_agent_query_accepts_jwt(self):
        user_model = get_user_model()
        user_model.objects.create_user(username='agent-user', password='password123')

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'agent-user', 'password': 'password123'},
            format='json',
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access_token = token_response.data['access']

        fake_service = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='jwt-ok', cache_hit=True)
        )
        with patch('api.views.SERVICE', fake_service):
            response = self.client.post(
                '/api/v1/agent/query/',
                {'question': 'hello'},
                format='json',
                HTTP_AUTHORIZATION=f'Bearer {access_token}',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('answer'), 'jwt-ok')
