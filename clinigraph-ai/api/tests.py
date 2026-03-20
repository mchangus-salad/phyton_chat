from types import SimpleNamespace
from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
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
        old_invoice.save(update_fields=['generated_at', 'status'])

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
