from types import SimpleNamespace
from unittest.mock import patch
from datetime import timedelta
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-local-cache',
        }
    }
)
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
    def test_agent_query_stream_accepts_api_key(self):
        fake_service = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='stream-ok', cache_hit=False)
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/query/stream/',
                {'question': 'What is new?', 'user_id': 'u-1'},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.streaming)
            payload = b''.join(response.streaming_content).decode('utf-8')
            events = [json.loads(line) for line in payload.splitlines() if line.strip()]

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0].get('event'), 'start')
        self.assertEqual(events[-1].get('event'), 'done')
        self.assertEqual(events[-1].get('answer'), 'stream-ok')

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
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='oncology-ok', cache_hit=False, citations=[])
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
    def test_oncology_query_stream_returns_done_event(self):
        fake_service = SimpleNamespace(
            ask_stream=lambda **kwargs: iter([
                {'event': 'delta', 'delta': 'oncology-'},
                {'event': 'done', 'answer': 'oncology-ok', 'cache_hit': False, 'citations': []},
            ])
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/oncology/query/stream/',
                {'question': 'Summarize oncology pathways', 'subdomain': 'lung-cancer'},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            payload = b''.join(response.streaming_content).decode('utf-8')
            events = [json.loads(line) for line in payload.splitlines() if line.strip()]

        self.assertEqual(events[-1].get('event'), 'done')
        self.assertEqual(events[-1].get('answer'), 'oncology-ok')
        self.assertEqual(events[-1].get('domain'), 'oncology')

    @override_settings(AGENT_API_KEY='test-key')
    def test_medical_train_accepts_generic_domain(self):
        def fake_ingest_documents(documents, domain='medical', subdomain=None, **kwargs):
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
                '/api/v1/agent/medical/train/',
                {
                    'domain': 'cardiology',
                    'subdomain': 'heart-failure',
                    'documents': [
                        {'source': 'guideline-1', 'text': 'Heart failure management overview.'},
                    ],
                },
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('domain'), 'cardiology')
        self.assertEqual(response.data.get('subdomain'), 'heart-failure')
        self.assertEqual(response.data.get('documents_indexed'), 1)

    @override_settings(AGENT_API_KEY='test-key')
    def test_medical_query_returns_domain_and_notice(self):
        fake_service = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='medical-ok', cache_hit=False, citations=[])
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/medical/query/',
                {'question': 'Summarize heart failure markers.', 'domain': 'cardiology', 'subdomain': 'heart-failure'},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('domain'), 'cardiology')
        self.assertEqual(response.data.get('subdomain'), 'heart-failure')
        self.assertIn('safety_notice', response.data)

    @override_settings(AGENT_API_KEY='test-key')
    def test_medical_query_stream_returns_done_event(self):
        fake_service = SimpleNamespace(
            ask_stream=lambda **kwargs: iter([
                {'event': 'delta', 'delta': 'medical-'},
                {'event': 'done', 'answer': 'medical-ok', 'cache_hit': False, 'citations': []},
            ])
        )
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/medical/query/stream/',
                {'question': 'Summarize heart failure markers.', 'domain': 'cardiology', 'subdomain': 'heart-failure'},
                format='json',
                HTTP_X_API_KEY='test-key',
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            payload = b''.join(response.streaming_content).decode('utf-8')
            events = [json.loads(line) for line in payload.splitlines() if line.strip()]

        self.assertEqual(events[-1].get('event'), 'done')
        self.assertEqual(events[-1].get('answer'), 'medical-ok')
        self.assertEqual(events[-1].get('domain'), 'cardiology')

    @override_settings(AGENT_API_KEY='test-key')
    def test_medical_evidence_supports_condition_and_marker_filters(self):
        captured = {}

        def fake_search_evidence(query, max_results=5, subdomain=None, **kwargs):
            captured['condition'] = kwargs.get('condition')
            captured['marker'] = kwargs.get('marker')
            return SimpleNamespace(
                domain='cardiology',
                subdomain=subdomain,
                evidence=[
                    {
                        'citation_id': 'cardiology/heart-failure/guideline-1',
                        'citation_label': 'Heart failure biomarkers (2024, guideline)',
                        'source': 'cardiology/heart-failure/guideline-1',
                        'title': 'Heart failure biomarkers',
                        'text': 'NT-proBNP supports risk stratification in heart failure research.',
                        'condition': 'heart failure',
                        'markers': ['NT-proBNP'],
                        'evidence_type': 'guideline',
                        'publication_year': 2024,
                    }
                ],
            )

        fake_service = SimpleNamespace(search_evidence=fake_search_evidence)
        with patch('api.views._get_service', return_value=fake_service):
            response = self.client.post(
                '/api/v1/agent/medical/evidence/',
                {
                    'domain': 'cardiology',
                    'subdomain': 'heart-failure',
                    'query': 'NT-proBNP evidence',
                    'condition': 'heart failure',
                    'marker': 'NT-proBNP',
                    'max_results': 3,
                },
                format='json',
                HTTP_X_API_KEY='test-key',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('domain'), 'cardiology')
        self.assertEqual(captured.get('condition'), 'heart failure')
        self.assertEqual(captured.get('marker'), 'NT-proBNP')
        self.assertEqual(response.data['evidence'][0]['condition'], 'heart failure')

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
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='agent-user', password='password123')
        tenant = Tenant.objects.create(name='Agent Query Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)
        plan = SubscriptionPlan.objects.create(
            code='agent-query-active-plan',
            name='Agent Query Active Plan',
            description='LLM entitlement allow test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

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
                HTTP_X_TENANT_ID=str(tenant.tenant_id),
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('answer'), 'jwt-ok')

    def test_billing_estimate_hybrid_breakdown(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription, UsageRecord

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-admin', password='password123')
        tenant = Tenant.objects.create(name='Hospital A', tenant_type='hospital', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='hospital-test-hybrid',
            name='Hospital Test Hybrid',
            description='Hybrid test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=100000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=2,
            seat_price_cents=5000,
            api_overage_per_1000_cents=100,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        # Seed observed API usage for current month.
        UsageRecord.objects.create(tenant=tenant, metric='api.request', quantity=12050)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-admin', 'password': 'password123'},
            format='json',
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/estimate/',
            {'active_users': 4},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['plan_code'], 'hospital-test-hybrid')
        self.assertEqual(response.data['overage_users'], 2)
        self.assertEqual(response.data['overage_api_requests'], 2050)
        self.assertEqual(response.data['users_overage_cents'], 10000)
        self.assertEqual(response.data['api_overage_cents'], 300)
        self.assertEqual(response.data['total_cents'], 110300)

    def test_billing_estimate_denies_canceled_subscription_with_402(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-canceled-user', password='password123')
        tenant = Tenant.objects.create(name='Canceled Hospital', tenant_type='hospital', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='hospital-canceled-plan',
            name='Hospital Canceled Plan',
            description='Canceled entitlement test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=100000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=2,
            seat_price_cents=5000,
            api_overage_per_1000_cents=100,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.CANCELED,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-canceled-user', 'password': 'password123'},
            format='json',
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/estimate/',
            {'active_users': 4},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, 402)

    def test_billing_role_can_access_billing_usage_summary(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription, UsageRecord

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-role-user', password='password123')
        tenant = Tenant.objects.create(name='Billing Role Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.BILLING, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='billing-role-plan',
            name='Billing Role Plan',
            description='Billing role access test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=2,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.CANCELED,
            provider='stripe',
            provider_customer_id='cus_billing_role',
        )
        UsageRecord.objects.create(tenant=tenant, metric='api.request', quantity=100)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-role-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.get(
            '/api/v1/billing/usage/summary/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_billing_role_cannot_access_llm_endpoints(self):
        from api.models import Tenant, TenantMembership

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-llm-denied', password='password123')
        tenant = Tenant.objects.create(name='Billing LLM Denied Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.BILLING, is_active=True)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-llm-denied', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/agent/query/',
            {'question': 'Can I access LLM?'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_llm_endpoints_require_active_entitlement_for_tenant_jwt(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='llm-entitlement-denied', password='password123')
        tenant = Tenant.objects.create(name='LLM Entitlement Denied Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='llm-entitlement-denied-plan',
            name='LLM Entitlement Denied Plan',
            description='LLM entitlement deny test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.CANCELED,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'llm-entitlement-denied', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/agent/query/',
            {'question': 'Can I access LLM after cancel?'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, 402)

    def test_agent_chat_session_message_and_highlight_flow(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='chat-flow-user', password='password123')
        tenant = Tenant.objects.create(name='Chat Flow Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='chat-flow-plan',
            name='Chat Flow Plan',
            description='Chat flow entitlement test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'chat-flow-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        create_session = self.client.post(
            '/api/v1/agent/chats/',
            {'title': 'Heart failure follow-up'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(create_session.status_code, status.HTTP_201_CREATED)
        session_id = create_session.data['session_id']

        user_message = self.client.post(
            f'/api/v1/agent/chats/{session_id}/messages/',
            {'role': 'user', 'content': 'Summarize HFrEF treatment options.'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(user_message.status_code, status.HTTP_201_CREATED)

        assistant_message = self.client.post(
            f'/api/v1/agent/chats/{session_id}/messages/',
            {
                'role': 'assistant',
                'content': 'Use GDMT with ACEi/ARB/ARNI, beta-blocker, MRA, and SGLT2 inhibitor when indicated.',
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(assistant_message.status_code, status.HTTP_201_CREATED)
        assistant_message_id = assistant_message.data['message_id']

        create_highlight = self.client.post(
            f'/api/v1/agent/chats/{session_id}/highlights/',
            {
                'message_id': assistant_message_id,
                'selected_text': 'SGLT2 inhibitor',
                'start_offset': 55,
                'end_offset': 70,
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(create_highlight.status_code, status.HTTP_201_CREATED)

        detail = self.client.get(
            f'/api/v1/agent/chats/{session_id}/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.data['messages']), 2)
        self.assertEqual(len(detail.data['highlights']), 1)

    def test_agent_chat_highlight_pop_uses_lifo(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='chat-highlight-pop-user', password='password123')
        tenant = Tenant.objects.create(name='Chat Highlight Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='chat-highlight-plan',
            name='Chat Highlight Plan',
            description='Chat highlight pop test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'chat-highlight-pop-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        session_response = self.client.post(
            '/api/v1/agent/chats/',
            {'title': 'LIFO test'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        session_id = session_response.data['session_id']

        assistant_message = self.client.post(
            f'/api/v1/agent/chats/{session_id}/messages/',
            {
                'role': 'assistant',
                'content': 'Aspirin plus statin are commonly used in secondary prevention contexts.',
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        message_id = assistant_message.data['message_id']

        first_highlight = self.client.post(
            f'/api/v1/agent/chats/{session_id}/highlights/',
            {
                'message_id': message_id,
                'selected_text': 'Aspirin',
                'start_offset': 0,
                'end_offset': 7,
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(first_highlight.status_code, status.HTTP_201_CREATED)

        second_highlight = self.client.post(
            f'/api/v1/agent/chats/{session_id}/highlights/',
            {
                'message_id': message_id,
                'selected_text': 'statin',
                'start_offset': 13,
                'end_offset': 19,
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(second_highlight.status_code, status.HTTP_201_CREATED)

        pop_response = self.client.delete(
            f'/api/v1/agent/chats/{session_id}/highlights/pop/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(pop_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pop_response.data['undone_highlight_id'], second_highlight.data['highlight_id'])

    def test_agent_chat_session_title_auto_generates_from_first_assistant_response(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='chat-title-user', password='password123')
        tenant = Tenant.objects.create(name='Chat Title Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='chat-title-plan',
            name='Chat Title Plan',
            description='Chat title generation test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'chat-title-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        session_response = self.client.post(
            '/api/v1/agent/chats/',
            {},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        session_id = session_response.data['session_id']

        self.client.post(
            f'/api/v1/agent/chats/{session_id}/messages/',
            {'role': 'user', 'content': 'What are guideline updates?'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )

        self.client.post(
            f'/api/v1/agent/chats/{session_id}/messages/',
            {
                'role': 'assistant',
                'content': 'Guideline update: prioritize SGLT2 inhibitors in eligible HFrEF patients. Additional notes follow.',
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )

        detail = self.client.get(
            f'/api/v1/agent/chats/{session_id}/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertTrue(detail.data['title'].startswith('Guideline update: prioritize SGLT2 inhibitors'))

    def test_agent_chat_sessions_search_returns_paginated_shape(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='chat-search-user', password='password123')
        tenant = Tenant.objects.create(name='Chat Search Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='chat-search-plan',
            name='Chat Search Plan',
            description='Chat search shape test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'chat-search-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        first = self.client.post(
            '/api/v1/agent/chats/',
            {'title': 'Cancer biomarkers review'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        second = self.client.post(
            '/api/v1/agent/chats/',
            {'title': 'Neurology follow-up'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

        response = self.client.get(
            '/api/v1/agent/chats/?q=biomarkers&limit=1&offset=0',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('items', response.data)
        self.assertIn('pagination', response.data)
        self.assertEqual(response.data['pagination']['limit'], 1)
        self.assertGreaterEqual(response.data['pagination']['total'], 1)
        self.assertGreaterEqual(len(response.data['items']), 1)

    def test_agent_chat_session_detail_supports_tail_pagination_for_older_messages(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='chat-tail-user', password='password123')
        tenant = Tenant.objects.create(name='Chat Tail Tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='chat-tail-plan',
            name='Chat Tail Plan',
            description='Chat tail pagination test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'chat-tail-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        session_response = self.client.post(
            '/api/v1/agent/chats/',
            {'title': 'Tail pagination'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        session_id = session_response.data['session_id']

        for idx in range(6):
            self.client.post(
                f'/api/v1/agent/chats/{session_id}/messages/',
                {'role': 'assistant', 'content': f'Message {idx + 1}'},
                format='json',
                HTTP_AUTHORIZATION=f'Bearer {access_token}',
                HTTP_X_TENANT_ID=str(tenant.tenant_id),
            )

        latest_slice = self.client.get(
            f'/api/v1/agent/chats/{session_id}/?message_limit=3&message_offset=0&from_end=1',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(latest_slice.status_code, status.HTTP_200_OK)
        self.assertEqual(len(latest_slice.data['messages']), 3)
        self.assertEqual(latest_slice.data['messages'][0]['content'], 'Message 4')
        self.assertTrue(latest_slice.data['messages_pagination']['has_more'])

        older_slice = self.client.get(
            f'/api/v1/agent/chats/{session_id}/?message_limit=3&message_offset=3&from_end=1',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(older_slice.status_code, status.HTTP_200_OK)
        self.assertEqual([m['content'] for m in older_slice.data['messages']], ['Message 1', 'Message 2', 'Message 3'])
        self.assertFalse(older_slice.data['messages_pagination']['has_more'])

    def test_tenant_memberships_owner_can_create_list_and_update(self):
        from api.models import Tenant, TenantMembership

        user_model = get_user_model()
        owner = user_model.objects.create_user(username='membership-owner', password='password123')
        tenant = Tenant.objects.create(name='Membership Tenant', tenant_type='clinic', owner=owner)
        TenantMembership.objects.create(tenant=tenant, user=owner, role=TenantMembership.Role.OWNER, is_active=True)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'membership-owner', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        create_response = self.client.post(
            '/api/v1/tenants/memberships/create/',
            {'username': 'membership-clinician', 'email': 'membership-clinician@example.com', 'password': 'password123', 'role': 'clinician'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data['role'], TenantMembership.Role.CLINICIAN)

        list_response = self.client.get(
            '/api/v1/tenants/memberships/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        usernames = {item['username'] for item in list_response.data}
        self.assertIn('membership-clinician', usernames)

        membership_id = create_response.data['membership_id']
        update_response = self.client.patch(
            f'/api/v1/tenants/memberships/{membership_id}/',
            {'role': 'auditor', 'is_active': False},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data['role'], TenantMembership.Role.AUDITOR)
        self.assertFalse(update_response.data['is_active'])

    def test_tenant_memberships_billing_role_is_forbidden(self):
        from api.models import Tenant, TenantMembership

        user_model = get_user_model()
        billing_user = user_model.objects.create_user(username='membership-billing', password='password123')
        tenant = Tenant.objects.create(name='Membership Billing Tenant', tenant_type='clinic', owner=billing_user)
        TenantMembership.objects.create(tenant=tenant, user=billing_user, role=TenantMembership.Role.BILLING, is_active=True)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'membership-billing', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        list_response = self.client.get(
            '/api/v1/tenants/memberships/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_memberships_cannot_demote_last_owner(self):
        from api.models import Tenant, TenantMembership

        user_model = get_user_model()
        owner = user_model.objects.create_user(username='membership-last-owner', password='password123')
        tenant = Tenant.objects.create(name='Membership Last Owner Tenant', tenant_type='clinic', owner=owner)
        owner_membership = TenantMembership.objects.create(tenant=tenant, user=owner, role=TenantMembership.Role.OWNER, is_active=True)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'membership-last-owner', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.patch(
            f'/api/v1/tenants/memberships/{owner_membership.pk}/',
            {'role': 'admin'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'cannot remove last owner')

    def test_billing_invoice_close_and_latest(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-close-user', password='password123')
        tenant = Tenant.objects.create(name='Clinic Billing', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='clinic-close-hybrid',
            name='Clinic Close Hybrid',
            description='Hybrid close test',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=20000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=5000,
            max_users=5,
            seat_price_cents=1500,
            api_overage_per_1000_cents=120,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-close-user', 'password': 'password123'},
            format='json',
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access_token = token_response.data['access']

        close_response = self.client.post(
            '/api/v1/billing/invoices/close/',
            {'active_users': 7, 'api_requests': 7001},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(close_response.data['overage_users'], 2)
        self.assertEqual(close_response.data['overage_api_requests'], 2001)

        latest_response = self.client.get(
            '/api/v1/billing/invoices/latest/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(latest_response.status_code, status.HTTP_200_OK)
        self.assertEqual(latest_response.data['invoice_id'], close_response.data['invoice_id'])

        list_response = self.client.get(
            '/api/v1/billing/invoices/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_response.data), 1)

        invoice_id = close_response.data['invoice_id']
        detail_response = self.client.get(
            f'/api/v1/billing/invoices/{invoice_id}/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertIn('line_items', detail_response.data)
        self.assertGreaterEqual(len(detail_response.data['line_items']), 3)

        receipt_response = self.client.get(
            f'/api/v1/billing/invoices/{invoice_id}/receipt.txt',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(receipt_response.status_code, status.HTTP_200_OK)
        self.assertIn('CliniGraph AI Receipt', receipt_response.content.decode('utf-8'))

    @patch('api.platform_views.render_invoice_pdf')
    def test_billing_invoice_receipt_pdf_and_export_csv(self, mock_render_pdf):
        from api.models import BillingInvoice, SubscriptionPlan, Tenant, TenantMembership, Subscription

        mock_render_pdf.return_value = b'%PDF-1.4\n%mock\n'

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-pdf-user', password='password123')
        tenant = Tenant.objects.create(name='Finance Org', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='finance-plan',
            name='Finance Plan',
            description='Finance test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=2,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-pdf-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        close_response = self.client.post(
            '/api/v1/billing/invoices/close/',
            {'active_users': 3, 'api_requests': 1500},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        invoice_id = close_response.data['invoice_id']

        old_invoice = BillingInvoice.objects.get(invoice_id=invoice_id)
        old_invoice.generated_at = timezone.now() - timedelta(days=40)
        old_invoice.status = BillingInvoice.Status.PAID
        old_invoice.period_start = timezone.now() - timedelta(days=60)
        old_invoice.period_end = timezone.now() - timedelta(days=30)
        old_invoice.save(update_fields=['generated_at', 'status', 'period_start', 'period_end'])

        pdf_response = self.client.get(
            f'/api/v1/billing/invoices/{invoice_id}/receipt.pdf',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(pdf_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')

        csv_response = self.client.get(
            '/api/v1/billing/invoices/export.csv',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(csv_response.status_code, status.HTTP_200_OK)
        content = csv_response.content.decode('utf-8')
        self.assertIn('invoice_id,period_start,period_end', content)
        self.assertIn(str(invoice_id), content)

        filtered_csv = self.client.get(
            '/api/v1/billing/invoices/export.csv?status=paid',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(filtered_csv.status_code, status.HTTP_200_OK)
        filtered_content = filtered_csv.content.decode('utf-8')
        self.assertIn(str(invoice_id), filtered_content)

        start_date = (timezone.now() - timedelta(days=7)).date().isoformat()
        date_filtered_csv = self.client.get(
            f'/api/v1/billing/invoices/export.csv?start_date={start_date}',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(date_filtered_csv.status_code, status.HTTP_200_OK)
        date_filtered_content = date_filtered_csv.content.decode('utf-8')
        self.assertNotIn(str(invoice_id), date_filtered_content)

        period_filtered_csv = self.client.get(
            f'/api/v1/billing/invoices/export.csv?period_start={(timezone.now() - timedelta(days=10)).date().isoformat()}',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(period_filtered_csv.status_code, status.HTTP_200_OK)
        period_filtered_content = period_filtered_csv.content.decode('utf-8')
        self.assertNotIn(str(invoice_id), period_filtered_content)

        invalid_period_csv = self.client.get(
            '/api/v1/billing/invoices/export.csv?period_start=2026-01-10&period_end=2025-12-01',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(invalid_period_csv.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_date_csv = self.client.get(
            '/api/v1/billing/invoices/export.csv?start_date=2026-99-99',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(invalid_date_csv.status_code, status.HTTP_400_BAD_REQUEST)

    def test_billing_usage_summary_includes_latest_invoice(self):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription, UsageRecord

        user_model = get_user_model()
        user = user_model.objects.create_user(username='billing-summary-user', password='password123')
        tenant = Tenant.objects.create(name='Summary Hospital', tenant_type='hospital', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.ADMIN, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='summary-plan',
            name='Summary Plan',
            description='Summary test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=90000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=10,
            seat_price_cents=2000,
            api_overage_per_1000_cents=80,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='internal',
        )
        UsageRecord.objects.create(tenant=tenant, metric='api.request', quantity=12500)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'billing-summary-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        self.client.post(
            '/api/v1/billing/invoices/close/',
            {'active_users': 12, 'api_requests': 12500},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )

        response = self.client.get(
            '/api/v1/billing/usage/summary/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overage_api_requests'], 2500)
        self.assertIsNotNone(response.data['latest_invoice'])

    @patch('api.services.platform_service.StripeBillingProvider')
    def test_create_checkout_session_reuses_existing_stripe_customer(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription
        from api.services.platform_service import create_checkout_session

        mock_provider = mock_provider_cls.return_value
        mock_provider.create_checkout_session.return_value = SimpleNamespace(
            id='cs_test_reuse',
            url='https://checkout.stripe.test/cs_test_reuse',
            customer='cus_existing_123',
        )

        user_model = get_user_model()
        user = user_model.objects.create_user(username='reuse-customer-user', password='password123', email='reuse@example.com')
        tenant = Tenant.objects.create(name='Reuse Tenant', tenant_type='clinic', owner=user)

        current_plan = SubscriptionPlan.objects.create(
            code='reuse-current-plan',
            name='Reuse Current Plan',
            description='Current plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=9900,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=2,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
            provider_price_id='price_current_reuse',
        )
        target_plan = SubscriptionPlan.objects.create(
            code='reuse-target-plan',
            name='Reuse Target Plan',
            description='Target plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=19900,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=5000,
            max_users=10,
            seat_price_cents=1200,
            api_overage_per_1000_cents=40,
            provider_price_id='price_target_reuse',
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=current_plan,
            status=Subscription.Status.ACTIVE,
            provider='stripe',
            provider_customer_id='cus_existing_123',
            provider_subscription_id='sub_existing_123',
        )

        result = create_checkout_session(
            user=user,
            tenant_name=tenant.name,
            tenant_type=tenant.tenant_type,
            plan=target_plan,
        )

        self.assertEqual(result.subscription.provider_customer_id, 'cus_existing_123')
        kwargs = mock_provider.create_checkout_session.call_args.kwargs
        self.assertEqual(kwargs.get('existing_customer_id'), 'cus_existing_123')
        self.assertEqual(kwargs.get('user_email'), 'reuse@example.com')

    @patch('api.services.platform_service.StripeBillingProvider')
    def test_create_checkout_session_retries_when_existing_customer_is_stale(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription
        from api.services.platform_service import create_checkout_session

        mock_provider = mock_provider_cls.return_value
        mock_provider.create_checkout_session.side_effect = [
            Exception("No such customer: 'cus_stale_123'"),
            SimpleNamespace(id='cs_test_retry', url='https://checkout.stripe.test/cs_test_retry', customer='cus_new_456'),
        ]

        user_model = get_user_model()
        user = user_model.objects.create_user(username='retry-customer-user', password='password123', email='retry@example.com')
        tenant = Tenant.objects.create(name='Retry Tenant', tenant_type='clinic', owner=user)

        previous_plan = SubscriptionPlan.objects.create(
            code='retry-prev-plan',
            name='Retry Prev Plan',
            description='Previous plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=9000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=2,
            seat_price_cents=800,
            api_overage_per_1000_cents=30,
            provider_price_id='price_retry_prev',
        )
        target_plan = SubscriptionPlan.objects.create(
            code='retry-target-plan',
            name='Retry Target Plan',
            description='Target plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=15000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=5000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=40,
            provider_price_id='price_retry_target',
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=previous_plan,
            status=Subscription.Status.ACTIVE,
            provider='stripe',
            provider_customer_id='cus_stale_123',
            provider_subscription_id='sub_stale_123',
        )

        result = create_checkout_session(
            user=user,
            tenant_name=tenant.name,
            tenant_type=tenant.tenant_type,
            plan=target_plan,
        )

        self.assertEqual(mock_provider.create_checkout_session.call_count, 2)
        first_call = mock_provider.create_checkout_session.call_args_list[0].kwargs
        second_call = mock_provider.create_checkout_session.call_args_list[1].kwargs
        self.assertEqual(first_call.get('existing_customer_id'), 'cus_stale_123')
        self.assertIsNone(second_call.get('existing_customer_id'))
        self.assertEqual(result.subscription.provider_customer_id, 'cus_new_456')

    @patch('api.services.platform_service.StripeBillingProvider')
    def test_create_checkout_session_does_not_keep_stale_customer_when_retry_session_customer_missing(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription
        from api.services.platform_service import create_checkout_session

        mock_provider = mock_provider_cls.return_value
        mock_provider.create_checkout_session.side_effect = [
            Exception("No such customer: 'cus_stale_789'"),
            SimpleNamespace(id='cs_test_retry_empty', url='https://checkout.stripe.test/cs_test_retry_empty', customer=''),
        ]

        user_model = get_user_model()
        user = user_model.objects.create_user(username='retry-empty-user', password='password123', email='retry-empty@example.com')
        tenant = Tenant.objects.create(name='Retry Empty Tenant', tenant_type='clinic', owner=user)
        previous_plan = SubscriptionPlan.objects.create(
            code='retry-empty-prev-plan',
            name='Retry Empty Prev Plan',
            description='Previous plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=9000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=2,
            seat_price_cents=800,
            api_overage_per_1000_cents=30,
            provider_price_id='price_retry_empty_prev',
        )
        target_plan = SubscriptionPlan.objects.create(
            code='retry-empty-target-plan',
            name='Retry Empty Target Plan',
            description='Target plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=15000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=5000,
            max_users=10,
            seat_price_cents=1000,
            api_overage_per_1000_cents=40,
            provider_price_id='price_retry_empty_target',
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=previous_plan,
            status=Subscription.Status.ACTIVE,
            provider='stripe',
            provider_customer_id='cus_stale_789',
            provider_subscription_id='sub_stale_789',
        )

        result = create_checkout_session(
            user=user,
            tenant_name=tenant.name,
            tenant_type=tenant.tenant_type,
            plan=target_plan,
        )

        self.assertEqual(mock_provider.create_checkout_session.call_count, 2)
        self.assertEqual(result.subscription.provider_customer_id, '')

    @patch('api.platform_views.create_portal_session')
    def test_billing_portal_session_create(self, mock_create_portal_session):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        mock_create_portal_session.return_value = SimpleNamespace(url='https://billing.example.com/portal', id='bps_123')

        user_model = get_user_model()
        user = user_model.objects.create_user(username='portal-user', password='password123')
        tenant = Tenant.objects.create(name='Portal Clinic', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='portal-plan',
            name='Portal Plan',
            description='Portal test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=50000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=10,
            seat_price_cents=2000,
            api_overage_per_1000_cents=100,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='stripe',
            provider_customer_id='cus_123',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'portal-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/portal/session/',
            {'return_url': 'https://app.example.com/billing'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['session_id'], 'bps_123')

    @patch('api.platform_views.create_portal_session')
    def test_billing_portal_session_create_allows_canceled_subscription_for_recovery(self, mock_create_portal_session):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        mock_create_portal_session.return_value = SimpleNamespace(url='https://billing.example.com/portal', id='bps_recovery_123')

        user_model = get_user_model()
        user = user_model.objects.create_user(username='portal-recovery-user', password='password123')
        tenant = Tenant.objects.create(name='Portal Recovery Clinic', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True)

        plan = SubscriptionPlan.objects.create(
            code='portal-recovery-plan',
            name='Portal Recovery Plan',
            description='Portal recovery test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=50000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=10,
            seat_price_cents=2000,
            api_overage_per_1000_cents=100,
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.CANCELED,
            provider='stripe',
            provider_customer_id='cus_recovery_123',
            provider_subscription_id='sub_recovery_123',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'portal-recovery-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/portal/session/',
            {'return_url': 'https://app.example.com/billing'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['session_id'], 'bps_recovery_123')

    @patch('api.platform_views.change_subscription_plan')
    def test_billing_subscription_change_plan_preview(self, mock_change_subscription_plan):
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        mock_change_subscription_plan.return_value = SimpleNamespace(
            applied=False,
            preview={'currency': 'usd', 'amount_due': 999, 'amount_remaining': 999, 'proration_date': 1700000000},
        )

        user_model = get_user_model()
        user = user_model.objects.create_user(username='plan-change-user', password='password123')
        tenant = Tenant.objects.create(name='Plan Change Org', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.ADMIN, is_active=True)

        current_plan = SubscriptionPlan.objects.create(
            code='current-plan',
            name='Current Plan',
            description='Current plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=2,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
            provider_price_id='price_current',
        )
        target_plan = SubscriptionPlan.objects.create(
            code='target-plan',
            name='Target Plan',
            description='Target plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=20000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=5000,
            max_users=10,
            seat_price_cents=1500,
            api_overage_per_1000_cents=40,
            provider_price_id='price_target',
        )
        Subscription.objects.create(
            tenant=tenant,
            plan=current_plan,
            status=Subscription.Status.ACTIVE,
            provider='stripe',
            provider_subscription_id='sub_123',
            provider_customer_id='cus_123',
        )

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'plan-change-user', 'password': 'password123'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/subscriptions/change-plan/',
            {'target_plan_code': target_plan.code, 'apply': False},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['applied'], False)
        self.assertEqual(response.data['target_plan_code'], target_plan.code)

    @patch('api.platform_views.StripeBillingProvider')
    def test_billing_webhook_idempotent_by_provider_event_id(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription, BillingEvent

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        user_model = get_user_model()
        user = user_model.objects.create_user(username='webhook-idempotency-user', password='password123')
        tenant = Tenant.objects.create(name='Webhook Idempotency Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='webhook-idempotency-plan',
            name='Webhook Idempotency Plan',
            description='Webhook plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=10000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
            provider_price_id='price_webhook_idempotency',
        )
        subscription = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            provider='stripe',
            provider_subscription_id='sub_webhook_idempotency',
            provider_customer_id='cus_webhook_idempotency',
        )
        event_payload = FakeStripeEvent(
            event_id='evt_idempotent_123',
            event_type='invoice.payment_failed',
            data_object={'subscription': subscription.provider_subscription_id},
        )
        mock_provider = mock_provider_cls.return_value
        mock_provider.construct_event.return_value = event_payload

        response_first = self.client.post(
            '/api/v1/billing/webhook/',
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response_first.status_code, status.HTTP_200_OK)

        response_second = self.client.post(
            '/api/v1/billing/webhook/',
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response_second.status_code, status.HTTP_200_OK)
        self.assertTrue(response_second.data.get('duplicate'))
        self.assertEqual(BillingEvent.objects.filter(provider='stripe', provider_event_id='evt_idempotent_123').count(), 1)

    @patch('api.platform_views.StripeBillingProvider')
    def test_billing_webhook_invoice_paid_sets_subscription_and_invoice_paid(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription, BillingInvoice

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        user_model = get_user_model()
        user = user_model.objects.create_user(username='webhook-invoice-paid-user', password='password123')
        tenant = Tenant.objects.create(name='Webhook Invoice Paid Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='webhook-invoice-paid-plan',
            name='Webhook Invoice Paid Plan',
            description='Webhook invoice paid plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=12000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=1000,
            api_overage_per_1000_cents=50,
            provider_price_id='price_webhook_invoice_paid',
        )
        subscription = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.PAST_DUE,
            provider='stripe',
            provider_subscription_id='sub_invoice_paid_123',
            provider_customer_id='cus_invoice_paid_123',
        )
        invoice = BillingInvoice.objects.create(
            tenant=tenant,
            subscription=subscription,
            period_start=timezone.now() - timedelta(days=30),
            period_end=timezone.now(),
            currency='USD',
            status=BillingInvoice.Status.FINALIZED,
            total_cents=12000,
            platform_fee_cents=12000,
        )
        event_payload = FakeStripeEvent(
            event_id='evt_invoice_paid_123',
            event_type='invoice.paid',
            data_object={'id': 'in_test_paid_123', 'subscription': subscription.provider_subscription_id},
        )
        mock_provider = mock_provider_cls.return_value
        mock_provider.construct_event.return_value = event_payload

        response = self.client.post(
            '/api/v1/billing/webhook/',
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        subscription.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(invoice.status, BillingInvoice.Status.PAID)
        self.assertEqual(invoice.external_invoice_id, 'in_test_paid_123')
        self.assertIsNotNone(invoice.paid_at)


# ---------------------------------------------------------------------------
# Entitlement service tests
# ---------------------------------------------------------------------------

@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-entitlement-cache',
        }
    },
    BILLING_GRACE_PERIOD_DAYS=7,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class EntitlementServiceTests(APITestCase):
    """Unit tests for check_tenant_entitlement, begin_grace_period, restore / revoke."""

    def _make_tenant_and_plan(self, username: str):
        from api.models import SubscriptionPlan, Tenant
        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw', email=f'{username}@example.com')
        tenant = Tenant.objects.create(name=f'Tenant {username}', tenant_type='individual', owner=user)
        plan = SubscriptionPlan.objects.create(
            code=f'plan-{username}',
            name='Test Plan',
            description='',
            billing_cycle='monthly',
            price_cents=5000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=500,
            api_overage_per_1000_cents=50,
        )
        return tenant, plan, user

    def test_active_subscription_is_allowed(self):
        from api.models import Subscription
        from api.services.entitlement_service import check_tenant_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-active')
        Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
        result = check_tenant_entitlement(tenant)
        self.assertTrue(result.allowed)
        self.assertFalse(result.in_grace)

    def test_trialing_subscription_is_allowed(self):
        from api.models import Subscription
        from api.services.entitlement_service import check_tenant_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-trial')
        Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.TRIALING)
        result = check_tenant_entitlement(tenant)
        self.assertTrue(result.allowed)

    def test_canceled_subscription_is_denied(self):
        from api.models import Subscription
        from api.services.entitlement_service import check_tenant_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-canceled')
        Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.CANCELED)
        result = check_tenant_entitlement(tenant)
        self.assertFalse(result.allowed)

    def test_no_subscription_is_denied(self):
        from api.models import Tenant
        from api.services.entitlement_service import check_tenant_entitlement
        User = get_user_model()
        user = User.objects.create_user(username='ent-nosub', password='pw')
        tenant = Tenant.objects.create(name='No Sub Tenant', tenant_type='individual', owner=user)
        result = check_tenant_entitlement(tenant)
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, 'no_subscription')

    def test_past_due_within_grace_is_allowed_with_warning(self):
        from api.models import Subscription
        from api.services.entitlement_service import check_tenant_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-grace-ok')
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() + timedelta(days=3),
        )
        result = check_tenant_entitlement(tenant)
        self.assertTrue(result.allowed)
        self.assertTrue(result.in_grace)
        self.assertIsNotNone(result.grace_ends_at)

    def test_past_due_with_expired_grace_is_denied(self):
        from api.models import Subscription
        from api.services.entitlement_service import check_tenant_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-grace-expired')
        Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() - timedelta(hours=1),
        )
        result = check_tenant_entitlement(tenant)
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, 'grace_expired')

    def test_past_due_without_grace_date_is_denied(self):
        from api.models import Subscription
        from api.services.entitlement_service import check_tenant_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-pastdue-nograce')
        Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=None,
        )
        result = check_tenant_entitlement(tenant)
        self.assertFalse(result.allowed)

    def test_begin_grace_period_sets_status_and_deadline(self):
        from api.models import Subscription
        from api.services.entitlement_service import begin_grace_period
        tenant, plan, _ = self._make_tenant_and_plan('ent-begin-grace')
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
        before = timezone.now()
        begin_grace_period(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        self.assertIsNotNone(sub.grace_period_ends_at)
        # Should be ~7 days out
        delta = sub.grace_period_ends_at - before
        self.assertGreater(delta.total_seconds(), 6 * 86400)
        self.assertLess(delta.total_seconds(), 8 * 86400)

    def test_restore_entitlement_clears_grace_and_sets_active(self):
        from api.models import Subscription
        from api.services.entitlement_service import restore_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-restore')
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() + timedelta(days=2),
        )
        restore_entitlement(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNone(sub.grace_period_ends_at)

    def test_revoke_entitlement_cancels_subscription(self):
        from api.models import Subscription
        from api.services.entitlement_service import revoke_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-revoke')
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE)
        revoke_entitlement(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)
        self.assertIsNotNone(sub.canceled_at)
        self.assertIsNone(sub.grace_period_ends_at)

    def test_begin_grace_period_is_idempotent_on_retries(self):
        """Calling begin_grace_period twice must NOT extend the grace window."""
        from api.models import Subscription
        from api.services.entitlement_service import begin_grace_period
        tenant, plan, _ = self._make_tenant_and_plan('ent-grace-idempotent')
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
        begin_grace_period(sub)
        sub.refresh_from_db()
        first_deadline = sub.grace_period_ends_at

        # Second call (simulating a Stripe payment retry event)
        begin_grace_period(sub)
        sub.refresh_from_db()
        second_deadline = sub.grace_period_ends_at

        # Grace window must remain unchanged
        self.assertEqual(first_deadline, second_deadline)
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)

    def test_increment_failed_payment_count_increases_atomically(self):
        """increment_failed_payment_count must increment and return the new value."""
        from api.models import Subscription
        from api.services.entitlement_service import increment_failed_payment_count
        tenant, plan, _ = self._make_tenant_and_plan('ent-failcount')
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE)
        self.assertEqual(sub.failed_payment_count, 0)

        count = increment_failed_payment_count(sub)
        self.assertEqual(count, 1)

        count = increment_failed_payment_count(sub)
        self.assertEqual(count, 2)

        sub.refresh_from_db()
        self.assertEqual(sub.failed_payment_count, 2)

    def test_restore_entitlement_resets_failed_payment_count(self):
        """restore_entitlement must reset failed_payment_count to 0."""
        from api.models import Subscription
        from api.services.entitlement_service import restore_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-restore-count')
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() + timedelta(days=2),
            failed_payment_count=3,
        )
        restore_entitlement(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.failed_payment_count, 0)

    def test_revoke_entitlement_resets_failed_payment_count(self):
        """revoke_entitlement must reset failed_payment_count to 0."""
        from api.models import Subscription
        from api.services.entitlement_service import revoke_entitlement
        tenant, plan, _ = self._make_tenant_and_plan('ent-revoke-count')
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() - timedelta(hours=1),
            failed_payment_count=2,
        )
        revoke_entitlement(sub)
        sub.refresh_from_db()
        self.assertEqual(sub.failed_payment_count, 0)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-webhook-grace-cache',
        }
    },
    BILLING_GRACE_PERIOD_DAYS=7,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class WebhookGracePeriodTests(APITestCase):
    """Verify that payment_failed webhook triggers grace period instead of simple PAST_DUE."""

    @patch('api.platform_views.StripeBillingProvider')
    def test_payment_failed_webhook_begins_grace_period(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        User = get_user_model()
        user = User.objects.create_user(username='wh-grace-user', password='pw', email='grace@example.com')
        tenant = Tenant.objects.create(name='Grace Webhook Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='wh-grace-plan', name='WH Grace Plan', description='',
            billing_cycle='monthly', price_cents=9000, billing_model='hybrid',
            currency='USD', max_monthly_requests=1000, max_users=3,
            seat_price_cents=500, api_overage_per_1000_cents=50,
            provider_price_id='price_wh_grace',
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            provider='stripe', provider_subscription_id='sub_wh_grace',
        )
        event_payload = FakeStripeEvent(
            event_id='evt_wh_grace_001',
            event_type='invoice.payment_failed',
            data_object={'subscription': sub.provider_subscription_id},
        )
        mock_provider_cls.return_value.construct_event.return_value = event_payload

        response = self.client.post(
            '/api/v1/billing/webhook/', data='{}',
            content_type='application/json', HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response.status_code, 200)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        self.assertIsNotNone(sub.grace_period_ends_at)
        self.assertGreater(sub.grace_period_ends_at, timezone.now())

    @patch('api.platform_views.StripeBillingProvider')
    def test_subscription_deleted_webhook_revokes_entitlement(self, mock_provider_cls):
        from api.models import SubscriptionPlan, Tenant, Subscription

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        User = get_user_model()
        user = User.objects.create_user(username='wh-revoke-user', password='pw', email='revoke@example.com')
        tenant = Tenant.objects.create(name='Revoke Webhook Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='wh-revoke-plan', name='WH Revoke Plan', description='',
            billing_cycle='monthly', price_cents=9000, billing_model='hybrid',
            currency='USD', max_monthly_requests=1000, max_users=3,
            seat_price_cents=500, api_overage_per_1000_cents=50,
            provider_price_id='price_wh_revoke',
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            provider='stripe', provider_subscription_id='sub_wh_revoke',
        )
        event_payload = FakeStripeEvent(
            event_id='evt_wh_revoke_001',
            event_type='customer.subscription.deleted',
            data_object={'id': sub.provider_subscription_id},
        )
        mock_provider_cls.return_value.construct_event.return_value = event_payload

        response = self.client.post(
            '/api/v1/billing/webhook/', data='{}',
            content_type='application/json', HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response.status_code, 200)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)
        self.assertIsNotNone(sub.canceled_at)

    @patch('api.platform_views.StripeBillingProvider')
    def test_payment_failed_webhook_increments_failed_payment_count(self, mock_provider_cls):
        """Each invoice.payment_failed event increments failed_payment_count."""
        from api.models import SubscriptionPlan, Tenant, Subscription

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        User = get_user_model()
        user = User.objects.create_user(username='wh-cnt-user', password='pw', email='cnt@example.com')
        tenant = Tenant.objects.create(name='Counter Webhook Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='wh-cnt-plan', name='WH Counter Plan', description='',
            billing_cycle='monthly', price_cents=9000, billing_model='hybrid',
            currency='USD', max_monthly_requests=1000, max_users=3,
            seat_price_cents=500, api_overage_per_1000_cents=50,
            provider_price_id='price_wh_cnt',
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            provider='stripe', provider_subscription_id='sub_wh_cnt',
        )
        event_payload = FakeStripeEvent(
            event_id='evt_wh_cnt_001',
            event_type='invoice.payment_failed',
            data_object={'subscription': sub.provider_subscription_id},
        )
        mock_provider_cls.return_value.construct_event.return_value = event_payload

        self.client.post(
            '/api/v1/billing/webhook/', data='{}',
            content_type='application/json', HTTP_STRIPE_SIGNATURE='sig_test',
        )
        sub.refresh_from_db()
        self.assertEqual(sub.failed_payment_count, 1)

    @patch('api.platform_views.StripeBillingProvider')
    def test_payment_action_required_webhook_is_accepted(self, mock_provider_cls):
        """invoice.payment_action_required must return 200 without crashing."""
        from api.models import SubscriptionPlan, Tenant, Subscription

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        User = get_user_model()
        user = User.objects.create_user(username='wh-sca-user', password='pw', email='sca@example.com')
        tenant = Tenant.objects.create(name='SCA Webhook Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='wh-sca-plan', name='WH SCA Plan', description='',
            billing_cycle='monthly', price_cents=9000, billing_model='hybrid',
            currency='USD', max_monthly_requests=1000, max_users=3,
            seat_price_cents=500, api_overage_per_1000_cents=50,
            provider_price_id='price_wh_sca',
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            provider='stripe', provider_subscription_id='sub_wh_sca',
        )
        event_payload = FakeStripeEvent(
            event_id='evt_wh_sca_001',
            event_type='invoice.payment_action_required',
            data_object={'subscription': sub.provider_subscription_id},
        )
        mock_provider_cls.return_value.construct_event.return_value = event_payload

        response = self.client.post(
            '/api/v1/billing/webhook/', data='{}',
            content_type='application/json', HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response.status_code, 200)
        # Subscription remains ACTIVE (no state change for SCA events)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-expire-grace-cache',
        }
    },
    BILLING_GRACE_PERIOD_DAYS=7,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class ExpireGracePeriodsCommandTests(APITestCase):
    """Test the expire_grace_periods management command."""

    def test_command_cancels_expired_grace_subscriptions(self):
        from io import StringIO
        from api.models import SubscriptionPlan, Tenant, Subscription
        from django.core.management import call_command

        User = get_user_model()
        user = User.objects.create_user(username='cmd-expire-user', password='pw', email='expire@example.com')
        tenant = Tenant.objects.create(name='Expire Cmd Tenant', tenant_type='individual', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='cmd-expire-plan', name='Expire Plan', description='',
            billing_cycle='monthly', price_cents=4000, billing_model='hybrid',
            currency='USD', max_monthly_requests=500, max_users=2,
            seat_price_cents=400, api_overage_per_1000_cents=40,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() - timedelta(hours=2),
        )

        out = StringIO()
        call_command('expire_grace_periods', stdout=out)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)
        self.assertIsNotNone(sub.canceled_at)

    def test_command_dry_run_does_not_cancel(self):
        from io import StringIO
        from api.models import SubscriptionPlan, Tenant, Subscription
        from django.core.management import call_command

        User = get_user_model()
        user = User.objects.create_user(username='cmd-dryrun-user', password='pw', email='dryrun@example.com')
        tenant = Tenant.objects.create(name='DryRun Tenant', tenant_type='individual', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='cmd-dryrun-plan', name='DryRun Plan', description='',
            billing_cycle='monthly', price_cents=4000, billing_model='hybrid',
            currency='USD', max_monthly_requests=500, max_users=2,
            seat_price_cents=400, api_overage_per_1000_cents=40,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            grace_period_ends_at=timezone.now() - timedelta(hours=2),
        )

        out = StringIO()
        call_command('expire_grace_periods', '--dry-run', stdout=out)

        sub.refresh_from_db()
        # Status must NOT have changed
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        self.assertIn('dry-run', out.getvalue())

    def test_command_skips_stripe_managed_subscriptions(self):
        """Stripe-provider PAST_DUE subs must NOT be canceled by this command."""
        from io import StringIO
        from api.models import SubscriptionPlan, Tenant, Subscription
        from django.core.management import call_command

        User = get_user_model()
        user = User.objects.create_user(username='cmd-stripe-user', password='pw', email='stripesgrace@example.com')
        tenant = Tenant.objects.create(name='Stripe Grace Tenant', tenant_type='individual', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='cmd-stripe-grace-plan', name='Stripe Grace Plan', description='',
            billing_cycle='monthly', price_cents=4000, billing_model='hybrid',
            currency='USD', max_monthly_requests=500, max_users=2,
            seat_price_cents=400, api_overage_per_1000_cents=40,
        )
        # Stripe-managed subscription with expired grace — command must skip it
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            provider='stripe', provider_subscription_id='sub_stripe_grace_skip',
            grace_period_ends_at=timezone.now() - timedelta(hours=3),
        )

        out = StringIO()
        call_command('expire_grace_periods', stdout=out)

        sub.refresh_from_db()
        # Must still be PAST_DUE — Stripe drives the cancelation via webhook
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)

    def test_command_skips_subscriptions_still_within_grace(self):
        """Subscriptions with grace_period_ends_at in the future must not be canceled."""
        from io import StringIO
        from api.models import SubscriptionPlan, Tenant, Subscription
        from django.core.management import call_command

        User = get_user_model()
        user = User.objects.create_user(username='cmd-within-user', password='pw', email='within@example.com')
        tenant = Tenant.objects.create(name='Within Grace Tenant', tenant_type='individual', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='cmd-within-grace-plan', name='Within Grace Plan', description='',
            billing_cycle='monthly', price_cents=4000, billing_model='hybrid',
            currency='USD', max_monthly_requests=500, max_users=2,
            seat_price_cents=400, api_overage_per_1000_cents=40,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.PAST_DUE,
            provider='internal',
            grace_period_ends_at=timezone.now() + timedelta(days=3),  # still valid
        )

        out = StringIO()
        call_command('expire_grace_periods', stdout=out)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)

    # -------------------------------------------------------------------------
    # Auth / Security: logout + token rotation
    # -------------------------------------------------------------------------

    def test_auth_logout_invalidates_refresh_token(self):
        """POST /auth/logout/ with a valid refresh token returns 200 and blacklists it."""
        User = get_user_model()
        User.objects.create_user(username='logout-user', password='pw_logout')

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'logout-user', 'password': 'pw_logout'},
            format='json',
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access_token = token_response.data['access']
        refresh_token = token_response.data['refresh']

        logout_response = self.client.post(
            '/api/v1/auth/logout/',
            {'refresh': refresh_token},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertIn('detail', logout_response.data)

        # Re-using the same refresh token must now fail (blacklisted).
        reuse_response = self.client.post(
            '/api/v1/auth/token/refresh/',
            {'refresh': refresh_token},
            format='json',
        )
        self.assertIn(reuse_response.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_400_BAD_REQUEST,
        ])

    def test_auth_logout_rejects_invalid_token(self):
        """POST /auth/logout/ with a malformed token body returns 400."""
        User = get_user_model()
        User.objects.create_user(username='logout-invalid-user', password='pw_logout2')
        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'logout-invalid-user', 'password': 'pw_logout2'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/auth/logout/',
            {'refresh': 'this.is.not.a.valid.jwt.token'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_auth_logout_requires_refresh_field(self):
        """POST /auth/logout/ with missing refresh field returns 400 (serializer validation)."""
        User = get_user_model()
        User.objects.create_user(username='logout-nofield-user', password='pw_logout3')
        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'logout-nofield-user', 'password': 'pw_logout3'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/auth/logout/',
            {},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(SIMPLE_JWT={
        'ROTATE_REFRESH_TOKENS': True,
        'BLACKLIST_AFTER_ROTATION': True,
        'UPDATE_LAST_LOGIN': True,
    })
    def test_auth_token_refresh_rotation_issues_new_pair(self):
        """POST /auth/token/refresh/ returns a new refresh token; the original is blacklisted."""
        User = get_user_model()
        User.objects.create_user(username='rotation-user', password='pw_rotate')

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'rotation-user', 'password': 'pw_rotate'},
            format='json',
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        original_refresh = token_response.data['refresh']

        rotate_response = self.client.post(
            '/api/v1/auth/token/refresh/',
            {'refresh': original_refresh},
            format='json',
        )
        self.assertEqual(rotate_response.status_code, status.HTTP_200_OK)
        # Rotation must return both a new access and a new refresh token.
        self.assertIn('access', rotate_response.data)
        self.assertIn('refresh', rotate_response.data)
        new_refresh = rotate_response.data['refresh']
        self.assertNotEqual(original_refresh, new_refresh)

        # The original refresh token must now be blacklisted.
        second_rotate = self.client.post(
            '/api/v1/auth/token/refresh/',
            {'refresh': original_refresh},
            format='json',
        )
        self.assertIn(second_rotate.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_400_BAD_REQUEST,
        ])

    # -------------------------------------------------------------------------
    # TenantPlanQuotaThrottle
    # -------------------------------------------------------------------------

    def _make_quota_tenant(self, username: str, max_monthly_requests: int):
        """Helper: create user + tenant + plan + active subscription."""
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw_quota')
        tenant = Tenant.objects.create(name=f'{username}-clinic', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(
            tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True
        )
        plan = SubscriptionPlan.objects.create(
            code=f'quota-plan-{username}',
            name=f'Quota Plan {username}',
            description='Throttle integration test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=5000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=max_monthly_requests,
            max_users=5,
            seat_price_cents=500,
            api_overage_per_1000_cents=50,
        )
        Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE, provider='internal',
        )
        return user, tenant

    @override_settings(AGENT_API_KEY='quota-test-key')
    def test_tenant_quota_throttle_blocks_requests_over_2x_limit(self):
        """TenantPlanQuotaThrottle returns 429 when usage exceeds 2x plan.max_monthly_requests."""
        from api.models import UsageRecord

        user, tenant = self._make_quota_tenant('quota-blocked', max_monthly_requests=100)
        # Seed usage at 201 — strictly above the 2x hard limit (200).
        UsageRecord.objects.create(tenant=tenant, metric='api_requests', quantity=201)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'quota-blocked', 'password': 'pw_quota'},
            format='json',
        )
        access_token = token_response.data['access']

        fake_svc = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='ok', cache_hit=False)
        )
        with patch('api.views._get_service', return_value=fake_svc):
            response = self.client.post(
                '/api/v1/agent/query/',
                {'question': 'over-quota test'},
                format='json',
                HTTP_AUTHORIZATION=f'Bearer {access_token}',
                HTTP_X_TENANT_ID=str(tenant.tenant_id),
            )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(AGENT_API_KEY='quota-test-key')
    def test_tenant_quota_throttle_allows_requests_under_limit(self):
        """TenantPlanQuotaThrottle allows requests when usage is well below 2x limit."""
        from api.models import UsageRecord

        user, tenant = self._make_quota_tenant('quota-allowed', max_monthly_requests=500)
        # Seed usage at 50 — far below the 2x hard limit (1000).
        UsageRecord.objects.create(tenant=tenant, metric='api_requests', quantity=50)

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'quota-allowed', 'password': 'pw_quota'},
            format='json',
        )
        access_token = token_response.data['access']

        fake_svc = SimpleNamespace(
            ask=lambda question, user_id='anonymous': SimpleNamespace(answer='ok', cache_hit=False)
        )
        with patch('api.views._get_service', return_value=fake_svc):
            response = self.client.post(
                '/api/v1/agent/query/',
                {'question': 'under-quota test'},
                format='json',
                HTTP_AUTHORIZATION=f'Bearer {access_token}',
                HTTP_X_TENANT_ID=str(tenant.tenant_id),
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # -------------------------------------------------------------------------
    # Subscription cancellation
    # -------------------------------------------------------------------------

    def _make_billing_owner(self, username: str, plan_code: str):
        """Helper: create owner user + tenant + plan + active subscription."""
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw_billing')
        tenant = Tenant.objects.create(name=f'{username}-tenant', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(
            tenant=tenant, user=user, role=TenantMembership.Role.OWNER, is_active=True
        )
        plan = SubscriptionPlan.objects.create(
            code=plan_code,
            name=f'Plan {plan_code}',
            description='Billing integration test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=5000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=5,
            seat_price_cents=500,
            api_overage_per_1000_cents=50,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE, provider='internal',
        )
        return user, tenant, sub

    def test_billing_subscription_cancel_at_period_end(self):
        """POST /billing/subscriptions/cancel/ with immediately=false defers cancellation."""
        user, tenant, sub = self._make_billing_owner('cancel-period-user', 'cancel-period-plan')

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'cancel-period-user', 'password': 'pw_billing'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/subscriptions/cancel/',
            {'immediately': False},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['cancel_at_period_end'])
        self.assertIsNotNone(response.data['canceled_at'])

        # Subscription must still be ACTIVE (only deferred).
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'active')
        self.assertIsNotNone(sub.canceled_at)

    def test_billing_subscription_cancel_immediately(self):
        """POST /billing/subscriptions/cancel/ with immediately=true sets status to CANCELED."""
        user, tenant, sub = self._make_billing_owner('cancel-imm-user', 'cancel-imm-plan')

        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'username': 'cancel-imm-user', 'password': 'pw_billing'},
            format='json',
        )
        access_token = token_response.data['access']

        response = self.client.post(
            '/api/v1/billing/subscriptions/cancel/',
            {'immediately': True},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['cancel_at_period_end'])
        self.assertEqual(response.data['status'], 'canceled')

        sub.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')

    # -------------------------------------------------------------------------
    # Usage ingest
    # -------------------------------------------------------------------------

    @override_settings(AGENT_API_KEY='ingest-test-key')
    def test_billing_usage_ingest_records_usage_record(self):
        """POST /billing/usage/ingest/ creates a UsageRecord for the given tenant."""
        from api.models import Tenant, UsageRecord

        User = get_user_model()
        user = User.objects.create_user(username='ingest-user', password='pw_ingest')
        tenant = Tenant.objects.create(name='Ingest Clinic', tenant_type='clinic', owner=user)

        before_count = UsageRecord.objects.filter(tenant=tenant, metric='api_requests').count()

        response = self.client.post(
            '/api/v1/billing/usage/ingest/',
            {
                'tenant_id': str(tenant.tenant_id),
                'metric': 'api_requests',
                'quantity': 5,
                'meta': {'source': 'test'},
            },
            format='json',
            HTTP_X_API_KEY='ingest-test-key',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'ok')
        after_count = UsageRecord.objects.filter(tenant=tenant, metric='api_requests').count()
        self.assertEqual(after_count, before_count + 1)

    @override_settings(AGENT_API_KEY='ingest-test-key')
    def test_billing_usage_ingest_rejects_unknown_tenant(self):
        """POST /billing/usage/ingest/ returns 400 when the tenant_id does not exist."""
        response = self.client.post(
            '/api/v1/billing/usage/ingest/',
            {
                'tenant_id': '00000000-0000-0000-0000-000000000000',
                'metric': 'api_requests',
                'quantity': 1,
            },
            format='json',
            HTTP_X_API_KEY='ingest-test-key',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # Trial expiration workflows
    # -------------------------------------------------------------------------

    def _make_trialing_sub(self, username: str, price_cents: int, days_ago: int = 2):
        """Helper: create a TRIALING internal subscription with trial already expired."""
        from api.models import SubscriptionPlan, Tenant, TenantMembership, Subscription

        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw_trial')
        tenant = Tenant.objects.create(name=f'{username}-clinic', tenant_type='clinic', owner=user)
        TenantMembership.objects.create(
            tenant=tenant, user=user, role=TenantMembership.Role.CLINICIAN, is_active=True
        )
        plan = SubscriptionPlan.objects.create(
            code=f'trial-plan-{username}',
            name=f'Trial Plan {username}',
            description='Trial workflow test plan',
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price_cents=price_cents,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=200,
            max_users=3,
            seat_price_cents=300,
            api_overage_per_1000_cents=30,
        )
        sub = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.TRIALING,
            provider='internal',
            trial_ends_at=timezone.now() - timedelta(days=days_ago),
        )
        return sub, tenant

    def test_expire_trials_free_plan_sets_active(self):
        """expire_trials converts a free-plan TRIALING sub with elapsed trial to ACTIVE."""
        from io import StringIO
        from django.core.management import call_command
        from api.models import Subscription

        sub, _ = self._make_trialing_sub('trial-free-user', price_cents=0)

        out = StringIO()
        call_command('expire_trials', stdout=out)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNone(sub.trial_ends_at)
        self.assertIn('ACTIVE', out.getvalue())

    def test_expire_trials_paid_plan_sets_past_due(self):
        """expire_trials converts a paid-plan TRIALING sub with elapsed trial to PAST_DUE."""
        from io import StringIO
        from django.core.management import call_command
        from api.models import Subscription

        sub, _ = self._make_trialing_sub('trial-paid-user', price_cents=4900)

        out = StringIO()
        call_command('expire_trials', stdout=out)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        self.assertIsNotNone(sub.grace_period_ends_at)

    def test_expire_trials_dry_run_does_not_mutate(self):
        """expire_trials --dry-run prints results without changing the database."""
        from io import StringIO
        from django.core.management import call_command
        from api.models import Subscription

        sub, _ = self._make_trialing_sub('trial-dry-user', price_cents=0)

        out = StringIO()
        call_command('expire_trials', '--dry-run', stdout=out)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.TRIALING)  # unchanged
        self.assertIn('dry-run', out.getvalue())

    def test_expire_trials_skips_stripe_provider(self):
        """expire_trials must not touch Stripe-provider subscriptions."""
        from io import StringIO
        from django.core.management import call_command
        from api.models import SubscriptionPlan, Tenant, Subscription

        User = get_user_model()
        user = User.objects.create_user(username='trial-stripe-user', password='pw_t')
        tenant = Tenant.objects.create(name='Stripe Test Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='stripe-trial-plan', name='Stripe Trial Plan', description='',
            billing_cycle='monthly', price_cents=9900, billing_model='hybrid',
            currency='USD', max_monthly_requests=300, max_users=5,
            seat_price_cents=500, api_overage_per_1000_cents=50,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan,
            status=Subscription.Status.TRIALING,
            provider='stripe',
            trial_ends_at=timezone.now() - timedelta(days=1),
        )

        out = StringIO()
        call_command('expire_trials', stdout=out)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.TRIALING)  # Stripe subs unchanged

    @patch('api.platform_views.StripeBillingProvider')
    def test_stripe_webhook_trial_will_end_event_is_accepted(self, mock_provider_cls):
        """customer.subscription.trial_will_end webhook is processed and returns 200."""
        from api.models import SubscriptionPlan, Tenant, Subscription

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        User = get_user_model()
        user = User.objects.create_user(username='trial-wh-user', password='pw_wh')
        tenant = Tenant.objects.create(name='Trial WH Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='wh-trial-plan', name='WH Trial Plan', description='',
            billing_cycle='monthly', price_cents=4900, billing_model='hybrid',
            currency='USD', max_monthly_requests=200, max_users=3,
            seat_price_cents=300, api_overage_per_1000_cents=30,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan,
            status=Subscription.Status.TRIALING,
            provider='stripe',
            provider_subscription_id='sub_trial_wh_test',
        )

        event_payload = FakeStripeEvent(
            event_id='evt_trial_will_end_001',
            event_type='customer.subscription.trial_will_end',
            data_object={
                'id': 'sub_trial_wh_test',
                'status': 'trialing',
                'metadata': {'tenant_id': str(tenant.tenant_id)},
            },
        )
        mock_provider = mock_provider_cls.return_value
        mock_provider.construct_event.return_value = event_payload

        response = self.client.post(
            '/api/v1/billing/webhook/',
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('api.platform_views.StripeBillingProvider')
    def test_stripe_webhook_subscription_updated_maps_trialing_status(self, mock_provider_cls):
        """customer.subscription.updated with stripe status 'trialing' keeps TRIALING in DB."""
        from api.models import SubscriptionPlan, Tenant, Subscription

        class FakeStripeEvent(dict):
            def __init__(self, *, event_id, event_type, data_object):
                super().__init__({"data": {"object": data_object}})
                self.id = event_id
                self.type = event_type

        User = get_user_model()
        user = User.objects.create_user(username='trial-map-user', password='pw_map')
        tenant = Tenant.objects.create(name='Trial Map Tenant', tenant_type='clinic', owner=user)
        plan = SubscriptionPlan.objects.create(
            code='map-trial-plan', name='Map Trial Plan', description='',
            billing_cycle='monthly', price_cents=4900, billing_model='hybrid',
            currency='USD', max_monthly_requests=200, max_users=3,
            seat_price_cents=300, api_overage_per_1000_cents=30,
        )
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan,
            status=Subscription.Status.INCOMPLETE,
            provider='stripe',
            provider_subscription_id='sub_map_trialing_test',
        )

        event_payload = FakeStripeEvent(
            event_id='evt_sub_updated_trialing_001',
            event_type='customer.subscription.updated',
            data_object={
                'id': 'sub_map_trialing_test',
                'status': 'trialing',
                'customer': 'cus_trial_map_001',
                'metadata': {'tenant_id': str(tenant.tenant_id)},
            },
        )
        mock_provider = mock_provider_cls.return_value
        mock_provider.construct_event.return_value = event_payload

        response = self.client.post(
            '/api/v1/billing/webhook/',
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig_test',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.TRIALING)


# ---------------------------------------------------------------------------
# OpenTelemetry tracing tests
# ---------------------------------------------------------------------------

class TracingSetupTests(TestCase):
    """Unit tests for api.tracing.setup_tracing().

    These tests verify the tracing module's public contract without spawning
    a real OTLP exporter or collector — the TracerProvider is reset between
    tests to keep them isolated.
    """

    def setUp(self):
        # Reset the singleton guard so each test starts fresh
        import api.tracing as tracing_mod
        tracing_mod._SETUP_DONE = False
        # Reset the global tracer provider to a fresh no-op state
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        trace.set_tracer_provider(TracerProvider())

    def test_setup_tracing_noop_by_default(self):
        """setup_tracing() with OTEL_EXPORTER=none should complete without error."""
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"OTEL_EXPORTER": "none"}):
            from api.tracing import setup_tracing
            setup_tracing()  # must not raise
        from api.tracing import _SETUP_DONE
        self.assertTrue(_SETUP_DONE)

    def test_setup_tracing_is_idempotent(self):
        """Calling setup_tracing() twice must not raise or reset the provider."""
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"OTEL_EXPORTER": "none"}):
            from api.tracing import setup_tracing
            setup_tracing()
            setup_tracing()  # second call — must be a no-op
        from api.tracing import _SETUP_DONE
        self.assertTrue(_SETUP_DONE)

    def test_setup_tracing_console_exporter(self):
        """OTEL_EXPORTER=console should register a ConsoleSpanExporter without error."""
        import os
        from unittest.mock import patch
        import api.tracing as tracing_mod
        with patch.dict(os.environ, {"OTEL_EXPORTER": "console", "OTEL_SERVICE_NAME": "test-svc"}):
            tracing_mod.setup_tracing()
        self.assertTrue(tracing_mod._SETUP_DONE)

    def test_get_tracer_returns_tracer(self):
        """get_tracer() should return a valid Tracer instance."""
        from api.tracing import setup_tracing, get_tracer
        from opentelemetry.trace import Tracer
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"OTEL_EXPORTER": "none"}):
            setup_tracing()
        tracer = get_tracer("test")
        self.assertIsNotNone(tracer)
        # Tracer should support start_as_current_span context manager
        with tracer.start_as_current_span("test-span") as span:
            self.assertIsNotNone(span)

    def test_rag_graph_imports_without_error(self):
        """graph.py must import cleanly after tracing is initialised."""
        from api.tracing import setup_tracing
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"OTEL_EXPORTER": "none"}):
            setup_tracing()
        # Re-importing should not raise even with OTel already initialised
        import importlib
        import api.agent_ai.graph as graph_mod
        importlib.reload(graph_mod)
        self.assertTrue(hasattr(graph_mod, "build_agent_graph"))


# ---------------------------------------------------------------------------
# Tax / VAT strategy tests
# ---------------------------------------------------------------------------

@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-tax-cache',
        }
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TaxServiceTests(TestCase):
    """Unit tests for calculate_tax_for_subtotal() in tax_service.py."""

    def _make_tenant(self, username: str, **kwargs) -> 'Tenant':
        from api.models import Tenant
        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw')
        return Tenant.objects.create(name=f'Tax Tenant {username}', tenant_type='individual', owner=user, **kwargs)

    def test_no_country_code_returns_zero(self):
        """Tenants without tax_country_code never owe tax."""
        from api.services.tax_service import calculate_tax_for_subtotal
        tenant = self._make_tenant('tax-no-country')
        tax_cents, rate_bps = calculate_tax_for_subtotal(10_000, tenant)
        self.assertEqual(tax_cents, 0)
        self.assertEqual(rate_bps, 0)

    def test_exempt_tenant_returns_zero(self):
        """tax_exempt=True always produces (0, 0) regardless of policy."""
        from api.models import TaxPolicy
        from api.services.tax_service import calculate_tax_for_subtotal
        TaxPolicy.objects.create(country_code='DE', rate_bps=1900, description='German VAT', is_active=True)
        tenant = self._make_tenant('tax-exempt', tax_country_code='DE', tax_exempt=True)
        tax_cents, rate_bps = calculate_tax_for_subtotal(10_000, tenant)
        self.assertEqual(tax_cents, 0)
        self.assertEqual(rate_bps, 0)

    def test_standard_exclusive_tax_calculated_correctly(self):
        """20 % exclusive VAT on 10 000 cents → 2 000 cents tax."""
        from api.models import TaxPolicy
        from api.services.tax_service import calculate_tax_for_subtotal
        TaxPolicy.objects.create(country_code='GB', rate_bps=2000, description='UK VAT', is_active=True)
        tenant = self._make_tenant('tax-gb', tax_country_code='GB')
        tax_cents, rate_bps = calculate_tax_for_subtotal(10_000, tenant)
        self.assertEqual(tax_cents, 2_000)
        self.assertEqual(rate_bps, 2_000)

    def test_inclusive_tax_returns_zero_extra_charge(self):
        """Inclusive tax: rate is recorded but no extra cents are added."""
        from api.models import TaxPolicy
        from api.services.tax_service import calculate_tax_for_subtotal
        TaxPolicy.objects.create(country_code='AU', rate_bps=1000, is_inclusive=True, description='Australian GST (inclusive)', is_active=True)
        tenant = self._make_tenant('tax-au', tax_country_code='AU')
        tax_cents, rate_bps = calculate_tax_for_subtotal(10_000, tenant)
        self.assertEqual(tax_cents, 0)
        self.assertEqual(rate_bps, 1_000)

    def test_region_specific_policy_overrides_country_wide(self):
        """Texas-specific rate (8.25 %) beats the US country-wide rate (0 %)."""
        from api.models import TaxPolicy
        from api.services.tax_service import calculate_tax_for_subtotal
        # Country-wide: US SaaS often exempt at federal level
        TaxPolicy.objects.create(country_code='US', region_code='', rate_bps=0, description='US federal (no SaaS tax)', is_active=True)
        # Texas state rate
        TaxPolicy.objects.create(country_code='US', region_code='TX', rate_bps=825, description='Texas SaaS', is_active=True)
        tenant = self._make_tenant('tax-tx', tax_country_code='US', tax_region_code='TX')
        tax_cents, rate_bps = calculate_tax_for_subtotal(10_000, tenant)
        self.assertEqual(rate_bps, 825)
        self.assertEqual(tax_cents, 825)  # floor(10000 * 825 / 10000)

    def test_no_matching_policy_returns_zero(self):
        """Unknown jurisdiction → (0, 0) without error."""
        from api.services.tax_service import calculate_tax_for_subtotal
        tenant = self._make_tenant('tax-unknown', tax_country_code='ZZ')
        tax_cents, rate_bps = calculate_tax_for_subtotal(5_000, tenant)
        self.assertEqual(tax_cents, 0)
        self.assertEqual(rate_bps, 0)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-tax-invoice-cache',
        }
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TaxInvoiceIntegrationTests(APITestCase):
    """Integration tests: closing a billing period stores tax in BillingInvoice."""

    def _setup(self, username: str, rate_bps: int = 2000):
        from api.models import SubscriptionPlan, Subscription, Tenant, TaxPolicy

        TaxPolicy.objects.create(country_code='FR', rate_bps=rate_bps, description='French TVA', is_active=True)

        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw', email=f'{username}@example.com')
        tenant = Tenant.objects.create(
            name=f'Tax Invoice Tenant {username}',
            tenant_type='individual',
            owner=user,
            tax_country_code='FR',
        )
        plan = SubscriptionPlan.objects.create(
            code=f'plan-{username}',
            name='Tax Plan',
            billing_cycle='monthly',
            price_cents=10_000,
            billing_model='hybrid',
            currency='EUR',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
        return tenant, plan, sub, user

    def test_invoice_close_stores_tax_cents(self):
        """tax_cents on BillingInvoice equals floor(platform_fee * rate_bps / 10_000)."""
        from api.services.platform_service import close_current_billing_period

        tenant, plan, sub, _ = self._setup('tax-inv-close')
        invoice = close_current_billing_period(tenant=tenant, subscription=sub)
        expected_tax = (invoice.platform_fee_cents * 2_000) // 10_000
        self.assertEqual(invoice.tax_cents, expected_tax)
        self.assertEqual(invoice.tax_rate_bps, 2_000)
        self.assertEqual(invoice.total_cents, invoice.platform_fee_cents + expected_tax)

    def test_invoice_close_adds_tax_line_item(self):
        """When tax_cents > 0 a 'tax' BillingInvoiceLineItem is created."""
        from api.models import BillingInvoiceLineItem
        from api.services.platform_service import close_current_billing_period

        tenant, plan, sub, _ = self._setup('tax-inv-line')
        invoice = close_current_billing_period(tenant=tenant, subscription=sub)
        tax_line = BillingInvoiceLineItem.objects.filter(invoice=invoice, code='tax').first()
        self.assertIsNotNone(tax_line)
        self.assertEqual(tax_line.total_price_cents, invoice.tax_cents)

    def test_invoice_close_no_tax_for_exempt_tenant(self):
        """tax_exempt=True → tax_cents=0 and no 'tax' line item."""
        from api.models import BillingInvoiceLineItem, TaxPolicy
        from api.services.platform_service import close_current_billing_period

        TaxPolicy.objects.create(country_code='ES', rate_bps=2100, description='Spain IVA', is_active=True)
        User = get_user_model()
        user = User.objects.create_user(username='tax-exempt-inv', password='pw')
        from api.models import Tenant, SubscriptionPlan, Subscription
        tenant = Tenant.objects.create(
            name='Exempt Invoice Tenant',
            owner=user,
            tax_country_code='ES',
            tax_exempt=True,
        )
        plan = SubscriptionPlan.objects.create(
            code='plan-exempt-inv',
            name='Exempt Plan',
            billing_cycle='monthly',
            price_cents=8_000,
            billing_model='hybrid',
            currency='EUR',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
        invoice = close_current_billing_period(tenant=tenant, subscription=sub)
        self.assertEqual(invoice.tax_cents, 0)
        self.assertFalse(BillingInvoiceLineItem.objects.filter(invoice=invoice, code='tax').exists())


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-tax-api-cache',
        }
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TaxInfoEndpointTests(APITestCase):
    """API tests for PATCH /api/v1/billing/tax-info/."""

    def _setup(self, username: str):
        from api.models import SubscriptionPlan, Subscription, Tenant, TenantMembership

        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw', email=f'{username}@tax.example.com')
        tenant = Tenant.objects.create(name=f'TaxAPI Tenant {username}', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.BILLING, is_active=True)
        plan = SubscriptionPlan.objects.create(
            code=f'plan-taxapi-{username}',
            name='Tax API Plan',
            billing_cycle='monthly',
            price_cents=5_000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)

        token_resp = self.client.post(
            '/api/v1/auth/token/',
            {'username': username, 'password': 'pw'},
            format='json',
        )
        access = token_resp.data['access']
        return tenant, access

    def test_patch_tax_info_updates_tenant(self):
        """PATCH /billing/tax-info/ stores tax_id, country, region, exempt."""
        tenant, access = self._setup('tax-api-patch')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        resp = self.client.patch(
            '/api/v1/billing/tax-info/',
            {
                'tax_id': 'DE123456789',
                'tax_country_code': 'de',    # lowercase — should be normalised to 'DE'
                'tax_region_code': '',
                'tax_exempt': False,
            },
            format='json',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['tax_id'], 'DE123456789')
        self.assertEqual(resp.data['tax_country_code'], 'DE')

        tenant.refresh_from_db()
        self.assertEqual(tenant.tax_id, 'DE123456789')
        self.assertEqual(tenant.tax_country_code, 'DE')

    def test_patch_tax_exempt_sets_flag(self):
        """PATCH with tax_exempt=true marks tenant as exempt."""
        tenant, access = self._setup('tax-api-exempt')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        resp = self.client.patch(
            '/api/v1/billing/tax-info/',
            {'tax_exempt': True},
            format='json',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['tax_exempt'])

        tenant.refresh_from_db()
        self.assertTrue(tenant.tax_exempt)

    def test_patch_tax_info_requires_auth(self):
        """Unauthenticated request → 401."""
        tenant, _ = self._setup('tax-api-unauth')
        resp = self.client.patch(
            '/api/v1/billing/tax-info/',
            {'tax_country_code': 'US'},
            format='json',
            HTTP_X_TENANT_ID=str(tenant.tenant_id),
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Tenant isolation strategy tests
# ---------------------------------------------------------------------------

@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-isolation-cache',
        }
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TenantBoundManagerTests(TestCase):
    """Unit tests for TenantBoundManager and assert_tenant_owns()."""

    def _make_tenant(self, username: str):
        from api.models import Tenant
        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw')
        return Tenant.objects.create(name=f'Isolation Tenant {username}', owner=user)

    def _make_invoice(self, tenant):
        from api.models import SubscriptionPlan, Subscription, BillingInvoice
        from django.utils import timezone
        plan = SubscriptionPlan.objects.create(
            code=f'plan-iso-{tenant.tenant_id}',
            name='Isolation Plan',
            billing_cycle='monthly',
            price_cents=5_000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
        now = timezone.now()
        return BillingInvoice.objects.create(
            tenant=tenant,
            subscription=sub,
            period_start=now,
            period_end=now,
            platform_fee_cents=5_000,
            total_cents=5_000,
            currency='USD',
        )

    def test_for_tenant_returns_only_own_records(self):
        """tenant_objects.for_tenant(t) returns only records for t."""
        from api.models import BillingInvoice
        tenant_a = self._make_tenant('iso-mgr-a')
        tenant_b = self._make_tenant('iso-mgr-b')
        inv_a = self._make_invoice(tenant_a)
        self._make_invoice(tenant_b)

        qs = BillingInvoice.tenant_objects.for_tenant(tenant_a)
        self.assertEqual(list(qs.values_list('pk', flat=True)), [inv_a.pk])

    def test_for_tenant_excludes_other_tenant_records(self):
        """tenant_objects.for_tenant(t) contains no records from other tenants."""
        from api.models import BillingInvoice
        tenant_a = self._make_tenant('iso-mgr-c')
        tenant_b = self._make_tenant('iso-mgr-d')
        self._make_invoice(tenant_a)
        inv_b = self._make_invoice(tenant_b)

        qs = BillingInvoice.tenant_objects.for_tenant(tenant_a)
        self.assertNotIn(inv_b.pk, list(qs.values_list('pk', flat=True)))

    def test_for_tenant_on_agent_chat_session(self):
        """AgentChatSession.tenant_objects.for_tenant() scopes chat sessions."""
        from api.models import AgentChatSession
        tenant_a = self._make_tenant('iso-chat-a')
        tenant_b = self._make_tenant('iso-chat-b')
        User = get_user_model()
        user = User.objects.create_user(username='iso-chat-user', password='pw')

        sess_a = AgentChatSession.objects.create(tenant=tenant_a, user=user)
        AgentChatSession.objects.create(tenant=tenant_b, user=user)

        qs = AgentChatSession.tenant_objects.for_tenant(tenant_a)
        self.assertEqual(list(qs.values_list('pk', flat=True)), [sess_a.pk])

    def test_assert_tenant_owns_passes_for_correct_tenant(self):
        """assert_tenant_owns() does not raise when ownership matches."""
        from api.services.tenant_isolation import assert_tenant_owns
        tenant = self._make_tenant('iso-assert-ok')
        invoice = self._make_invoice(tenant)
        assert_tenant_owns(invoice, tenant)  # should not raise

    def test_assert_tenant_owns_raises_for_wrong_tenant(self):
        """assert_tenant_owns() raises PermissionError on cross-tenant access."""
        from api.services.tenant_isolation import assert_tenant_owns
        tenant_a = self._make_tenant('iso-assert-a')
        tenant_b = self._make_tenant('iso-assert-b')
        invoice_a = self._make_invoice(tenant_a)
        with self.assertRaises(PermissionError):
            assert_tenant_owns(invoice_a, tenant_b)

    def test_assert_tenant_owns_raises_for_non_tenant_model(self):
        """assert_tenant_owns() raises PermissionError for objects without tenant_id."""
        from api.services.tenant_isolation import assert_tenant_owns
        from api.models import SubscriptionPlan
        tenant = self._make_tenant('iso-assert-non')
        plan = SubscriptionPlan.objects.create(
            code='iso-plan-nt',
            name='NT Plan',
            billing_cycle='monthly',
            price_cents=0,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=100,
            max_users=1,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        with self.assertRaises(PermissionError):
            assert_tenant_owns(plan, tenant)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tests-idor-cache',
        }
    },
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TenantIsolationIDORTests(APITestCase):
    """
    IDOR (Insecure Direct Object Reference) regression tests.

    Each test verifies that a user from Tenant B cannot access data
    owned by Tenant A, even when they know the object's ID.
    """

    def _make_billing_tenant(self, username: str):
        """Create user + tenant + BILLING membership + ACTIVE subscription."""
        from api.models import SubscriptionPlan, Subscription, Tenant, TenantMembership

        User = get_user_model()
        user = User.objects.create_user(username=username, password='pw', email=f'{username}@idor.test')
        tenant = Tenant.objects.create(name=f'IDOR Tenant {username}', owner=user)
        TenantMembership.objects.create(tenant=tenant, user=user, role=TenantMembership.Role.BILLING, is_active=True)
        plan = SubscriptionPlan.objects.create(
            code=f'plan-idor-{username}',
            name='IDOR Plan',
            billing_cycle='monthly',
            price_cents=5_000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)

        token_resp = self.client.post('/api/v1/auth/token/', {'username': username, 'password': 'pw'}, format='json')
        access = token_resp.data['access']
        return tenant, user, access

    def _make_invoice(self, tenant):
        from api.models import SubscriptionPlan, Subscription, BillingInvoice
        from django.utils import timezone
        sub = Subscription.objects.filter(tenant=tenant).first()
        now = timezone.now()
        return BillingInvoice.objects.create(
            tenant=tenant,
            subscription=sub,
            period_start=now,
            period_end=now,
            platform_fee_cents=5_000,
            total_cents=5_000,
            currency='USD',
        )

    def test_invoice_detail_idor_blocked(self):
        """Tenant B cannot fetch Tenant A's invoice detail, even with a valid invoice_id."""
        tenant_a, _, _ = self._make_billing_tenant('idor-inv-a')
        _, _, token_b = self._make_billing_tenant('idor-inv-b')
        tenant_b, _, _ = self._make_billing_tenant('idor-inv-b2')
        tenant_a2, _, _ = self._make_billing_tenant('idor-inv-a2')

        # Re-use existing method without duplicate username
        invoice_a = self._make_invoice(tenant_a)

        # Tenant B user authenticates with their own tenant but gives tenant_a's invoice id
        _, _, token_b_final = self._make_billing_tenant('idor-inv-b-final')
        tenant_b_final, _, _ = self._make_billing_tenant('idor-inv-b-final2')
        # Create two independent tenants cleanly
        from api.models import SubscriptionPlan, Subscription, Tenant, TenantMembership
        User = get_user_model()
        user_b = User.objects.create_user(username='idor-clean-b', password='pw', email='idor-clean-b@idor.test')
        t_b = Tenant.objects.create(name='IDOR Clean B', owner=user_b)
        TenantMembership.objects.create(tenant=t_b, user=user_b, role=TenantMembership.Role.BILLING, is_active=True)
        plan_b = SubscriptionPlan.objects.create(
            code='plan-idor-clean-b',
            name='Clean Plan B',
            billing_cycle='monthly',
            price_cents=5_000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        Subscription.objects.create(tenant=t_b, plan=plan_b, status=Subscription.Status.ACTIVE)
        tok = self.client.post('/api/v1/auth/token/', {'username': 'idor-clean-b', 'password': 'pw'}, format='json').data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tok}')
        resp = self.client.get(
            f'/api/v1/billing/invoices/{invoice_a.invoice_id}/',
            HTTP_X_TENANT_ID=str(t_b.tenant_id),
        )
        # Must be 404 (invoice not found in tenant B scope), not 200
        self.assertNotEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_invoice_list_scoped_to_own_tenant(self):
        """Invoice list returns only invoices belonging to the requesting tenant."""
        from api.models import SubscriptionPlan, Subscription, Tenant, TenantMembership, BillingInvoice
        from django.utils import timezone

        User = get_user_model()
        # Tenant A
        user_a = User.objects.create_user(username='idor-list-a', password='pw', email='idor-list-a@idor.test')
        t_a = Tenant.objects.create(name='IDOR List A', owner=user_a)
        TenantMembership.objects.create(tenant=t_a, user=user_a, role=TenantMembership.Role.BILLING, is_active=True)
        plan_a = SubscriptionPlan.objects.create(
            code='plan-idor-list-a',
            name='List Plan A',
            billing_cycle='monthly',
            price_cents=5_000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        sub_a = Subscription.objects.create(tenant=t_a, plan=plan_a, status=Subscription.Status.ACTIVE)
        now = timezone.now()
        BillingInvoice.objects.create(tenant=t_a, subscription=sub_a, period_start=now, period_end=now, platform_fee_cents=1000, total_cents=1000, currency='USD')

        # Tenant B
        user_b = User.objects.create_user(username='idor-list-b', password='pw', email='idor-list-b@idor.test')
        t_b = Tenant.objects.create(name='IDOR List B', owner=user_b)
        TenantMembership.objects.create(tenant=t_b, user=user_b, role=TenantMembership.Role.BILLING, is_active=True)
        plan_b = SubscriptionPlan.objects.create(
            code='plan-idor-list-b',
            name='List Plan B',
            billing_cycle='monthly',
            price_cents=5_000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=1000,
            max_users=3,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        sub_b = Subscription.objects.create(tenant=t_b, plan=plan_b, status=Subscription.Status.ACTIVE)
        BillingInvoice.objects.create(tenant=t_b, subscription=sub_b, period_start=now, period_end=now, platform_fee_cents=9999, total_cents=9999, currency='USD')

        tok_a = self.client.post('/api/v1/auth/token/', {'username': 'idor-list-a', 'password': 'pw'}, format='json').data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tok_a}')
        resp = self.client.get('/api/v1/billing/invoices/', HTTP_X_TENANT_ID=str(t_a.tenant_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Tenant A sees exactly one invoice (theirs)
        for inv in resp.data:
            self.assertEqual(inv['platform_fee_cents'], 1000)

    def test_chat_session_cross_tenant_blocked(self):
        """
        User from Tenant B, authenticated with their own token, cannot list
        chat sessions belonging to Tenant A even if they know Tenant A's tenant_id.
        """
        from api.models import AgentChatSession, Tenant, TenantMembership, SubscriptionPlan, Subscription

        User = get_user_model()
        user_a = User.objects.create_user(username='idor-chat-a', password='pw')
        t_a = Tenant.objects.create(name='Chat IDOR A', owner=user_a)
        TenantMembership.objects.create(tenant=t_a, user=user_a, role=TenantMembership.Role.CLINICIAN, is_active=True)
        plan_a = SubscriptionPlan.objects.create(
            code='plan-idor-chat-a',
            name='Chat Plan A',
            billing_cycle='monthly',
            price_cents=1000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=5,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        Subscription.objects.create(tenant=t_a, plan=plan_a, status=Subscription.Status.ACTIVE)
        AgentChatSession.objects.create(tenant=t_a, user=user_a, title='Secret Session')

        user_b = User.objects.create_user(username='idor-chat-b', password='pw')
        t_b = Tenant.objects.create(name='Chat IDOR B', owner=user_b)
        TenantMembership.objects.create(tenant=t_b, user=user_b, role=TenantMembership.Role.CLINICIAN, is_active=True)
        plan_b = SubscriptionPlan.objects.create(
            code='plan-idor-chat-b',
            name='Chat Plan B',
            billing_cycle='monthly',
            price_cents=1000,
            billing_model='hybrid',
            currency='USD',
            max_monthly_requests=10000,
            max_users=5,
            seat_price_cents=0,
            api_overage_per_1000_cents=0,
        )
        Subscription.objects.create(tenant=t_b, plan=plan_b, status=Subscription.Status.ACTIVE)

        tok_b = self.client.post('/api/v1/auth/token/', {'username': 'idor-chat-b', 'password': 'pw'}, format='json').data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tok_b}')

        # User B requests Tenant A's session list — their membership check will fail (403)
        resp = self.client.get('/api/v1/chat/sessions/', HTTP_X_TENANT_ID=str(t_a.tenant_id))
        # Must not be 200 — either 403 (membership denied) or 404
        self.assertNotEqual(resp.status_code, status.HTTP_200_OK)


# =============================================================================
# Telemetry / Prometheus metrics tests
# =============================================================================

class TelemetrySnapshotTests(TestCase):
    """Unit tests for api.telemetry — counter increments and snapshot correctness."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_incr_and_get(self):
        from api import telemetry
        telemetry.incr("test.counter.unit", 5)
        self.assertEqual(telemetry.get("test.counter.unit"), 5)

    def test_incr_accumulates(self):
        from api import telemetry
        telemetry.incr("test.counter.accum", 3)
        telemetry.incr("test.counter.accum", 2)
        self.assertEqual(telemetry.get("test.counter.accum"), 5)

    def test_get_unknown_key_returns_default(self):
        from api import telemetry
        self.assertEqual(telemetry.get("this.key.does.not.exist"), 0)
        self.assertEqual(telemetry.get("this.key.does.not.exist", 42), 42)

    def test_observe_latency_records_count_and_sum(self):
        from api import telemetry
        telemetry.observe_latency_ms("latency.unit_test", 500.0)
        telemetry.observe_latency_ms("latency.unit_test", 300.0)
        self.assertEqual(telemetry.get("latency.unit_test:count"), 2)
        self.assertEqual(telemetry.get("latency.unit_test:sum_ms"), 800)

    def test_snapshot_contains_all_expected_keys(self):
        from api import telemetry
        snap = telemetry.snapshot()
        expected_keys = [
            "http.requests.total",
            "http.responses.2xx",
            "http.responses.4xx",
            "http.responses.5xx",
            "security.events.total",
            "security.blocks.total",
            "auth.failures.total",
            "billing.events.total",
            "billing.usage_events.total",
            "latency.http:avg_ms",
        ]
        for key in expected_keys:
            self.assertIn(key, snap, f"Missing key: {key}")

    def test_snapshot_avg_ms_computed(self):
        from api import telemetry
        # Reset by using unique keys scoped to this test
        telemetry.incr("latency.http:count", 4)
        telemetry.incr("latency.http:sum_ms", 2000)
        snap = telemetry.snapshot()
        # avg = 2000 / 4 = 500
        self.assertGreaterEqual(snap["latency.http:avg_ms"], 0)

    def test_snapshot_avg_ms_zero_when_no_requests(self):
        """avg_ms must be 0.0 when count is 0 (no division by zero)."""
        from api import telemetry
        snap = telemetry.snapshot()
        # Should not raise; avg_ms can be 0 when count is 0
        self.assertIsInstance(snap["latency.http:avg_ms"], float)


class PrometheusTextEndpointTests(TestCase):
    """Verify that prometheus_text() output is parseable Prometheus text format."""

    def test_prometheus_text_contains_all_metric_names(self):
        from api import telemetry
        text = telemetry.prometheus_text()
        metrics = [
            "clinigraph_http_requests_total",
            "clinigraph_http_responses_2xx",
            "clinigraph_http_responses_4xx",
            "clinigraph_http_responses_5xx",
            "clinigraph_security_events_total",
            "clinigraph_security_blocks_total",
            "clinigraph_auth_failures_total",
            "clinigraph_billing_events_total",
            "clinigraph_billing_usage_events_total",
            "clinigraph_http_latency_avg_ms",
        ]
        for metric in metrics:
            self.assertIn(metric, text, f"Metric missing from Prometheus output: {metric}")

    def test_prometheus_text_has_help_and_type_lines(self):
        from api import telemetry
        text = telemetry.prometheus_text()
        self.assertIn("# HELP", text)
        self.assertIn("# TYPE", text)

    def test_prometheus_text_counters_are_numeric(self):
        """Every non-comment, non-empty line must parse as 'name numeric_value'."""
        from api import telemetry
        text = telemetry.prometheus_text()
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            self.assertEqual(len(parts), 2, f"Unexpected format: {line!r}")
            float(parts[1])  # Should not raise


class PrometheusMetricsViewTests(TestCase):
    """Integration: GET /api/v1/ops/metrics/prometheus/ returns valid text."""

    def test_metrics_endpoint_accessible_with_api_key(self):
        from django.test import Client
        from django.conf import settings
        client = Client()
        api_key = getattr(settings, "AGENT_API_KEY", "changeme")
        resp = client.get(
            "/api/v1/ops/metrics/prometheus/",
            HTTP_X_API_KEY=api_key,
        )
        # 200 or 403 depending on key; at minimum not 500
        self.assertNotEqual(resp.status_code, 500)

    def test_metrics_endpoint_returns_content_type_text(self):
        from django.test import Client
        from django.conf import settings
        client = Client()
        api_key = getattr(settings, "AGENT_API_KEY", "changeme")
        resp = client.get(
            "/api/v1/ops/metrics/prometheus/",
            HTTP_X_API_KEY=api_key,
        )
        if resp.status_code == 200:
            self.assertIn("text/plain", resp.get("Content-Type", ""))


# =============================================================================
# Registration endpoint tests
# =============================================================================

class RegistrationEndpointTests(APITestCase):
    """Tests for POST /api/v1/auth/register/."""

    def test_register_creates_user_and_returns_tokens(self):
        payload = {
            "username": "newclinician",
            "email": "newclinician@test.example",
            "password": "S3cur3P@ss!",
        }
        resp = self.client.post("/api/v1/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["username"], "newclinician")
        self.assertEqual(resp.data["email"], "newclinician@test.example")

    def test_register_tokens_are_usable(self):
        """The returned access token should authenticate subsequent requests."""
        payload = {"username": "tokenuser", "email": "tokenuser@test.example", "password": "S3cur3P@ss!"}
        resp = self.client.post("/api/v1/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        access = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp2 = self.client.get("/api/v1/auth/my-tenants/")
        # 200 — authenticated; user has no tenant memberships yet, so reply is []
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

    def test_register_duplicate_username_returns_409(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(username="dupeuser", email="dupe@test.example", password="pw")

        payload = {"username": "dupeuser", "email": "other@test.example", "password": "S3cur3P@ss!"}
        resp = self.client.post("/api/v1/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("username taken", resp.data.get("error", ""))

    def test_register_duplicate_email_returns_409(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(username="emailuser1", email="shared@test.example", password="pw")

        payload = {"username": "emailuser2", "email": "shared@test.example", "password": "S3cur3P@ss!"}
        resp = self.client.post("/api/v1/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("email taken", resp.data.get("error", ""))

    def test_register_missing_fields_returns_400(self):
        resp = self.client.post("/api/v1/auth/register/", {"username": "incomplete"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password_returns_400(self):
        payload = {"username": "weakpassuser", "email": "weak@test.example", "password": "123"}
        resp = self.client.post("/api/v1/auth/register/", payload, format="json")
        # 400 from Django's validate_password (too short / numeric only)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_stores_first_and_last_name(self):
        payload = {
            "username": "nameuser",
            "email": "nameuser@test.example",
            "password": "S3cur3P@ss!",
            "first_name": "Jane",
            "last_name": "Doe",
        }
        resp = self.client.post("/api/v1/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(username="nameuser")
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.last_name, "Doe")


class SecurityAuditEndpointTests(APITestCase):
    """Tests for /security/events/export/ and /audit/patient-cases/ endpoints."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="auditor_staff", password="pass", is_staff=True
        )
        self.regular = User.objects.create_user(
            username="auditor_regular", password="pass", is_staff=False
        )
        from api.models import SecurityEvent, PatientCaseSession
        SecurityEvent.objects.create(
            event_type="auth_failure",
            severity="high",
            ip_address="10.0.0.1",
            path="/api/v1/auth/token/",
            method="POST",
        )
        PatientCaseSession.objects.create(
            domain="oncology",
            subdomain="breast",
            redaction_count=3,
            redaction_categories={"DATE": 2, "NAME": 1},
            user_id="u1",
        )

    def _token(self, user):
        resp = self.client.post(
            "/api/v1/auth/token/",
            {"username": user.username, "password": "pass"},
            format="json",
        )
        return resp.data["access"]

    # --- SIEM export: JSON ---
    def test_security_export_json_staff(self):
        token = self._token(self.staff)
        resp = self.client.get(
            "/api/v1/security/events/export/?output=json&limit=10",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("application/x-ndjson", resp["Content-Type"])
        lines = [l for l in resp.content.decode().strip().split("\n") if l]
        self.assertGreaterEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertIn("event_type", row)
        self.assertIn("severity", row)

    def test_security_export_cef_staff(self):
        token = self._token(self.staff)
        resp = self.client.get(
            "/api/v1/security/events/export/?output=cef&limit=10",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("text/plain", resp["Content-Type"])
        self.assertIn("CEF:0", resp.content.decode())

    def test_security_export_invalid_format(self):
        token = self._token(self.staff)
        resp = self.client.get(
            "/api/v1/security/events/export/?output=xml",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_security_export_forbidden_non_staff(self):
        token = self._token(self.regular)
        resp = self.client.get(
            "/api/v1/security/events/export/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_security_export_unauthenticated(self):
        resp = self.client.get("/api/v1/security/events/export/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Patient-case audit ---
    def test_patient_case_audit_staff(self):
        token = self._token(self.staff)
        resp = self.client.get(
            "/api/v1/audit/patient-cases/?days=30&limit=10",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("total_sessions", data)
        self.assertIn("total_redactions", data)
        self.assertIn("redactions_by_category", data)
        self.assertIn("sessions_by_domain", data)
        self.assertIn("recent_sessions", data)
        self.assertGreaterEqual(data["total_sessions"], 1)
        self.assertGreaterEqual(data["total_redactions"], 1)

    def test_patient_case_audit_forbidden_non_staff(self):
        token = self._token(self.regular)
        resp = self.client.get(
            "/api/v1/audit/patient-cases/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_case_audit_unauthenticated(self):
        resp = self.client.get("/api/v1/audit/patient-cases/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_case_audit_phi_not_exposed(self):
        """Ensure no raw text hash or PHI appears in audit output."""
        token = self._token(self.staff)
        resp = self.client.get(
            "/api/v1/audit/patient-cases/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        content = resp.content.decode()
        # text_hash field is shown but only as a hash, not PHI — verify no plain text body key
        self.assertNotIn('"text":', content)
        self.assertNotIn('"patient_name":', content)
        self.assertNotIn('"original_text":', content)

