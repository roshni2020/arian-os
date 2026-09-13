"""Bounded GitHub REST metadata imports, never repository execution.

API contract: https://docs.github.com/en/rest?apiVersion=2026-03-10
At most four JSON reads: repository, branch commit, root tree and pinned README.
README text is untrusted evidence: no free-text scores or instructions are used.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import re
import subprocess
from urllib.parse import quote, urlsplit

from .compatibility import compatibility, readiness
from .providers import FIELDS, ProviderError, credential, safe_json

API_VERSION = "2026-03-10"
MAX_README_BYTES = 128 * 1024
MAX_ROOT_ENTRIES = 200
SHA = re.compile(r"[0-9a-f]{40}")


def _identifier(value):
    if (not isinstance(value, str) or len(value) > 200 or ".." in value
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", value)):
        raise ProviderError("Invalid GitHub repository identifier")
    return value


def _text(value, limit=20000):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _token():
    token = credential("GH_TOKEN") or credential("GITHUB_TOKEN")
    if token:
        return token
    # Command and arguments are fixed. Never log stdout/stderr or exceptions.
    try:
        result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                capture_output=True, text=True, timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        value = result.stdout.strip() if result.returncode == 0 else None
        return value if value and len(value) <= 4096 and not any(c.isspace() for c in value) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _readme(raw):
    if (not isinstance(raw, dict) or raw.get("encoding") != "base64"
            or raw.get("type") != "file" or type(raw.get("size")) is not int
            or not 0 <= raw["size"] <= MAX_README_BYTES):
        raise ProviderError("README unavailable or exceeds inspection limit")
    content = raw.get("content")
    if not isinstance(content, str) or len(content) > MAX_README_BYTES * 2:
        raise ProviderError("README unavailable or exceeds inspection limit")
    try:
        decoded = base64.b64decode("".join(content.split()), validate=True)
        if len(decoded) > MAX_README_BYTES:
            raise ValueError()
        return decoded.decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error):
        raise ProviderError("README encoding is unsupported") from None


def _links(text):
    """Only recognizable structured provider links; never follow README URLs."""
    datasets, papers = set(), set()
    for candidate in re.findall(r"https?://[^\s<>\"'`]+", text):
        candidate = candidate.rstrip(").,;]")
        try:
            parsed = urlsplit(candidate)
            if parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.query:
                continue
        except ValueError:
            continue
        if parsed.hostname == "huggingface.co" and re.fullmatch(r"/datasets/[\w.-]+/[\w.-]+/?", parsed.path):
            datasets.add("https://huggingface.co" + parsed.path.rstrip("/"))
        if parsed.hostname == "zenodo.org" and re.fullmatch(r"/records?/\d+/?", parsed.path):
            datasets.add("https://zenodo.org/records/" + parsed.path.rstrip("/").rsplit("/", 1)[1])
        if parsed.hostname == "arxiv.org" and re.fullmatch(r"/(?:abs|pdf)/\d{4}\.\d{4,5}(?:v\d+)?(?:\.pdf)?", parsed.path):
            papers.add("https://arxiv.org/abs/" + parsed.path.rsplit("/", 1)[1].removesuffix(".pdf"))
        if parsed.hostname == "doi.org" and re.fullmatch(r"/10\.\d{4,9}/[^\s]+", parsed.path):
            papers.add("https://doi.org" + parsed.path)
        if parsed.hostname == "openaccess.thecvf.com" and re.fullmatch(r"/[A-Za-z0-9_/-]+_paper\.pdf", parsed.path):
            papers.add("https://openaccess.thecvf.com" + parsed.path)
    return datasets, papers


class GitHubProvider:
    name = "github"

    def get_benchmark(self, identifier: str) -> dict:
        identifier = _identifier(identifier)
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}
        token = _token()
        if token:
            headers["Authorization"] = "Bearer " + token
        api = "https://api.github.com/repos/" + quote(identifier, safe="/")
        raw = safe_json(api, headers)
        if not isinstance(raw, dict) or str(raw.get("full_name", "")).lower() != identifier.lower():
            raise ProviderError("Provider returned a different repository")
        if raw.get("private") is not False:
            raise ProviderError("Only public repositories may be imported")
        identifier = _identifier(raw["full_name"])
        repository_url = "https://github.com/" + identifier
        warnings = []
        commit_sha = tree_sha = None
        branch = raw.get("default_branch")
        if isinstance(branch, str) and 0 < len(branch) <= 200:
            try:
                commit = safe_json(api + "/commits/" + quote(branch, safe=""), headers)
                if not isinstance(commit, dict) or not SHA.fullmatch(str(commit.get("sha", ""))):
                    raise ProviderError("Invalid repository revision")
                commit_sha = commit["sha"]
                tree_sha = commit.get("commit", {}).get("tree", {}).get("sha")
                if not isinstance(tree_sha, str) or not SHA.fullmatch(tree_sha):
                    tree_sha = None
            except (ProviderError, AttributeError, TypeError):
                warnings.append("The repository commit could not be verified; source inspection is incomplete.")
        else:
            warnings.append("The repository has no inspectable default branch.")
        source_url = repository_url + ("/tree/" + commit_sha if commit_sha else "")
        root_files = []
        if tree_sha:
            try:
                tree = safe_json(api + "/git/trees/" + tree_sha, headers)
                if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
                    raise ProviderError("Invalid repository tree")
                if tree.get("truncated") or len(tree["tree"]) > MAX_ROOT_ENTRIES:
                    warnings.append("Root file inspection was limited; additional files were not inspected.")
                root_files = [entry["path"] for entry in tree["tree"][:MAX_ROOT_ENTRIES]
                              if isinstance(entry, dict) and entry.get("type") == "blob"
                              and isinstance(entry.get("path"), str) and len(entry["path"]) <= 200
                              and "/" not in entry["path"] and "\\" not in entry["path"]]
            except ProviderError:
                warnings.append("Root files could not be inspected.")
        readme_text = ""
        readme_source = source_url
        if commit_sha:
            try:
                readme_raw = safe_json(api + "/readme?ref=" + commit_sha, headers)
                readme_text = _readme(readme_raw)
                path = readme_raw.get("path")
                if isinstance(path, str) and len(path) <= 500:
                    readme_source = repository_url + "/blob/" + commit_sha + "/" + quote(path, safe="/")
            except ProviderError:
                warnings.append("README content is missing, unavailable, or exceeds the bounded inspection limit.")
        datasets, papers = _links(readme_text)
        if len(datasets) > 1:
            warnings.append("Multiple dataset links were found; no dataset was selected.")
        if len(papers) > 1:
            warnings.append("Multiple paper links were found; no paper was selected.")
        now = datetime.now(timezone.utc).isoformat()
        repository_license = raw.get("license")
        repository_license = _text(repository_license.get("spdx_id"), 100) if isinstance(repository_license, dict) else None
        if repository_license == "NOASSERTION":
            repository_license = None
        benchmark = dict.fromkeys(FIELDS)
        benchmark.update(
            id="github-" + hashlib.sha256(identifier.lower().encode()).hexdigest()[:24],
            slug=identifier.replace("/", "--"), title=_text(raw.get("name")) or identifier,
            description=_text(raw.get("description")), repository_url=repository_url,
            repository_public=True, dataset_public=None,
            dataset_url=next(iter(datasets)) if len(datasets) == 1 else None,
            paper_url=next(iter(papers)) if len(papers) == 1 else None,
            source="github", created_at=now, updated_at=now,
            # These are inspection facts, not a verified evaluation protocol.
            evaluation_protocol={"repository_commit": commit_sha, "repository_license": repository_license,
                                 "dataset_license": None, "inspected_root_files": root_files,
                                 "inspection_warnings": warnings},
        )
        if benchmark["dataset_url"]:
            if "/datasets/" in benchmark["dataset_url"]:
                benchmark["dataset_identifier"] = benchmark["dataset_url"].split("/datasets/", 1)[1]
                benchmark["dataset_provider"] = "huggingface"
            else:
                benchmark["dataset_identifier"] = benchmark["dataset_url"].rsplit("/", 1)[1]
                benchmark["dataset_provider"] = "zenodo"
        benchmark["provenance"] = {}
        inferred = {"dataset_url", "dataset_identifier", "dataset_provider", "paper_url"}
        for field, value in benchmark.items():
            if field in {"id", "slug", "created_at", "updated_at", "provenance"}:
                continue
            benchmark["provenance"][field] = {
                "value": value, "source_provider": "github" if value is not None else None,
                "source_url": (readme_source if field in inferred else api if field in {"title", "description"} else source_url) if value is not None else None,
                "status": "missing" if value is None else "inferred" if field in inferred else "verified",
                "confidence": None if value is None else "medium" if field in inferred else "high",
            }
        benchmark.update(
            sources=[{"provider": "github", "external_id": identifier,
                      "external_url": source_url, "last_synced_at": now}], results=[],
        )
        benchmark["readiness"] = readiness(benchmark)
        benchmark["compatibility"] = compatibility(benchmark)
        return benchmark
