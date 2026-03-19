from django.core.management.base import BaseCommand, CommandError

from api.agent_ai.oncology_corpus import load_oncology_corpus
from api.agent_ai.service import AgentAIService


class Command(BaseCommand):
    help = "Import a generic medical corpus from JSON, CSV, or TXT into the vector store."

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="Path to a .json, .csv, or .txt medical corpus file")
        parser.add_argument("--domain", default="medical", help="Medical domain label, e.g. cardiology")
        parser.add_argument("--subdomain", default="", help="Optional medical subdomain, e.g. heart-failure")
        parser.add_argument(
            "--dedup-mode",
            default="upsert",
            choices=["upsert", "batch-dedup", "versioned"],
            help="Ingestion strategy for duplicate handling",
        )
        parser.add_argument("--version-tag", default="", help="Optional version tag used by versioned mode")

    def handle(self, *args, **options):
        file_path = options["file_path"]
        domain = options["domain"]
        subdomain = options["subdomain"] or None
        dedup_mode = options["dedup_mode"]
        version_tag = options["version_tag"] or None

        try:
            documents = load_oncology_corpus(file_path)
        except Exception as exc:
            raise CommandError(f"Failed to load corpus: {exc}") from exc

        if not documents:
            raise CommandError("Corpus file did not contain any importable documents")

        service = AgentAIService(domain=domain, subdomain=subdomain, initialize_graph=False)
        try:
            result = service.ingest_documents(
                documents=documents,
                domain=domain,
                subdomain=subdomain,
                dedup_mode=dedup_mode,
                version_tag=version_tag,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Imported {result.documents_indexed} documents into domain '{result.domain}'"
                    f" with subdomain '{result.subdomain or 'default'}' from {file_path}."
                )
            )
        finally:
            service.close()
