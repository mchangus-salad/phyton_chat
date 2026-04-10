"""
Celery tasks for asynchronous corpus ingestion.

These tasks wrap the synchronous CliniGraphService.ingest_documents() call
so that heavy ingestion jobs can run in a background worker without blocking
the HTTP request/response cycle.

Lifecycle:
  HTTP POST /train  → creates IngestionJob(status=pending) → fires task → returns 202
  Worker picks up   → sets status=running → calls ingest_documents()
  On success        → sets status=completed, result=<summary>
  On failure        → sets status=failed, error=<message>

Callers can poll GET /api/v1/jobs/<job_id>/ to observe progress.
"""

import base64
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_job(job_id: str):
    from .models import IngestionJob
    return IngestionJob.objects.get(pk=job_id)


def _mark_running(job_id: str, task_id: str):
    from .models import IngestionJob
    IngestionJob.objects.filter(pk=job_id).update(
        task_id=task_id,
        status=IngestionJob.STATUS_RUNNING,
        updated_at=timezone.now(),
    )


def _mark_completed(job_id: str, result_data: dict):
    from .models import IngestionJob
    IngestionJob.objects.filter(pk=job_id).update(
        status=IngestionJob.STATUS_COMPLETED,
        result=result_data,
        updated_at=timezone.now(),
    )


def _mark_failed(job_id: str, error_msg: str):
    from .models import IngestionJob
    IngestionJob.objects.filter(pk=job_id).update(
        status=IngestionJob.STATUS_FAILED,
        error=error_msg,
        updated_at=timezone.now(),
    )


@shared_task(bind=True, max_retries=0, name='api.tasks.ingest_corpus')
def ingest_corpus(self, job_id: str, domain: str, subdomain, documents: list,
                  corpus_name: str, dedup_mode: str = 'upsert', version_tag=None):
    """
    Asynchronously ingest a list of knowledge documents into the vector store.

    Args:
        job_id: UUID string of the IngestionJob record to update.
        domain: Medical domain (e.g. 'oncology', 'cardiology').
        subdomain: Optional sub-domain narrowing (may be None).
        documents: List of document dicts already validated by KnowledgeDocumentSerializer.
        corpus_name: Human-readable label stored in the job record.
        dedup_mode: 'upsert' | 'batch-dedup' | 'versioned'.
        version_tag: Optional version string for 'versioned' dedup mode.
    """
    _mark_running(job_id, self.request.id or '')
    try:
        from .agent_ai.service import CliniGraphService
        service = CliniGraphService(domain=domain, subdomain=subdomain)
        result = service.ingest_documents(
            documents=documents,
            domain=domain,
            subdomain=subdomain,
            dedup_mode=dedup_mode,
            version_tag=version_tag,
        )
        _mark_completed(job_id, {
            'domain': result.domain,
            'subdomain': result.subdomain or '',
            'corpus_name': corpus_name,
            'documents_received': result.documents_received,
            'duplicates_dropped': result.duplicates_dropped,
            'documents_indexed': result.documents_indexed,
            'dedup_mode': result.dedup_mode,
            'version_tag': result.version_tag,
        })
        logger.info('ingest_corpus completed job_id=%s domain=%s indexed=%d',
                    job_id, domain, result.documents_indexed)
    except Exception as exc:
        error_msg = f'{type(exc).__name__}: {exc}'
        _mark_failed(job_id, error_msg)
        logger.exception('ingest_corpus failed job_id=%s domain=%s', job_id, domain)


@shared_task(bind=True, max_retries=0, name='api.tasks.ingest_file')
def ingest_file(self, job_id: str, domain: str, subdomain, filename: str,
                file_bytes_b64: str, corpus_name: str, dedup_mode: str = 'batch-dedup'):
    """
    Asynchronously ingest a corpus file (uploaded via multipart) into the vector store.

    The raw file bytes are base64-encoded for JSON-safe transport through the Celery broker.

    Args:
        job_id: UUID string of the IngestionJob record to update.
        domain: Medical domain (e.g. 'oncology').
        subdomain: Optional sub-domain.
        filename: Original filename — used to infer content format (json/csv/txt).
        file_bytes_b64: Base64-encoded raw bytes of the uploaded file.
        corpus_name: Human-readable label stored in the job record.
        dedup_mode: Ingestion dedup strategy.
    """
    _mark_running(job_id, self.request.id or '')
    try:
        file_bytes = base64.b64decode(file_bytes_b64)
        # Both oncology and generic medical uploads use the same JSON/CSV/TXT parser.
        from .agent_ai.oncology_corpus import load_oncology_corpus_content
        documents = load_oncology_corpus_content(filename, file_bytes)

        from .agent_ai.service import CliniGraphService
        service = CliniGraphService(domain=domain, subdomain=subdomain)
        result = service.ingest_documents(
            documents=documents,
            domain=domain,
            subdomain=subdomain,
            dedup_mode=dedup_mode,
        )
        _mark_completed(job_id, {
            'domain': result.domain,
            'subdomain': result.subdomain or '',
            'corpus_name': corpus_name,
            'documents_received': result.documents_received,
            'duplicates_dropped': result.duplicates_dropped,
            'documents_indexed': result.documents_indexed,
            'dedup_mode': result.dedup_mode,
            'version_tag': result.version_tag,
        })
        logger.info('ingest_file completed job_id=%s domain=%s filename=%s indexed=%d',
                    job_id, domain, filename, result.documents_indexed)
    except Exception as exc:
        error_msg = f'{type(exc).__name__}: {exc}'
        _mark_failed(job_id, error_msg)
        logger.exception('ingest_file failed job_id=%s domain=%s filename=%s', job_id, domain, filename)
