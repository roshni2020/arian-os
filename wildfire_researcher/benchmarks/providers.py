"""Read-only structured provider adapters. Never downloads or executes datasets.

References: https://huggingface.co/docs/hub/api and
https://huggingface.co/docs/huggingface_hub/package_reference/hf_api
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import queue
import re
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlsplit

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 15.0
ALLOWED_HOSTS = frozenset({"huggingface.co", "www.openml.org", "api.openml.org", "api.github.com", "api.crossref.org", "export.arxiv.org"})


class ProviderError(ValueError):
    """Safe message only: upstream bodies, URLs and credentials are not included."""


def credential(name: str) -> str | None:
    if name not in {"HF_TOKEN", "OPENML_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"}:
        return None
    value = os.environ.get(name)
    if not value and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = winreg.QueryValueEx(key, name)[0]
        except OSError:
            pass
    return value.strip() if isinstance(value, str) and value.strip() else None


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderError("Provider request timed out")
    return remaining


def _public_addresses(host: str, deadline: float) -> list:
    # Bound DNS as well as network I/O; DNS workers are daemon threads.
    result = queue.Queue(maxsize=1)
    def resolve():
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except Exception:
            result.put(None)
    threading.Thread(target=resolve, daemon=True).start()
    try:
        addresses = result.get(timeout=_remaining(deadline))
    except queue.Empty:
        raise ProviderError("Provider request timed out") from None
    if not addresses:
        raise ProviderError("Provider is unavailable")
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ProviderError("Provider address is not public")
    return addresses


def safe_bytes(url: str, headers: dict | None = None):
    """GET allowlisted HTTPS JSON with pinned public DNS, no proxies/redirects.

    A single 15-second deadline bounds DNS, connect, TLS, headers and body.
    Only identity encoding is accepted, so compressed bombs cannot bypass 2MB.
    """
    connection = None
    response = None
    watchdog = None
    try:
        if not isinstance(url, str) or any(ord(c) < 33 for c in url) or "\\" in url:
            raise ProviderError("Invalid provider URL")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment):
            raise ProviderError("Unsupported provider URL")
        deadline = time.monotonic() + REQUEST_TIMEOUT
        addresses = _public_addresses(parsed.hostname, deadline)
        # Keep original host for TLS certificate/SNI while connecting to the
        # validated numeric address directly, avoiding a second DNS lookup.
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=_remaining(deadline), context=ssl.create_default_context())
        def connect_public(*args, **kwargs):
            for family, socktype, proto, _, address in addresses:
                sock = socket.socket(family, socktype, proto)
                try:
                    sock.settimeout(_remaining(deadline))
                    sock.connect(address)
                    sock.settimeout(_remaining(deadline))
                    return sock
                except OSError:
                    sock.close()
            raise ProviderError("Provider is unavailable")
        connection._create_connection = connect_public
        def abort_at_deadline():
            # A peer sending one byte per socket timeout must not keep header
            # parsing or read1 alive beyond the total request deadline.
            active_socket = connection.sock
            if active_socket is None and response is not None:
                active_socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            if active_socket is not None:
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                active_socket.close()
        watchdog = threading.Timer(_remaining(deadline), abort_at_deadline)
        watchdog.daemon = True
        watchdog.start()
        request_headers = {"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "Focus-Benchmark-Importer/1.0"}
        for key, value in (headers or {}).items():
            if key.lower() not in {"authorization", "x-api-key", "accept", "x-github-api-version"}:
                raise ProviderError("Unsupported provider request header")
            if not isinstance(value, str) or "\r" in value or "\n" in value:
                raise ProviderError("Invalid provider request header")
            request_headers[key] = value
        connection.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""), headers=request_headers)
        connection.sock.settimeout(_remaining(deadline))
        response = connection.getresponse()
        if response.status != 200:
            if response.status == 429:
                raise ProviderError("Provider rate limit reached; retry later")
            raise ProviderError("Provider request failed")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise ProviderError("Unsupported provider response encoding")
        length = response.getheader("Content-Length")
        if length and int(length) > MAX_RESPONSE_BYTES:
            raise ProviderError("Provider response exceeds size limit")
        data = bytearray()
        while True:
            if connection.sock is not None:
                connection.sock.settimeout(_remaining(deadline))
            else:
                _remaining(deadline)
            chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ProviderError("Provider response exceeds size limit")
        _remaining(deadline)
        return bytes(data)
    except ProviderError:
        raise
    except (TimeoutError, socket.timeout):
        raise ProviderError("Provider request timed out") from None
    except Exception:
        raise ProviderError("Provider response unavailable or invalid") from None
    finally:
        if watchdog:
            watchdog.cancel()
        if response:
            response.close()
        if connection:
            connection.close()


def safe_text(url: str, headers: dict | None = None) -> str:
    try:
        return safe_bytes(url, headers).decode("utf-8")
    except UnicodeError:
        raise ProviderError("Provider response unavailable or invalid") from None


def safe_json(url: str, headers: dict | None = None):
    def reject_nonfinite(value):
        raise ValueError("Non-finite JSON number")
    try:
        return json.loads(safe_text(url, headers), parse_constant=reject_nonfinite)
    except ProviderError:
        raise
    except (ValueError, RecursionError):
        raise ProviderError("Provider response unavailable or invalid") from None


FIELDS = ("id slug title description domain task_type publication_date paper_url repository_url dataset_url dataset_provider dataset_identifier dataset_revision metric_name metric_direction published_score published_model sample_count license train_split validation_split test_split evaluation_protocol leakage_notes source created_at updated_at").split()


def _text(value):
    return value.strip()[:20000] if isinstance(value, str) and value.strip() else None


def _single(value):
    return _text(value[0]) if isinstance(value, list) and len(value) == 1 else _text(value)


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?", value) or len(value) > 200 or ".." in value:
        raise ProviderError("Invalid Hugging Face dataset identifier")
    return value


def normalize_huggingface(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ProviderError("Invalid Hugging Face dataset metadata")
    identifier = _identifier(raw.get("id") or raw.get("_id"))
    if raw.get("private") is True:
        raise ProviderError("Only public datasets may be imported")
    sha = raw.get("sha")
    sha = sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None
    url = "https://huggingface.co/datasets/" + quote(identifier, safe="/")
    source_url = url + ("/tree/" + sha if sha else "")
    card = raw.get("cardData") if isinstance(raw.get("cardData"), dict) else {}
    now = datetime.now(timezone.utc).isoformat()
    benchmark = dict.fromkeys(FIELDS)
    gated = raw.get("gated")
    if gated is True or (isinstance(gated, str) and gated in {"auto", "manual"}):
        dataset_public = False
    elif raw.get("private") is False and (gated is False or gated is None):
        dataset_public = True
    else:
        dataset_public = None
    benchmark.update(id="hf-" + hashlib.sha256(identifier.lower().encode()).hexdigest()[:24], slug=identifier.replace("/", "--"),
                     title=_text(card.get("pretty_name")) or identifier, description=_text(raw.get("description")),
                     dataset_provider="huggingface", dataset_identifier=identifier, dataset_url=url,
                     dataset_public=dataset_public, repository_public=None,
                     dataset_revision=sha, task_type=_single(card.get("task_categories")),
                     license=_single(card.get("license")), source="huggingface", created_at=now, updated_at=now)
    # Repository creation is not paper publication. Categories/size ranges are
    # not exact row counts. Multiple configurations must not be summed.
    info = card.get("dataset_info")
    if isinstance(info, list) and len(info) == 1:
        info = info[0]
    if isinstance(info, dict) and isinstance(info.get("splits"), list):
        splits = info["splits"]
        counts = [s.get("num_examples") for s in splits if isinstance(s, dict)]
        if len(counts) == len(splits) and counts and all(type(n) is int and n >= 0 for n in counts):
            benchmark["sample_count"] = sum(counts)
        for split in splits:
            if isinstance(split, dict) and split.get("name") in {"train", "validation", "test"}:
                benchmark[split["name"] + "_split"] = split["name"]
    benchmark["provenance"] = {
        field: {"value": value, "source_provider": "huggingface" if value is not None else None,
                "source_url": source_url if value is not None else None,
                "status": "verified" if value is not None else "missing",
                "confidence": "high" if value is not None else None}
        for field, value in benchmark.items() if field not in {"id", "slug", "created_at", "updated_at"}
    }
    if benchmark["sample_count"] is not None:
        benchmark["provenance"]["sample_count"].update(status="inferred", confidence="medium")
    if dataset_public is not None:
        # Access state belongs to live repository metadata, not a pinned card.
        benchmark["provenance"]["dataset_public"]["source_url"] = "https://huggingface.co/api/datasets/" + quote(identifier, safe="/")
    checks = {"dataset_url": benchmark["dataset_public"] is True,
              "metric_name": False, "published_score": False, "official_split": False,
              "repository_url": False, "evaluation_script": False}
    missing = [name for name, present in checks.items() if not present]
    benchmark.update(sources=[{"provider": "huggingface", "external_id": identifier, "external_url": source_url, "last_synced_at": now}],
                     results=[], readiness={"status": "partial", "score": 6 - len(missing), "total": 6, "missing": missing},
                     compatibility={"executable": False, "executor": None, "reasons": ["No supported executor has been verified for this imported dataset."], "comparability": "Dataset metadata alone does not establish a comparable evaluation protocol."})
    return benchmark


class HuggingFaceProvider:
    name = "huggingface"

    def _headers(self):
        token = credential("HF_TOKEN")
        return {"Authorization": "Bearer " + token} if token else {}

    def search(self, query: str = "", limit: int = 10) -> list[dict]:
        if not isinstance(query, str) or len(query) > 200 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProviderError("Invalid provider search parameters")
        params = urlencode({"search": query.strip(), "limit": limit, "full": "true"})
        raw = safe_json("https://huggingface.co/api/datasets?" + params, self._headers())
        if not isinstance(raw, list):
            raise ProviderError("Invalid Hugging Face search response")
        return [normalize_huggingface(item) for item in raw[:limit] if isinstance(item, dict) and item.get("private") is not True]

    def get_benchmark(self, identifier: str) -> dict:
        identifier = _identifier(identifier)
        raw = safe_json("https://huggingface.co/api/datasets/" + quote(identifier, safe="/"), self._headers())
        result = normalize_huggingface(raw)
        if result["dataset_identifier"].lower() != identifier.lower():
            raise ProviderError("Provider returned a different dataset")
        return result
