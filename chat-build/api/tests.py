from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
    def test_oncology_train_requires_auth_header(self):
        response = self.client.post(
            '/api/v1/agent/oncology/train/',
            {'documents': [{'source': 'paper-1', 'text': 'oncology text'}]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

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
        with patch('api.views._get_service', return_value=fake_service):
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
    def test_oncology_train_accepts_api_key(self):
        def fake_ingest_documents(documents, domain='oncology', subdomain=None, **kwargs):
            return SimpleNamespace(
                domain=domain,
                subdomain=subdomain,
                documents_received=len(documents),
                duplicates_dropped=0,
                documents_indexed=2,
                dedup_mode=kwargs.get('dedup_mode', 'upsert'),
                version_tag=kwargs.get('version_tag') or '',
            )

        fake_service = SimpleNamespace(
            ingest_documents=fake_ingest_documents
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/oncology/train/',
                {
                    'corpus_name': 'oncology-papers',
                    'subdomain': 'lung-cancer',
                    'documents': [
                        {'source': 'paper-1', 'text': 'Breast cancer biomarkers.'},
                        {'source': 'paper-2', 'text': 'Lung cancer immunotherapy response.'},
                    ],
                },
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('domain'), 'oncology')
        self.assertEqual(response.data.get('subdomain'), 'lung-cancer')
        self.assertEqual(response.data.get('documents_indexed'), 2)

    @override_settings(AGENT_API_KEY='test-key')
    def test_oncology_upload_accepts_multipart_file(self):
        def fake_ingest_documents(documents, domain='oncology', subdomain=None, **kwargs):
            return SimpleNamespace(
                domain=domain,
                subdomain=subdomain,
                documents_received=len(documents),
                duplicates_dropped=0,
                documents_indexed=len(documents),
                dedup_mode=kwargs.get('dedup_mode', 'batch-dedup'),
                version_tag=kwargs.get('version_tag') or '',
            )

        fake_service = SimpleNamespace(
            ingest_documents=fake_ingest_documents
        )
        upload = SimpleUploadedFile(
            'oncology.json',
            b'[{"source":"paper-1","text":"EGFR evidence","cancer_type":"lung cancer","biomarkers":["EGFR"]}]',
            content_type='application/json',
        )
        with patch('api.views._get_service', return_value=fake_service), patch(
            'api.views.load_oncology_corpus_content',
            return_value=[{'source': 'paper-1', 'text': 'EGFR evidence', 'cancer_type': 'lung cancer', 'biomarkers': ['EGFR']}],
        ):
            response = self.client.post(
                '/api/v1/agent/oncology/upload/',
                {'corpus_name': 'oncology-upload', 'subdomain': 'lung-cancer', 'file': upload},
                format='multipart',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('subdomain'), 'lung-cancer')
        self.assertEqual(response.data.get('documents_indexed'), 1)

    @override_settings(AGENT_API_KEY='test-key')
    def test_oncology_evidence_search_returns_filtered_documents(self):
        def fake_search_evidence(query, max_results=5, cancer_type=None, biomarker=None, subdomain=None, **kwargs):
            return SimpleNamespace(
                domain='oncology',
                subdomain=subdomain,
                evidence=[
                    {
                        'citation_id': 'oncology/lung-cancer/paper-1',
                        'citation_label': 'EGFR pathways (2024, review)',
                        'source': 'oncology/paper-1',
                        'title': 'EGFR pathways',
                        'text': 'EGFR drives several lung cancer research programs.',
                        'subdomain': 'lung-cancer',
                        'cancer_type': 'lung cancer',
                        'biomarkers': ['EGFR'],
                        'evidence_type': 'review',
                        'publication_year': 2024,
                    }
                ],
            )

        fake_service = SimpleNamespace(
            search_evidence=fake_search_evidence
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/oncology/evidence/',
                {'query': 'EGFR pathways', 'subdomain': 'lung-cancer', 'cancer_type': 'lung cancer', 'biomarker': 'EGFR', 'max_results': 3},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('domain'), 'oncology')
        self.assertEqual(response.data.get('subdomain'), 'lung-cancer')
        self.assertEqual(len(response.data.get('evidence', [])), 1)
        self.assertEqual(response.data['evidence'][0]['cancer_type'], 'lung cancer')
        self.assertEqual(response.data['evidence'][0]['citation_id'], 'oncology/lung-cancer/paper-1')

    @override_settings(AGENT_API_KEY='test-key')
    def test_oncology_query_returns_safety_notice(self):
        fake_service = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='oncology-ok', cache_hit=False)
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/oncology/query/',
                {'question': 'Summarize oncology pathways', 'user_id': 'researcher-1', 'subdomain': 'lung-cancer'},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('domain'), 'oncology')
        self.assertEqual(response.data.get('subdomain'), 'lung-cancer')
        self.assertIn('safety_notice', response.data)

    @override_settings(AGENT_API_KEY='test-key')
    def test_oncology_train_passes_versioned_dedup_parameters(self):
        captured = {}

        def fake_ingest_documents(documents, domain='oncology', subdomain=None, **kwargs):
            captured['dedup_mode'] = kwargs.get('dedup_mode')
            captured['version_tag'] = kwargs.get('version_tag')
            return SimpleNamespace(
                domain=domain,
                subdomain=subdomain,
                documents_received=len(documents),
                duplicates_dropped=0,
                documents_indexed=len(documents),
                dedup_mode=kwargs.get('dedup_mode', 'upsert'),
                version_tag=kwargs.get('version_tag') or '',
            )

        fake_service = SimpleNamespace(ingest_documents=fake_ingest_documents)
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/oncology/train/',
                {
                    'corpus_name': 'oncology-versioned',
                    'subdomain': 'lung-cancer',
                    'dedup_mode': 'versioned',
                    'version_tag': '2026-q1',
                    'documents': [
                        {'source': 'paper-1', 'text': 'EGFR resistance summary.'},
                    ],
                },
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(captured.get('dedup_mode'), 'versioned')
        self.assertEqual(captured.get('version_tag'), '2026-q1')
        self.assertEqual(response.data.get('dedup_mode'), 'versioned')
        self.assertEqual(response.data.get('version_tag'), '2026-q1')

    @override_settings(AGENT_API_KEY='test-key')
    def test_oncology_evidence_search_passes_year_filters_and_returns_rerank_score(self):
        captured = {}

        def fake_search_evidence(query, max_results=5, cancer_type=None, biomarker=None, subdomain=None, **kwargs):
            captured['publication_year_from'] = kwargs.get('publication_year_from')
            captured['publication_year_to'] = kwargs.get('publication_year_to')
            captured['rerank'] = kwargs.get('rerank')
            captured['evidence_type'] = kwargs.get('evidence_type')
            return SimpleNamespace(
                domain='oncology',
                subdomain=subdomain,
                evidence=[
                    {
                        'citation_id': 'oncology/lung-cancer/paper-3',
                        'citation_label': 'EGFR trial summary (2023, trial)',
                        'source': 'oncology/paper-3',
                        'title': 'EGFR trial summary',
                        'text': 'Phase II EGFR resistance findings.',
                        'subdomain': 'lung-cancer',
                        'cancer_type': 'lung cancer',
                        'biomarkers': ['EGFR'],
                        'evidence_type': 'trial',
                        'publication_year': 2023,
                        'score': 0.81,
                        'rerank_score': 1.21,
                    }
                ],
            )

        fake_service = SimpleNamespace(search_evidence=fake_search_evidence)
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/oncology/evidence/',
                {
                    'query': 'EGFR resistance pathways',
                    'subdomain': 'lung-cancer',
                    'cancer_type': 'lung cancer',
                    'biomarker': 'EGFR',
                    'evidence_type': 'trial',
                    'publication_year_from': 2020,
                    'publication_year_to': 2026,
                    'rerank': True,
                    'max_results': 3,
                },
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(captured.get('publication_year_from'), 2020)
        self.assertEqual(captured.get('publication_year_to'), 2026)
        self.assertEqual(captured.get('evidence_type'), 'trial')
        self.assertTrue(captured.get('rerank'))
        self.assertIn('rerank_score', response.data['evidence'][0])
        self.assertEqual(response.data['evidence'][0]['publication_year'], 2023)

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
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/query/',
                {'question': 'hello'},
                format='json',
                HTTP_AUTHORIZATION=f'Bearer {access_token}',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('answer'), 'jwt-ok')
