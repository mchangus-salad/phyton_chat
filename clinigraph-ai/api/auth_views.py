from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import TenantMembership


class CliniGraphTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        memberships = list(
            TenantMembership.objects.filter(user=user, is_active=True)
            .select_related("tenant")
            .values("tenant__tenant_id", "tenant__name", "role")
        )
        token["tenant_memberships"] = [
            {
                "tenant_id": str(item["tenant__tenant_id"]),
                "tenant_name": item["tenant__name"],
                "role": item["role"],
            }
            for item in memberships
        ]
        token["roles"] = sorted({item["role"] for item in memberships})
        token["is_staff_user"] = bool(getattr(user, "is_staff", False))
        return token


class CliniGraphTokenObtainPairView(TokenObtainPairView):
    serializer_class = CliniGraphTokenObtainPairSerializer


class TenantMembershipSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    tenant_name = serializers.CharField()
    role = serializers.CharField()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@extend_schema(
    operation_id="auth_my_tenants",
    description="List active tenant memberships for authenticated user.",
    responses={200: TenantMembershipSerializer(many=True)},
)
def my_tenants(request):
    memberships = list(
        TenantMembership.objects.filter(user=request.user, is_active=True)
        .select_related("tenant")
        .values("tenant__tenant_id", "tenant__name", "role")
    )
    payload = [
        {
            "tenant_id": item["tenant__tenant_id"],
            "tenant_name": item["tenant__name"],
            "role": item["role"],
        }
        for item in memberships
    ]
    return Response(payload, status=status.HTTP_200_OK)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Refresh token to blacklist.")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@extend_schema(
    operation_id="auth_logout",
    description="Logout the current user by blacklisting the supplied refresh token.",
    request=LogoutSerializer,
    responses={200: {"type": "object", "properties": {"detail": {"type": "string"}}}},
)
def logout(request):
    serializer = LogoutSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response(
            {"error": "invalid payload", "detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        token = RefreshToken(serializer.validated_data["refresh"])
        token.blacklist()
    except TokenError as exc:
        return Response(
            {"error": "token error", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, default='', required=False)
    last_name = serializers.CharField(max_length=150, default='', required=False)


@api_view(["POST"])
@permission_classes([AllowAny])
@extend_schema(
    operation_id="auth_register",
    description="Register a new user account. Returns JWT tokens on success.",
    request=RegisterSerializer,
    responses={
        201: {
            "type": "object",
            "properties": {
                "access": {"type": "string"},
                "refresh": {"type": "string"},
                "user_id": {"type": "integer"},
                "username": {"type": "string"},
                "email": {"type": "string"},
            },
        }
    },
)
def register(request):
    User = get_user_model()
    serializer = RegisterSerializer(data=request.data or {})
    if not serializer.is_valid():
        return Response(
            {"error": "invalid payload", "detail": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    username = data["username"].strip()
    email = data["email"].strip().lower()
    password = data["password"]

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "username taken", "detail": "A user with that username already exists."},
            status=status.HTTP_409_CONFLICT,
        )
    if User.objects.filter(email=email).exists():
        return Response(
            {"error": "email taken", "detail": "A user with that email address already exists."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        validate_password(password)
    except DjangoValidationError as exc:
        return Response(
            {"error": "password_invalid", "detail": list(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
    )

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user_id": user.pk,
            "username": user.username,
            "email": user.email,
        },
        status=status.HTTP_201_CREATED,
    )
