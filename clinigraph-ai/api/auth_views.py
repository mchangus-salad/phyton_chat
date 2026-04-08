from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema

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
