from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    agent_query,
    health,
    medical_evidence_search,
    medical_query,
    medical_train,
    medical_upload,
    oncology_evidence_search,
    oncology_query,
    oncology_train,
    oncology_upload,
)

urlpatterns = [
    path('health/', health, name='health'),
    path('auth/token/', TokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('agent/query/', agent_query, name='agent-query'),
    path('agent/medical/evidence/', medical_evidence_search, name='medical-evidence-search'),
    path('agent/medical/query/', medical_query, name='medical-query'),
    path('agent/medical/train/', medical_train, name='medical-train'),
    path('agent/medical/upload/', medical_upload, name='medical-upload'),
    path('agent/oncology/evidence/', oncology_evidence_search, name='oncology-evidence-search'),
    path('agent/oncology/query/', oncology_query, name='oncology-query'),
    path('agent/oncology/train/', oncology_train, name='oncology-train'),
    path('agent/oncology/upload/', oncology_upload, name='oncology-upload'),
]
