from rest_framework import serializers


class AgentQuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    user_id = serializers.CharField(max_length=128, required=False, default="anonymous")


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    framework = serializers.CharField()


class AgentQueryResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    cache_hit = serializers.BooleanField()
    request_id = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    request_id = serializers.CharField(required=False)
    detail = serializers.JSONField(required=False)
