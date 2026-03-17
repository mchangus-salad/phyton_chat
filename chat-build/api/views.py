import logging

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework import status

from .permissions import HasAgentApiKeyOrAuthenticated
from .serializers import (
    AgentQueryResponseSerializer,
    AgentQuerySerializer,
    ErrorResponseSerializer,
    HealthResponseSerializer,
)
from .throttles import AgentAnonRateThrottle, AgentUserRateThrottle


logger = logging.getLogger(__name__)


SERVICE = None


def _get_service():
	"""Create a single service instance per worker process."""
	global SERVICE
	if SERVICE is None:
		from .agent_ai.service import AgentAIService

		SERVICE = AgentAIService()
	return SERVICE


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
	"""Run the AgentAI graph and return answer + cache metadata."""
	serializer = AgentQuerySerializer(data=request.data or {})
	if not serializer.is_valid():
		return Response(
			{'error': 'invalid payload', 'detail': serializer.errors},
			status=status.HTTP_400_BAD_REQUEST,
		)

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
		logger.exception('agent execution failed request_id=%s user_id=%s', request_id, user_id)
		return Response(
			{
				'error': 'agent execution failed',
				'request_id': request_id,
			},
			status=status.HTTP_500_INTERNAL_SERVER_ERROR,
		)
