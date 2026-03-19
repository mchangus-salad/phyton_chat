from django.core.management.base import BaseCommand, CommandError

from api.agent_ai.oncology_corpus import load_oncology_corpus
from api.agent_ai.service import AgentAIService


class Command(BaseCommand):
    help = "Import an oncology corpus from a JSON, CSV, or TXT file into the vector store."

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="Path to a .json, .csv, or .txt oncology corpus file")
        parser.add_argument("--domain", default="oncology", help="Domain label for imported documents")
        parser.add_argument("--subdomain", default="", help="Optional oncology subdomain, e.g. lung-cancer")

    def handle(self, *args, **options):
        file_path = options["file_path"]
        domain = options["domain"]
        subdomain = options["subdomain"] or None

        try:
            documents = load_oncology_corpus(file_path)
        except Exception as exc:
            raise CommandError(f"Failed to load corpus: {exc}") from exc

        if not documents:
            raise CommandError("Corpus file did not contain any importable documents")

        service = AgentAIService(domain=domain, subdomain=subdomain, initialize_graph=False)
        try:
            result = service.ingest_documents(documents=documents, domain=domain, subdomain=subdomain)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Imported {result.documents_indexed} documents into domain '{result.domain}'"
                    f" with subdomain '{result.subdomain or 'default'}' from {file_path}."
                )
            )
        finally:
            service.close()