import json
import os
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from api.agent_ai.service import CliniGraphService


ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_MIN_INTERVAL_SECONDS = 0.34
DEFAULT_STATE_PATH = Path("/app/data/corpus_state/auto_update_state.json")


SEARCH_TOPICS = [
    {
        "domain": "oncology",
        "subdomain": "lung-cancer",
        "query": "non-small cell lung cancer EGFR randomized trial",
    },
    {
        "domain": "oncology",
        "subdomain": "breast-cancer",
        "query": "metastatic breast cancer HER2 trial",
    },
    {
        "domain": "oncology",
        "subdomain": "hematologic-oncology",
        "query": "multiple myeloma daratumumab phase 3",
    },
    {
        "domain": "cardiology",
        "subdomain": "heart-failure",
        "query": "heart failure reduced ejection fraction randomized trial",
    },
    {
        "domain": "cardiology",
        "subdomain": "acute-coronary-syndrome",
        "query": "acute coronary syndrome ticagrelor trial",
    },
    {
        "domain": "cardiology",
        "subdomain": "dyslipidemia",
        "query": "PCSK9 inhibitor cardiovascular outcomes trial",
    },
    {
        "domain": "neurology",
        "subdomain": "dementia",
        "query": "Alzheimer disease amyloid antibody trial",
    },
    {
        "domain": "neurology",
        "subdomain": "stroke",
        "query": "ischemic stroke thrombectomy randomized trial",
    },
    {
        "domain": "neurology",
        "subdomain": "multiple-sclerosis",
        "query": "multiple sclerosis ocrelizumab trial",
    },
    {
        "domain": "endocrinology",
        "subdomain": "diabetes",
        "query": "type 2 diabetes cardiovascular outcomes trial",
    },
    {
        "domain": "endocrinology",
        "subdomain": "obesity",
        "query": "obesity semaglutide randomized trial",
    },
    {
        "domain": "endocrinology",
        "subdomain": "bone-metabolism",
        "query": "osteoporosis fracture prevention trial",
    },
    {
        "domain": "pulmonology",
        "subdomain": "COPD",
        "query": "COPD triple therapy randomized trial",
    },
    {
        "domain": "pulmonology",
        "subdomain": "asthma",
        "query": "severe asthma biologic randomized trial",
    },
    {
        "domain": "pulmonology",
        "subdomain": "interstitial-lung-disease",
        "query": "idiopathic pulmonary fibrosis nintedanib trial",
    },
    {
        "domain": "rheumatology",
        "subdomain": "rheumatoid-arthritis",
        "query": "rheumatoid arthritis JAK inhibitor trial",
    },
    {
        "domain": "rheumatology",
        "subdomain": "lupus",
        "query": "systemic lupus anifrolumab trial",
    },
    {
        "domain": "rheumatology",
        "subdomain": "spondyloarthropathy",
        "query": "ankylosing spondylitis secukinumab trial",
    },
    {
        "domain": "infectious-diseases",
        "subdomain": "HIV",
        "query": "HIV antiretroviral randomized trial",
    },
    {
        "domain": "infectious-diseases",
        "subdomain": "hepatitis",
        "query": "hepatitis C direct acting antiviral trial",
    },
    {
        "domain": "infectious-diseases",
        "subdomain": "tuberculosis",
        "query": "multidrug resistant tuberculosis randomized trial",
    },
    {
        "domain": "infectious-diseases",
        "subdomain": "infectious-disease-critical-care",
        "query": "sepsis management randomized trial",
    },
    {
        "domain": "gastroenterology",
        "subdomain": "IBD",
        "query": "ulcerative colitis biologic randomized trial",
    },
    {
        "domain": "gastroenterology",
        "subdomain": "liver-disease",
        "query": "nonalcoholic steatohepatitis fibrosis trial",
    },
    {
        "domain": "gastroenterology",
        "subdomain": "gastric-disease",
        "query": "Helicobacter pylori eradication trial",
    },
    {
        "domain": "hematology",
        "subdomain": "myeloid-malignancy",
        "query": "acute myeloid leukemia phase 3 trial",
    },
    {
        "domain": "hematology",
        "subdomain": "lymphoid-malignancy",
        "query": "diffuse large B-cell lymphoma trial",
    },
    {
        "domain": "hematology",
        "subdomain": "hemoglobinopathy",
        "query": "sickle cell disease randomized trial",
    },
]


class Command(BaseCommand):
    help = "Fetch recent PubMed evidence and ingest it into CliniGraph domains."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-back",
            type=int,
            default=30,
            help="Fetch papers from the last N days (default: 30)",
        )
        parser.add_argument(
            "--max-per-topic",
            type=int,
            default=10,
            help="Maximum PubMed IDs to fetch per topic (default: 10)",
        )
        parser.add_argument(
            "--domain-filter",
            default="",
            help="Optional comma-separated list of domains to include",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only fetch and parse, do not ingest",
        )

    def handle(self, *args, **options):
        days_back = max(1, options["days_back"])
        max_per_topic = max(1, options["max_per_topic"])
        dry_run = bool(options["dry_run"])
        filters = {
            item.strip().lower()
            for item in str(options["domain_filter"] or "").split(",")
            if item.strip()
        }

        state = self._load_state(DEFAULT_STATE_PATH)
        state.setdefault("seen_pmids", [])
        seen_pmids = set(state["seen_pmids"])

        total_ingested = 0
        total_fetched = 0
        total_topics = 0

        for topic in SEARCH_TOPICS:
            domain = topic["domain"]
            if filters and domain.lower() not in filters:
                continue

            subdomain = topic["subdomain"]
            query = topic["query"]
            total_topics += 1

            self.stdout.write(f"[auto-update] topic={domain}/{subdomain} query='{query}'")
            pmids = self._esearch(query=query, days_back=days_back, max_results=max_per_topic)
            new_pmids = [pmid for pmid in pmids if pmid not in seen_pmids]

            if not new_pmids:
                self.stdout.write("  - no new PMIDs")
                continue

            medline_text = self._efetch_medline(new_pmids)
            records = self._parse_medline_records(medline_text)
            documents = []

            for record in records:
                doc = self._record_to_document(record=record, domain=domain, subdomain=subdomain)
                if doc:
                    documents.append(doc)

            total_fetched += len(documents)
            if not documents:
                self.stdout.write("  - fetched but no valid records")
                continue

            if dry_run:
                self.stdout.write(f"  - dry-run parsed={len(documents)}")
            else:
                service = CliniGraphService(domain=domain, subdomain=subdomain, initialize_graph=False)
                try:
                    result = service.ingest_documents(
                        documents=documents,
                        domain=domain,
                        subdomain=subdomain,
                        dedup_mode="upsert",
                    )
                    total_ingested += result.documents_indexed
                    self.stdout.write(
                        f"  - ingested={result.documents_indexed} received={result.documents_received}"
                    )
                finally:
                    service.close()

            for pmid in new_pmids:
                seen_pmids.add(pmid)

        state["seen_pmids"] = sorted(seen_pmids)
        state["last_run_utc"] = datetime.now(UTC).isoformat()
        state["last_run_topics"] = total_topics
        state["last_run_fetched"] = total_fetched
        state["last_run_ingested"] = total_ingested
        self._save_state(DEFAULT_STATE_PATH, state)

        self.stdout.write(
            self.style.SUCCESS(
                "auto_update_corpus completed "
                f"topics={total_topics} fetched={total_fetched} ingested={total_ingested} dry_run={dry_run}"
            )
        )

    def _esearch(self, query: str, days_back: int, max_results: int) -> list[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(max_results),
            "sort": "pub date",
            "datetype": "pdat",
            "reldate": str(days_back),
        }
        api_key = os.getenv("NCBI_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key
        url = f"{ESEARCH_URL}?{urllib.parse.urlencode(params)}"
        payload = self._http_get(url)
        data = json.loads(payload.decode("utf-8"))
        ids = data.get("esearchresult", {}).get("idlist", [])
        return [str(item).strip() for item in ids if str(item).strip()]

    def _efetch_medline(self, pmids: list[str]) -> str:
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "medline",
            "retmode": "text",
        }
        api_key = os.getenv("NCBI_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key
        url = f"{EFETCH_URL}?{urllib.parse.urlencode(params)}"
        payload = self._http_get(url)
        return payload.decode("utf-8", errors="ignore")

    def _http_get(self, url: str) -> bytes:
        time.sleep(NCBI_MIN_INTERVAL_SECONDS)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CliniGraph-AI/1.0 (auto-update-corpus)",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()

    def _parse_medline_records(self, text: str) -> list[dict]:
        records = []
        current: dict[str, Any] = {}
        current_field = None

        for raw_line in text.splitlines():
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            if line.startswith("PMID- "):
                if current:
                    records.append(current)
                current = {"PMID": line.replace("PMID- ", "").strip()}
                current_field = "PMID"
                continue

            if len(line) >= 6 and line[4:6] == "- ":
                tag = line[:4].strip()
                value = line[6:].strip()
                if not value:
                    continue
                if tag in {"MH", "PT", "FAU", "AU"}:
                    values = current.setdefault(tag, [])
                    if isinstance(values, list):
                        values.append(value)
                else:
                    current[tag] = value
                current_field = tag
                continue

            if line.startswith("      ") and current_field:
                cont = line.strip()
                if not cont:
                    continue
                prev = current.get(current_field)
                if isinstance(prev, list):
                    if prev:
                        prev[-1] = f"{prev[-1]} {cont}".strip()
                elif isinstance(prev, str):
                    current[current_field] = f"{prev} {cont}".strip()

        if current:
            records.append(current)
        return records

    def _record_to_document(self, record: dict, domain: str, subdomain: str) -> dict | None:
        pmid = str(record.get("PMID", "")).strip()
        title = str(record.get("TI", "")).strip()
        abstract = str(record.get("AB", "")).strip()
        publication = str(record.get("DP", "")).strip()
        evidence_type = self._infer_evidence_type(record)
        markers = self._extract_markers(record)

        if not pmid or not title:
            return None

        publication_year = self._extract_year(publication)
        text_parts = [
            f"TITLE: {title}",
            f"ABSTRACT: {abstract}" if abstract else "",
            f"PUBLICATION: {publication}" if publication else "",
            f"PUBLICATION TYPES: {', '.join(record.get('PT', []))}" if record.get("PT") else "",
            f"MESH: {', '.join(record.get('MH', [])[:12])}" if record.get("MH") else "",
        ]
        text_value = "\n".join(part for part in text_parts if part).strip()

        return {
            "source": f"pubmed-{pmid}",
            "title": title,
            "text": text_value,
            "condition": title,
            "markers": markers,
            "subdomain": subdomain,
            "evidence_type": evidence_type,
            "publication_year": publication_year,
        }

    def _infer_evidence_type(self, record: dict) -> str:
        publication_types = [item.lower() for item in record.get("PT", [])]
        mapping = [
            ("randomized controlled trial", "rct"),
            ("clinical trial", "clinical-trial"),
            ("systematic review", "systematic-review"),
            ("meta-analysis", "meta-analysis"),
            ("practice guideline", "guideline"),
            ("guideline", "guideline"),
            ("review", "review"),
        ]
        for key, value in mapping:
            if any(key in item for item in publication_types):
                return value
        return "study"

    def _extract_markers(self, record: dict) -> list[str]:
        candidates = []
        for mesh in record.get("MH", [])[:20]:
            token = mesh.split("/")[0].strip()
            if token and len(token) <= 40:
                candidates.append(token)
        # Preserve order while deduping.
        unique = []
        seen = set()
        for item in candidates:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:8]

    def _extract_year(self, publication: str) -> int:
        for token in publication.split():
            if token.isdigit() and len(token) == 4:
                year = int(token)
                if 1900 <= year <= 2100:
                    return year
        return datetime.now(UTC).year

    def _load_state(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _save_state(self, path: Path, state: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=True, indent=2)
