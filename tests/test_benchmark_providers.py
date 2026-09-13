import socket
import time
from unittest.mock import Mock

import pytest

from wildfire_researcher.benchmarks import providers as p


@pytest.mark.parametrize("url", ["http://huggingface.co/api/datasets", "https://localhost/", "https://127.0.0.1/", "https://169.254.169.254/", "https://huggingface.co.evil.test/", "https://token@huggingface.co/", "https://huggingface.co:444/", "https://huggingface.co/#x", "https://huggingface.co/\nX:secret", "https://huggingface.co\\@evil.test/"])
def test_url_boundary(url):
    with pytest.raises(p.ProviderError):
        p.safe_json(url)


def test_private_dns_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(p.ProviderError, match="not public"):
        p.safe_json("https://huggingface.co/api/datasets")


def test_dns_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr(p, "REQUEST_TIMEOUT", 0.02)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: time.sleep(0.2))
    started = time.monotonic()
    with pytest.raises(p.ProviderError, match="timed out"):
        p.safe_json("https://huggingface.co/api/datasets")
    assert time.monotonic() - started < 0.15


def fake_http(monkeypatch, *, status=200, body=b"{}", headers=None):
    monkeypatch.setattr(p, "_public_addresses", lambda *a: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))])
    response = Mock(status=status)
    response.getheader.side_effect = lambda name, default=None: (headers or {}).get(name, default)
    chunks = [body, b""]
    response.read1.side_effect = lambda size: chunks.pop(0)
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(p.http.client, "HTTPSConnection", lambda *a, **k: connection)
    return connection


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 404, 500])
def test_redirects_and_errors_do_not_follow_or_leak(monkeypatch, status):
    connection = fake_http(monkeypatch, status=status, body=b"SECRET PROVIDER BODY")
    with pytest.raises(p.ProviderError, match="^Provider request failed$"):
        p.safe_json("https://huggingface.co/api/datasets", {"Authorization": "Bearer SECRET"})
    assert connection.request.call_count == 1
    connection.close.assert_called_once()


@pytest.mark.parametrize("headers,body", [({"Content-Length": str(p.MAX_RESPONSE_BYTES + 1)}, b"{}"), ({}, b"x" * (p.MAX_RESPONSE_BYTES + 1)), ({"Content-Encoding": "gzip"}, b"{}")], ids=["declared-oversize", "streamed-oversize", "encoded-response"])
def test_response_bounds(monkeypatch, headers, body):
    fake_http(monkeypatch, headers=headers, body=body)
    with pytest.raises(p.ProviderError):
        p.safe_json("https://huggingface.co/api/datasets")


def test_invalid_json_sanitized(monkeypatch):
    fake_http(monkeypatch, body=b"SECRET BAD JSON")
    with pytest.raises(p.ProviderError, match="^Provider response unavailable or invalid$"):
        p.safe_json("https://huggingface.co/api/datasets")


def test_nonfinite_json_rejected(monkeypatch):
    fake_http(monkeypatch, body=b'{"score": NaN}')
    with pytest.raises(p.ProviderError):
        p.safe_json("https://huggingface.co/api/datasets")


def test_missing_and_ambiguous_metadata_stays_missing():
    b = p.normalize_huggingface({"id": "owner/data", "createdAt": "2026-01-01", "cardData": {"license": ["mit", "apache-2.0"], "size_categories": ["1K<n<10K"], "task_categories": ["a", "b"]}})
    for field in ["publication_date", "sample_count", "metric_name", "published_score", "license", "task_type"]:
        assert b[field] is None
        assert b["provenance"][field]["status"] == "missing"
    assert not b["compatibility"]["executable"]


def test_exact_revision_provenance_and_split_counts():
    sha = "a" * 40
    b = p.normalize_huggingface({"id": "owner/data", "sha": sha, "cardData": {"task_categories": ["image-classification"], "license": "mit", "dataset_info": {"splits": [{"name": "train", "num_examples": 8}, {"name": "test", "num_examples": 2}]}}})
    assert b["dataset_revision"] == sha
    assert b["sample_count"] == 10
    assert b["provenance"]["sample_count"]["status"] == "inferred"
    assert b["provenance"]["license"]["source_url"].endswith(sha)
    assert b["train_split"] == "train"
    assert "official_split" in b["readiness"]["missing"]


def test_search_is_bounded_and_private_filtered(monkeypatch):
    captured = []
    def fetch(url, headers):
        captured.append(url)
        return [{"id": "owner/private", "private": True}, {"id": "owner/public"}]
    monkeypatch.setattr(p, "safe_json", fetch)
    monkeypatch.setattr(p, "credential", lambda name: None)
    result = p.HuggingFaceProvider().search(" wildfire ", 2)
    assert len(result) == 1
    assert "search=wildfire&limit=2" in captured[0]
    with pytest.raises(p.ProviderError):
        p.HuggingFaceProvider().search("", 101)


@pytest.mark.parametrize("identifier", ["../secret", "a/b/c", "a?token=x", "a#x", "https://huggingface.co/foo", "a/%2e%2e", None])
def test_identifier_validation(identifier):
    with pytest.raises(p.ProviderError):
        p.HuggingFaceProvider().get_benchmark(identifier)


def test_different_dataset_rejected(monkeypatch):
    monkeypatch.setattr(p, "safe_json", lambda *a: {"id": "other/data"})
    monkeypatch.setattr(p, "credential", lambda name: None)
    with pytest.raises(p.ProviderError, match="different dataset"):
        p.HuggingFaceProvider().get_benchmark("owner/data")


def test_credential_allowlist(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "  example  ")
    assert p.credential("HF_TOKEN") == "example"
    assert p.credential("PATH") is None


@pytest.mark.parametrize("access,expected", [({}, None), ({"private": False}, True), ({"private": False, "gated": False}, True), ({"private": False, "gated": "manual"}, False), ({"gated": "auto"}, False), ({"gated": True}, False), ({"private": False, "gated": "unknown"}, None), ({"private": 0}, None)])
def test_dataset_public_requires_explicit_access_metadata(access, expected):
    b = p.normalize_huggingface({"id": "owner/data", **access})
    assert b["dataset_public"] is expected
    assert b["repository_public"] is None
    assert b["provenance"]["dataset_public"]["value"] is expected
    assert b["provenance"]["dataset_public"]["status"] == ("missing" if expected is None else "verified")
    assert ("dataset_url" not in b["readiness"]["missing"]) is (expected is True)
    assert b["provenance"]["repository_public"]["status"] == "missing"
