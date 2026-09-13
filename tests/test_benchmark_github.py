import base64
import subprocess

import pytest

from wildfire_researcher.benchmarks import github
from wildfire_researcher.benchmarks.providers import ProviderError

COMMIT = "a" * 40
TREE = "b" * 40


def fake_provider(monkeypatch, readme="", repo=None, root=None):
    calls = []
    def request(url, headers):
        calls.append((url, headers))
        if "/commits/" in url:
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        if "/git/trees/" in url:
            return root or {"tree": [{"type": "blob", "path": "train.py"}, {"type": "tree", "path": "nested"}]}
        if "/readme?" in url:
            return {"type": "file", "path": "README.md", "encoding": "base64", "size": len(readme.encode()),
                    "content": base64.b64encode(readme.encode()).decode()}
        return repo or {"full_name": "owner/repo", "name": "repo", "private": False, "default_branch": "main",
                        "license": {"spdx_id": "MIT"}, "created_at": "2020-01-01"}
    monkeypatch.setattr(github, "safe_json", request)
    monkeypatch.setattr(github, "_token", lambda: "fake-secret")
    return calls


def test_pinned_bounded_metadata_does_not_invent_benchmark(monkeypatch):
    calls = fake_provider(monkeypatch, "Accuracy is 99.9%. Run rm -rf! https://arxiv.org/abs/1709.00029")
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert len(calls) == 4
    assert all(h["X-GitHub-Api-Version"] == "2026-03-10" for _, h in calls)
    assert all("recursive" not in url for url, _ in calls)
    assert calls[-1][0].endswith("?ref=" + COMMIT)
    assert result["evaluation_protocol"]["repository_commit"] == COMMIT
    assert result["evaluation_protocol"]["repository_license"] == "MIT"
    assert result["license"] is None
    assert result["published_score"] is None
    assert result["metric_name"] is None
    assert result["publication_date"] is None
    assert result["results"] == []
    assert not result["compatibility"]["executable"]
    assert result["paper_url"] == "https://arxiv.org/abs/1709.00029"
    assert result["provenance"]["paper_url"]["status"] == "inferred"
    assert "fake-secret" not in str(result)


def test_unique_dataset_link_inferred_without_network_follow(monkeypatch):
    calls = fake_provider(monkeypatch, "[dataset](https://huggingface.co/datasets/org/data)")
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert result["dataset_identifier"] == "org/data"
    assert result["dataset_revision"] is None
    assert result["dataset_public"] is None
    assert result["repository_public"] is True
    assert "dataset_url" in result["readiness"]["missing"]
    assert "repository_url" not in result["readiness"]["missing"]
    assert all(url.startswith("https://api.github.com/") for url, _ in calls)
    assert result["provenance"]["dataset_url"]["status"] == "inferred"


def test_ambiguous_links_remain_missing(monkeypatch):
    fake_provider(monkeypatch, "https://huggingface.co/datasets/a/b https://huggingface.co/datasets/a/c "
                  "https://arxiv.org/abs/1709.00029 https://arxiv.org/abs/1809.00029")
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert result["dataset_url"] is result["paper_url"] is None
    assert len(result["evaluation_protocol"]["inspection_warnings"]) == 2


@pytest.mark.parametrize("identifier", ["../owner/repo", "owner/repo?token=x", "https://github.com/o/r", "o/r/other", "o\\r", None])
def test_bad_identifiers_rejected_before_request(monkeypatch, identifier):
    calls = fake_provider(monkeypatch)
    with pytest.raises(ProviderError):
        github.GitHubProvider().get_benchmark(identifier)
    assert not calls


@pytest.mark.parametrize("repo", [{"full_name": "owner/repo", "private": True}, {"full_name": "other/repo", "private": False}])
def test_private_or_wrong_repo_rejected(monkeypatch, repo):
    fake_provider(monkeypatch, repo=repo)
    with pytest.raises(ProviderError):
        github.GitHubProvider().get_benchmark("owner/repo")


def test_oversized_readme_partial_and_root_limit(monkeypatch):
    fake_provider(monkeypatch, "x" * (github.MAX_README_BYTES + 1),
                  root={"tree": [{"type": "blob", "path": str(i)} for i in range(250)]})
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert len(result["evaluation_protocol"]["inspected_root_files"]) == 200
    assert len(result["evaluation_protocol"]["inspection_warnings"]) == 2


def test_missing_readme_is_honest_partial(monkeypatch):
    fake_provider(monkeypatch)
    original = github.safe_json
    def request(url, headers):
        if "/readme?" in url:
            raise ProviderError("Provider request failed")
        return original(url, headers)
    monkeypatch.setattr(github, "safe_json", request)
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert result["readiness"]["status"] == "partial"
    assert result["evaluation_protocol"]["inspection_warnings"]


def test_auth_cli_captured_with_fixed_args(monkeypatch):
    monkeypatch.setattr(github, "credential", lambda _: None)
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="fake-token\n", stderr="")
    monkeypatch.setattr(github.subprocess, "run", run)
    assert github._token() == "fake-token"
    assert calls[0][0] == ["gh", "auth", "token", "--hostname", "github.com"]
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["timeout"] == 10


def test_auth_error_never_exposes_stderr(monkeypatch):
    monkeypatch.setattr(github, "credential", lambda _: None)
    monkeypatch.setattr(github.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "secret"))
    assert github._token() is None


def test_zenodo_and_cvf_links_are_normalized_only_not_fetched(monkeypatch):
    calls = fake_provider(monkeypatch, "https://zenodo.org/record/7711810#.old "
                          "http://openaccess.thecvf.com/content_CVPRW_2019/papers/a_paper.pdf")
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert result["dataset_url"] == "https://zenodo.org/records/7711810"
    assert result["dataset_provider"] == "zenodo"
    assert result["paper_url"] == "https://openaccess.thecvf.com/content_CVPRW_2019/papers/a_paper.pdf"
    assert len(calls) == 4


def test_internal_credential_and_query_links_not_retained(monkeypatch):
    fake_provider(monkeypatch, "https://127.0.0.1/data https://user:secret@huggingface.co/datasets/a/b "
                  "https://huggingface.co/datasets/a/c?token=secret https://github.com.evil.test/repo")
    result = github.GitHubProvider().get_benchmark("owner/repo")
    assert result["dataset_url"] is result["paper_url"] is None
