from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import agent_query, health, oncology_evidence_search, oncology_query, oncology_train, oncology_upload

urlpatterns = [
    path('health/', health, name='health'),
    path('auth/token/', TokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('agent/query/', agent_query, name='agent-query'),
    path('agent/oncology/evidence/', oncology_evidence_search, name='oncology-evidence-search'),
    path('agent/oncology/query/', oncology_query, name='oncology-query'),
    path('agent/oncology/train/', oncology_train, name='oncology-train'),
    path('agent/oncology/upload/', oncology_upload, name='oncology-upload'),
]
