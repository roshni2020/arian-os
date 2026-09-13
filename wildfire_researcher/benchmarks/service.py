"""Bounded provider refresh/import orchestration; catalog reads stay offline."""
from __future__ import annotations
import re
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote

_refresh_lock = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def classify_url(url):
    url = url.strip()
    if re.fullmatch(r"10\.\d{4,9}/[^\s]+", url):
        return "paper", url
    try:
        p = urlsplit(url)
        if p.scheme != "https" or p.username or p.password or p.port not in (None, 443) or p.query or p.fragment:
            raise ValueError()
    except ValueError:
        raise ValueError("use a public HTTPS provider URL without credentials, query or fragment") from None
    path = unquote(p.path).strip("/")
    if ".." in path or "\\" in path:
        raise ValueError("invalid provider URL path")
    if p.hostname == "huggingface.co" and re.fullmatch(r"datasets/[\w.-]+/[\w.-]+", path):
        return "huggingface", path.removeprefix("datasets/")
    if p.hostname in {"github.com", "www.github.com"} and re.fullmatch(r"[\w.-]+/[\w.-]+", path):
        return "github", path.removesuffix(".git")
    if p.hostname in {"openml.org", "www.openml.org"} and re.fullmatch(r"[dt]/\d+", path):
        return "openml", path
    if p.hostname in {"arxiv.org", "www.arxiv.org"} and re.fullmatch(r"(?:abs|pdf)/\d{4}\.\d{4,5}(?:v\d+)?(?:\.pdf)?", path):
        return "paper", "https://arxiv.org/abs/" + path.split("/", 1)[1].removesuffix(".pdf")
    if p.hostname == "doi.org" and re.fullmatch(r"10\.\d{4,9}/[^\s]+", path):
        return "paper", path
    raise ValueError("supported imports: Hugging Face dataset, OpenML /d/ or /t/, GitHub repository, arXiv paper, or DOI")


def provider_for(provider):
    if provider == "huggingface":
        from .providers import HuggingFaceProvider
        return HuggingFaceProvider()
    if provider == "openml":
        from .openml import OpenMLProvider
        return OpenMLProvider()
    if provider == "github":
        from .github import GitHubProvider
        return GitHubProvider()
    if provider == "paper":
        from .paper import PaperProvider
        return PaperProvider()
    raise ValueError("unsupported provider")


def sync_provider(st, provider, query="", limit=10):
    """Search a provider and return candidates. Nothing is written to the catalog except
    the curated WildfireIA pin and records the user already saved; a plain search must
    never fill the library with arbitrary datasets. Candidates carry saved=False and are
    persisted only through an explicit import."""
    from .providers import ProviderError
    from .storage import _decorate
    warnings = []
    with _refresh_lock:
        try:
            records = provider_for(provider).search(query, limit=limit)
            from .compatibility import wildfire_benchmark
            items = []
            for b in records:
                if provider == "huggingface" and b.get("dataset_identifier", "").lower() == "wildfireia/anonymous-wildfireia":
                    items.append(st.upsert(wildfire_benchmark()))
                    continue
                try:
                    items.append(st.get(b["id"]))  # already in the library: show the saved record
                except KeyError:
                    items.append({**_decorate(b), "saved": False})
        except (ProviderError, ImportError):
            items = st.list(q=query, source=provider, limit=limit)["items"]
            warnings.append("Provider refresh unavailable; showing saved metadata. Retry later.")
    return {"items": items, "warnings": warnings}


def import_url(st, url):
    from .providers import ProviderError
    provider, identity = classify_url(url)
    record = {"id": "import-" + uuid.uuid4().hex, "status": "fetching", "benchmark": None,
              "warnings": [], "created_at": now(), "provider": provider}
    with _refresh_lock:
        # Start the durable processing window only after this request owns the
        # provider slot. Each adapter finishes well inside the ten-minute lease.
        record["created_at"] = now()
        st.save_import(record)
        try:
            # Provider metadata is read live, but only the curated adapter supplies scientific pins.
            b = provider_for(provider).get_benchmark(identity)
            from .curated import enrich
            b = enrich(b)
            if (provider, identity.lower()) in {("huggingface", "wildfireia/anonymous-wildfireia"), ("github", "labrai/wildfireia")}:
                from .compatibility import wildfire_benchmark
                b = wildfire_benchmark()
            b = st.upsert(b)
            record["benchmark"] = b
            record["status"] = "complete" if b["readiness"]["status"] == "complete" else "partial"
            if record["status"] == "partial":
                record["warnings"].append("Some benchmark metadata is missing; review before creating a project.")
        except (ProviderError, ImportError):
            record["status"] = "failed"
            record["warnings"] = ["Provider unavailable or metadata could not be read. Saved catalog entries remain available."]
        except ValueError:
            record["status"] = "failed"
            record["warnings"] = ["Provider returned unsupported metadata; no project was created."]
        record = st.finish_import(record)
    return record
