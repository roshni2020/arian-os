"""Structured paper metadata only; no PDF fetching, crawling or score guessing.

Provider documentation:
https://www.crossref.org/documentation/retrieve-metadata/rest-api/
https://info.arxiv.org/help/api/user-manual.html
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import math
import re
import threading
import time
from urllib.parse import quote, urlencode, urlsplit
import xml.etree.ElementTree as ET

from . import providers
from .compatibility import compatibility, readiness


ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = re.compile(r"\d{4}\.\d{4,5}(?:v[1-9]\d*)?")
DOI = re.compile(r"10\.\d{4,9}/[^\s\x00-\x20<>\"\\]+", re.IGNORECASE)
_arxiv_lock = threading.Lock()
_arxiv_last_request = 0.0


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(value):
    if not isinstance(value, str):
        return None
    parser = _PlainText()
    parser.feed(value[:50000])
    return " ".join(" ".join(parser.parts).split())[:20000] or None


def _public_link(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value) or "\\" in value:
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password or url.port not in {None, 80, 443}:
            return None
    except ValueError:
        return None
    return value


def extract_results(raw, source_url):
    """Accept explicit structured result objects, never numbers from prose.

    Crossref/Atom normally supply no leaderboard. This optional normalized
    extension preserves every result when a structured source does provide it.
    It deliberately does not promote any result into the benchmark target.
    """
    results = []
    rows = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return results
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        score = row.get("score")
        metric = _text(row.get("metric_name"))
        if type(score) not in {int, float} or not math.isfinite(score) or not metric:
            continue
        result = {key: _text(row.get(key)) for key in (
            "model", "metric_name", "metric_direction", "metric_definition",
            "dataset_identifier", "dataset_revision", "split")}
        if result["metric_direction"] not in {"maximize", "minimize"}:
            result["metric_direction"] = None
        result.update(score=score, source_url=_public_link(row.get("source_url")) or source_url)
        import json
        result["id"] = _text(row.get("id")) or "result-" + hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:20]
        if not any(r["id"] == result["id"] for r in results):
            results.append(result)
    return results


def _record(provider, identifier, title, abstract, publication_date, links, raw=None):
    now = datetime.now(timezone.utc).isoformat()
    url = "https://arxiv.org/abs/" + identifier if provider == "arxiv" else "https://doi.org/" + quote(identifier, safe="/():;@-._~")
    record = dict.fromkeys(providers.FIELDS)
    record.update(id="paper-" + hashlib.sha256((provider + ":" + identifier.lower()).encode()).hexdigest()[:24],
                  slug=provider + "-" + re.sub(r"[^a-z0-9]+", "-", identifier.lower()).strip("-"),
                  title=title or identifier, description=abstract, publication_date=publication_date,
                  paper_url=url, source=provider, created_at=now, updated_at=now)
    repositories, datasets = [], []
    for link in links:
        link = _public_link(link)
        if not link:
            continue
        parsed = urlsplit(link)
        parts = [p for p in parsed.path.split("/") if p]
        if parsed.hostname == "github.com" and len(parts) == 2:
            repositories.append(link)
        if parsed.hostname == "huggingface.co" and len(parts) == 3 and parts[0] == "datasets":
            datasets.append((link, "/".join(parts[1:])))
    if len(set(repositories)) == 1:
        record["repository_url"] = repositories[0]
    if len(set(datasets)) == 1:
        record.update(dataset_url=datasets[0][0], dataset_identifier=datasets[0][1], dataset_provider="huggingface")
    record["results"] = extract_results(raw, url)
    record["sources"] = [{"provider": provider, "external_id": identifier, "external_url": url, "last_synced_at": now}]
    record["provenance"] = {
        field: {"value": value, "source_provider": provider if value is not None else None,
                "source_url": url if value is not None else None, "status": "verified" if value is not None else "missing",
                "confidence": "high" if value is not None else None}
        for field, value in record.items() if field not in {"id", "slug", "created_at", "updated_at", "sources"}
    }
    if title is None:
        record["provenance"]["title"].update(status="inferred", confidence="low")
    for field in ("dataset_identifier", "dataset_provider"):
        if record[field] is not None:
            record["provenance"][field].update(status="inferred", confidence="medium")
    record["readiness"] = readiness(record)
    record["compatibility"] = compatibility(record)
    return record


def normalize_crossref(raw, doi):
    if not isinstance(raw, dict) or not isinstance(raw.get("message"), dict):
        raise providers.ProviderError("Invalid Crossref metadata")
    work = raw["message"]
    if str(work.get("DOI", "")).lower() != doi.lower():
        raise providers.ProviderError("Provider returned a different paper")
    title = work.get("title")
    title = _text(title[0]) if isinstance(title, list) and title else None
    date = None
    # Deposited/indexed dates are not publication dates. Partial precision is
    # retained; a year-only date never becomes an invented January 1.
    for name in ("published", "published-online", "published-print"):
        parts = work.get(name, {}).get("date-parts") if isinstance(work.get(name), dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            p = parts[0]
            if 1 <= len(p) <= 3 and all(type(n) is int for n in p) and 1000 <= p[0] <= 9999:
                try:
                    datetime(p[0], p[1] if len(p) > 1 else 1, p[2] if len(p) > 2 else 1)
                    date = "-".join([str(p[0])] + [f"{n:02}" for n in p[1:]])
                    break
                except ValueError:
                    pass
    links = [entry.get("URL") for entry in work.get("link", []) if isinstance(entry, dict)] if isinstance(work.get("link"), list) else []
    return _record("crossref", doi.lower(), title, _text(work.get("abstract")), date, links, work)


def normalize_arxiv(text, identifier):
    if not isinstance(text, str) or len(text.encode("utf-8")) > providers.MAX_RESPONSE_BYTES or re.search(r"<!\s*(?:DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise providers.ProviderError("Invalid arXiv metadata")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, ValueError):
        raise providers.ProviderError("Invalid arXiv metadata") from None
    entries = root.findall(ATOM + "entry")
    if len(entries) != 1:
        raise providers.ProviderError("Paper was not found")
    entry = entries[0]
    actual = (entry.findtext(ATOM + "id") or "").rstrip("/").rsplit("/", 1)[-1]
    if not ARXIV.fullmatch(actual) or (actual != identifier if "v" in identifier else actual.split("v")[0] != identifier):
        raise providers.ProviderError("Provider returned a different paper")
    publication_date = entry.findtext(ATOM + "published")
    try:
        publication_date = datetime.fromisoformat(publication_date.replace("Z", "+00:00")).date().isoformat()
    except (AttributeError, ValueError):
        publication_date = None
    links = [link.get("href") for link in entry.findall(ATOM + "link")]
    return _record("arxiv", identifier, _text(entry.findtext(ATOM + "title")), _text(entry.findtext(ATOM + "summary")), publication_date, links)


class PaperProvider:
    name = "paper"

    def get_benchmark(self, value):
        global _arxiv_last_request
        if not isinstance(value, str) or len(value) > 2048:
            raise providers.ProviderError("Unsupported paper identifier")
        value = value.strip()
        if DOI.fullmatch(value):
            return normalize_crossref(providers.safe_json("https://api.crossref.org/works/" + quote(value, safe="")), value)
        try:
            parsed = urlsplit(value)
            match = re.fullmatch(r"/abs/(\d{4}\.\d{4,5}(?:v[1-9]\d*)?)", parsed.path)
            if parsed.scheme != "https" or parsed.hostname != "arxiv.org" or parsed.username or parsed.password or parsed.port not in {None, 443} or parsed.query or parsed.fragment or not match:
                raise ValueError()
        except ValueError:
            raise providers.ProviderError("Use an arXiv abstract URL or a DOI identifier") from None
        identifier = match.group(1)
        # arXiv requests at least three seconds between sequential API calls.
        with _arxiv_lock:
            pause = 3.0 - (time.monotonic() - _arxiv_last_request)
            if pause > 0:
                time.sleep(pause)
            try:
                text = providers.safe_text("https://export.arxiv.org/api/query?" + urlencode({"id_list": identifier, "max_results": 1}), {"Accept": "application/atom+xml"})
            finally:
                _arxiv_last_request = time.monotonic()
        return normalize_arxiv(text, identifier)
