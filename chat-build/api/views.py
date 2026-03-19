import logging

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .permissions import HasAgentApiKeyOrAuthenticated
from .agent_ai.oncology_corpus import load_oncology_corpus_content
from .serializers import (
	AgentQueryResponseSerializer,
	AgentQuerySerializer,
	DomainQueryResponseSerializer,
	ErrorResponseSerializer,
	HealthResponseSerializer,
	OncologyEvidenceSearchResponseSerializer,
	OncologyEvidenceSearchSerializer,
	OncologyFileUploadSerializer,
	OncologyQuerySerializer,
	OncologyTrainingResponseSerializer,
	OncologyTrainingSerializer,
)
from .throttles import AgentAnonRateThrottle, AgentUserRateThrottle


logger = logging.getLogger(__name__)

SERVICES = {}
ONCOLOGY_SAFETY_NOTICE = (
	'This oncology workflow is intended for research support only and does not replace medical diagnosis, '
	'treatment planning, or specialist review.'
)


def _get_service(domain: str | None = None, subdomain: str | None = None):
	"""Create a single service instance per worker process and domain."""
	service_key = f"{domain or 'general'}::{subdomain or 'default'}"
	if service_key not in SERVICES:
		from .agent_ai.service import AgentAIService

		SERVICES[service_key] = AgentAIService(domain=domain, subdomain=subdomain)
	return SERVICES[service_key]


def _validation_error_response(serializer):
	return Response(
		{'error': 'invalid payload', 'detail': serializer.errors},
		status=status.HTTP_400_BAD_REQUEST,
	)


def _agent_failure_response(request_id: str, user_id: str):
	logger.exception('agent execution failed request_id=%s user_id=%s', request_id, user_id)
	return Response(
		{
			'error': 'agent execution failed',
			'request_id': request_id,
		},
		status=status.HTTP_500_INTERNAL_SERVER_ERROR,
	)


@extend_schema(
	operation_id='health',
	description='Health check endpoint used by local automation and uptime checks.',
	responses={200: HealthResponseSerializer},
	auth=[],
)
@api_view(['GET'])
def health(request):
	"""Lightweight health endpoint used by automation and local smoke tests."""
	return Response({'status': 'ok', 'framework': 'django'})


@extend_schema(
	operation_id='agent_query',
	description='Execute AgentAI and return an answer. Authenticate with JWT bearer token or X-API-Key.',
	request=AgentQuerySerializer,
	parameters=[
		OpenApiParameter(
			name='X-API-Key',
			type=OpenApiTypes.STR,
			location=OpenApiParameter.HEADER,
			required=False,
			description='API key alternative to JWT bearer authentication.',
		),
	],
	responses={
		200: AgentQueryResponseSerializer,
		400: ErrorResponseSerializer,
		401: ErrorResponseSerializer,
		403: ErrorResponseSerializer,
		429: ErrorResponseSerializer,
		500: ErrorResponseSerializer,
	},
	auth=['BearerAuth', 'ApiKeyAuth'],
	examples=[
		OpenApiExample(
			'Agent Query Example',
			value={'question': 'What is our refund policy?', 'user_id': 'u-123'},
			request_only=True,
		),
	],
)
@api_view(['POST'])
@permission_classes([HasAgentApiKeyOrAuthenticated])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def agent_query(request):
	"""Run the default AgentAI graph and return answer + cache metadata."""
	serializer = AgentQuerySerializer(data=request.data or {})
	if not serializer.is_valid():
		return _validation_error_response(serializer)

	payload = serializer.validated_data
	question = payload['question']
	user_id = payload.get('user_id', 'anonymous')
	request_id = getattr(request, 'request_id', 'n/a')

	try:
		service = _get_service()
		result = service.ask(question=question, user_id=user_id)
		return Response(
			{
				'answer': result.answer,
				'cache_hit': result.cache_hit,
				'request_id': request_id,
			},
			status=status.HTTP_200_OK,
		)
	except Exception:
		return _agent_failure_response(request_id=request_id, user_id=user_id)


@extend_schema(
	operation_id='oncology_train',
	description='Ingest an oncology knowledge corpus into the vector store for later oncology-focused retrieval.',
	request=OncologyTrainingSerializer,
	parameters=[
		OpenApiParameter(
			name='X-API-Key',
			type=OpenApiTypes.STR,
			location=OpenApiParameter.HEADER,
			required=False,
			description='API key alternative to JWT bearer authentication.',
		),
	],
	responses={
		200: OncologyTrainingResponseSerializer,
		400: ErrorResponseSerializer,
		401: ErrorResponseSerializer,
		403: ErrorResponseSerializer,
		429: ErrorResponseSerializer,
		500: ErrorResponseSerializer,
	},
	auth=['BearerAuth', 'ApiKeyAuth'],
)
@api_view(['POST'])
@permission_classes([HasAgentApiKeyOrAuthenticated])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def oncology_train(request):
	"""Ingest oncology documents into the knowledge base for domain-scoped retrieval.

	Supports ingestion strategies:
	- upsert: deterministic id update per source
	- batch-dedup: removes duplicates in current payload
	- versioned: appends @version tag to source keys
	"""
	serializer = OncologyTrainingSerializer(data=request.data or {})
	if not serializer.is_valid():
		return _validation_error_response(serializer)

	payload = serializer.validated_data
	subdomain = payload.get('subdomain') or None
	request_id = getattr(request, 'request_id', 'n/a')

	try:
		service = _get_service(domain='oncology', subdomain=subdomain)
		result = service.ingest_documents(
			documents=payload['documents'],
			domain='oncology',
			subdomain=subdomain,
			dedup_mode=payload.get('dedup_mode', 'upsert'),
			version_tag=payload.get('version_tag') or None,
		)
		return Response(
			{
				'domain': result.domain,
				'subdomain': result.subdomain or '',
				'corpus_name': payload['corpus_name'],
				'documents_received': result.documents_received,
				'duplicates_dropped': result.duplicates_dropped,
				'documents_indexed': result.documents_indexed,
				'dedup_mode': result.dedup_mode,
				'version_tag': result.version_tag,
				'request_id': request_id,
			},
			status=status.HTTP_200_OK,
		)
	except Exception:
		logger.exception('oncology ingestion failed request_id=%s', request_id)
		return Response(
			{
				'error': 'oncology ingestion failed',
				'request_id': request_id,
			},
			status=status.HTTP_500_INTERNAL_SERVER_ERROR,
		)


@extend_schema(
	operation_id='oncology_query',
	description='Run an oncology-focused retrieval workflow over the oncology corpus. Research support only.',
	request=OncologyQuerySerializer,
	parameters=[
		OpenApiParameter(
			name='X-API-Key',
			type=OpenApiTypes.STR,
			location=OpenApiParameter.HEADER,
			required=False,
			description='API key alternative to JWT bearer authentication.',
		),
	],
	responses={
		200: DomainQueryResponseSerializer,
		400: ErrorResponseSerializer,
		401: ErrorResponseSerializer,
		403: ErrorResponseSerializer,
		429: ErrorResponseSerializer,
		500: ErrorResponseSerializer,
	},
	auth=['BearerAuth', 'ApiKeyAuth'],
	examples=[
		OpenApiExample(
			'Oncology Query Example',
			value={'question': 'Summarize common biomarkers for lung cancer research.', 'user_id': 'researcher-1'},
			request_only=True,
		),
	],
)
@api_view(['POST'])
@permission_classes([HasAgentApiKeyOrAuthenticated])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def oncology_query(request):
	"""Run the oncology-specific AgentAI graph and include a medical safety notice."""
	serializer = OncologyQuerySerializer(data=request.data or {})
	if not serializer.is_valid():
		return _validation_error_response(serializer)

	payload = serializer.validated_data
	question = payload['question']
	user_id = payload.get('user_id', 'anonymous')
	subdomain = payload.get('subdomain') or None
	request_id = getattr(request, 'request_id', 'n/a')

	try:
		service = _get_service(domain='oncology', subdomain=subdomain)
		result = service.ask(question=question, user_id=user_id)
		return Response(
			{
				'answer': result.answer,
				'cache_hit': result.cache_hit,
				'request_id': request_id,
				'domain': 'oncology',
				'subdomain': subdomain or '',
				'safety_notice': ONCOLOGY_SAFETY_NOTICE,
			},
			status=status.HTTP_200_OK,
		)
	except Exception:
		return _agent_failure_response(request_id=request_id, user_id=user_id)


@extend_schema(
	operation_id='oncology_evidence_search',
	description='Retrieve top oncology evidence documents with optional cancer type and biomarker filters.',
	request=OncologyEvidenceSearchSerializer,
	parameters=[
		OpenApiParameter(
			name='X-API-Key',
			type=OpenApiTypes.STR,
			location=OpenApiParameter.HEADER,
			required=False,
			description='API key alternative to JWT bearer authentication.',
		),
	],
	responses={
		200: OncologyEvidenceSearchResponseSerializer,
		400: ErrorResponseSerializer,
		401: ErrorResponseSerializer,
		403: ErrorResponseSerializer,
		429: ErrorResponseSerializer,
		500: ErrorResponseSerializer,
	},
	auth=['BearerAuth', 'ApiKeyAuth'],
	examples=[
		OpenApiExample(
			'Oncology Evidence Search Example',
			value={'query': 'EGFR resistance pathways', 'cancer_type': 'lung cancer', 'biomarker': 'EGFR', 'max_results': 3},
			request_only=True,
		),
	],
)
@api_view(['POST'])
@permission_classes([HasAgentApiKeyOrAuthenticated])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def oncology_evidence_search(request):
	"""Return structured oncology evidence snippets with optional metadata filters.

	Filters supported:
	- subdomain
	- cancer_type
	- biomarker
	- evidence_type
	- publication year range
	- optional rerank strategy
	"""
	serializer = OncologyEvidenceSearchSerializer(data=request.data or {})
	if not serializer.is_valid():
		return _validation_error_response(serializer)

	payload = serializer.validated_data
	request_id = getattr(request, 'request_id', 'n/a')
	subdomain = payload.get('subdomain') or None

	try:
		service = _get_service(domain='oncology', subdomain=subdomain)
		result = service.search_evidence(
			query=payload['query'],
			max_results=payload['max_results'],
			cancer_type=payload.get('cancer_type') or None,
			biomarker=payload.get('biomarker') or None,
			subdomain=subdomain,
			evidence_type=payload.get('evidence_type') or None,
			publication_year_from=payload.get('publication_year_from'),
			publication_year_to=payload.get('publication_year_to'),
			rerank=payload.get('rerank', True),
		)
		return Response(
			{
				'domain': result.domain,
				'subdomain': result.subdomain or '',
				'query': payload['query'],
				'evidence': result.evidence,
				'request_id': request_id,
				'safety_notice': ONCOLOGY_SAFETY_NOTICE,
			},
			status=status.HTTP_200_OK,
		)
	except Exception:
		logger.exception('oncology evidence search failed request_id=%s', request_id)
		return Response(
			{
				'error': 'oncology evidence search failed',
				'request_id': request_id,
			},
			status=status.HTTP_500_INTERNAL_SERVER_ERROR,
		)


@extend_schema(
	operation_id='oncology_upload',
	description='Upload a JSON, CSV, or TXT oncology corpus file for ingestion into a selected oncology subdomain.',
	request=OncologyFileUploadSerializer,
	parameters=[
		OpenApiParameter(
			name='X-API-Key',
			type=OpenApiTypes.STR,
			location=OpenApiParameter.HEADER,
			required=False,
			description='API key alternative to JWT bearer authentication.',
		),
	],
	responses={
		200: OncologyTrainingResponseSerializer,
		400: ErrorResponseSerializer,
		401: ErrorResponseSerializer,
		403: ErrorResponseSerializer,
		429: ErrorResponseSerializer,
		500: ErrorResponseSerializer,
	},
	auth=['BearerAuth', 'ApiKeyAuth'],
)
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([HasAgentApiKeyOrAuthenticated])
@throttle_classes([AgentAnonRateThrottle, AgentUserRateThrottle])
def oncology_upload(request):
	"""Upload and ingest an oncology corpus file directly through the API."""
	serializer = OncologyFileUploadSerializer(data=request.data)
	if not serializer.is_valid():
		return _validation_error_response(serializer)

	payload = serializer.validated_data
	request_id = getattr(request, 'request_id', 'n/a')
	uploaded_file = payload['file']
	subdomain = payload.get('subdomain') or None

	try:
		documents = load_oncology_corpus_content(uploaded_file.name, uploaded_file.read())
		service = _get_service(domain='oncology', subdomain=subdomain)
		result = service.ingest_documents(
			documents=documents,
			domain='oncology',
			subdomain=subdomain,
			dedup_mode='batch-dedup',
		)
		return Response(
			{
				'domain': result.domain,
				'subdomain': result.subdomain or '',
				'corpus_name': payload['corpus_name'],
				'documents_received': result.documents_received,
				'duplicates_dropped': result.duplicates_dropped,
				'documents_indexed': result.documents_indexed,
				'dedup_mode': result.dedup_mode,
				'version_tag': result.version_tag,
				'request_id': request_id,
			},
			status=status.HTTP_200_OK,
		)
	except ValueError as exc:
		return Response(
			{'error': 'invalid upload file', 'detail': str(exc), 'request_id': request_id},
			status=status.HTTP_400_BAD_REQUEST,
		)
	except Exception:
		logger.exception('oncology upload failed request_id=%s', request_id)
		return Response(
			{'error': 'oncology upload failed', 'request_id': request_id},
			status=status.HTTP_500_INTERNAL_SERVER_ERROR,
		)
