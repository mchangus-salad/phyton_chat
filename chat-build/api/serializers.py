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


class DomainQueryResponseSerializer(AgentQueryResponseSerializer):
    domain = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    safety_notice = serializers.CharField()


class KnowledgeDocumentSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, trim_whitespace=True)
    text = serializers.CharField(max_length=12000, allow_blank=False, trim_whitespace=True)
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    cancer_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    biomarkers = serializers.ListField(
        child=serializers.CharField(max_length=128, trim_whitespace=True),
        required=False,
        allow_empty=True,
    )
    evidence_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    publication_year = serializers.IntegerField(required=False, min_value=1800, max_value=2100)
    created_at = serializers.DateTimeField(required=False)


class OncologyTrainingSerializer(serializers.Serializer):
    corpus_name = serializers.CharField(max_length=128, required=False, default="oncology-research")
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    dedup_mode = serializers.ChoiceField(required=False, default="upsert", choices=["upsert", "batch-dedup", "versioned"])
    version_tag = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    documents = KnowledgeDocumentSerializer(many=True, allow_empty=False)


class OncologyTrainingResponseSerializer(serializers.Serializer):
    domain = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    corpus_name = serializers.CharField()
    documents_received = serializers.IntegerField()
    duplicates_dropped = serializers.IntegerField(required=False)
    documents_indexed = serializers.IntegerField()
    dedup_mode = serializers.CharField(required=False)
    version_tag = serializers.CharField(required=False, allow_blank=True)
    request_id = serializers.CharField()


class OncologyQuerySerializer(AgentQuerySerializer):
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)


class OncologyFileUploadSerializer(serializers.Serializer):
    corpus_name = serializers.CharField(max_length=128, required=False, default="oncology-upload")
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    file = serializers.FileField()


class OncologyEvidenceSearchSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    subdomain = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    cancer_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    biomarker = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    evidence_type = serializers.CharField(max_length=128, required=False, allow_blank=True, trim_whitespace=True)
    publication_year_from = serializers.IntegerField(required=False, min_value=1800, max_value=2100)
    publication_year_to = serializers.IntegerField(required=False, min_value=1800, max_value=2100)
    rerank = serializers.BooleanField(required=False, default=True)
    max_results = serializers.IntegerField(required=False, min_value=1, max_value=20, default=5)


class EvidenceDocumentSerializer(serializers.Serializer):
    citation_id = serializers.CharField()
    citation_label = serializers.CharField()
    source = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True)
    text = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    cancer_type = serializers.CharField(required=False, allow_blank=True)
    biomarkers = serializers.ListField(child=serializers.CharField(), required=False)
    evidence_type = serializers.CharField(required=False, allow_blank=True)
    publication_year = serializers.IntegerField(required=False)
    score = serializers.FloatField(required=False)
    rerank_score = serializers.FloatField(required=False)


class OncologyEvidenceSearchResponseSerializer(serializers.Serializer):
    domain = serializers.CharField()
    subdomain = serializers.CharField(required=False, allow_blank=True)
    query = serializers.CharField()
    evidence = EvidenceDocumentSerializer(many=True)
    request_id = serializers.CharField()
    safety_notice = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    request_id = serializers.CharField(required=False)
    detail = serializers.JSONField(required=False)
