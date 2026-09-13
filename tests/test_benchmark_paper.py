import pytest

from wildfire_researcher.benchmarks.paper import PaperProvider, normalize_arxiv, normalize_crossref
from wildfire_researcher.benchmarks.providers import ProviderError
from wildfire_researcher.benchmarks.storage import BenchmarkStore


DOI = "10.1234/example"


def test_crossref_missing_score_and_partial_date():
    b = normalize_crossref({"message": {"DOI": DOI, "title": ["Example"], "abstract": "<jats:p>Accuracy is 95%.</jats:p>", "published": {"date-parts": [[2020]]}}}, DOI)
    assert b["description"] == "Accuracy is 95%."
    assert b["publication_date"] == "2020"
    assert b["published_score"] is None
    assert b["metric_name"] is None
    assert b["results"] == []
    assert b["readiness"]["status"] == "partial"
    assert b["provenance"]["published_score"]["status"] == "missing"
    assert not b["compatibility"]["executable"]


def test_all_structured_results_retained_and_explicit_selection(tmp_path):
    b = normalize_crossref({"message": {"DOI": DOI, "title": ["Models"], "results": [
        {"model": "A", "metric_name": "AUPRC", "score": .5, "dataset_revision": "rev-a", "split": "test"},
        {"model": "B", "metric_name": "AUPRC", "score": .7, "dataset_revision": "rev-b", "split": "validation"},
        {"model": "bad", "metric_name": "AUPRC", "score": True}]}}, DOI)
    assert len(b["results"]) == 2
    assert b["published_score"] is None
    assert b["results"][0]["dataset_revision"] == "rev-a"
    store = BenchmarkStore(tmp_path / "papers.sqlite")
    b = store.upsert(b)
    with pytest.raises(ValueError, match="explicit"):
        store.create_project(b, "Review", 1)
    p = store.create_project(b, "Review", 1, selected_result_id=b["results"][0]["id"])
    assert p["snapshot"]["published_score"] == .5
    assert not p["compatibility"]["executable"]


def test_arxiv_metadata_no_abstract_score_guessing():
    atom = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1709.00029v1</id><title>EuroSAT</title><summary>Accuracy 98.5 percent.</summary><published>2017-08-31T00:00:00Z</published><link href="https://github.com/phelber/EuroSAT"/></entry></feed>'''
    b = normalize_arxiv(atom, "1709.00029")
    assert b["title"] == "EuroSAT"
    assert b["repository_url"] == "https://github.com/phelber/EuroSAT"
    assert b["publication_date"] == "2017-08-31"
    assert b["published_score"] is None
    with pytest.raises(ProviderError, match="different"):
        normalize_arxiv(atom, "1709.00030")


@pytest.mark.parametrize("url", ["https://localhost/paper", "https://arxiv.org.evil/abs/1709.00029", "https://arxiv.org@evil/abs/1709.00029", "https://arxiv.org/pdf/1709.00029", "http://arxiv.org/abs/1709.00029", "https://arxiv.org/abs/1709.00029?redirect=evil"])
def test_reject_unsupported_paper_urls(url):
    with pytest.raises(ProviderError):
        PaperProvider().get_benchmark(url)


@pytest.mark.parametrize("xml", ["<!DOCTYPE x [<!ENTITY secret SYSTEM 'file:///etc/passwd'>]><feed/>", "not XML", "<feed/>"])
def test_reject_xml_entities_and_invalid_metadata(xml):
    with pytest.raises(ProviderError):
        normalize_arxiv(xml, "1709.00029")


def test_crossref_network_uses_fixed_host(monkeypatch):
    observed = []
    def fetch(url):
        observed.append(url)
        return {"message": {"DOI": DOI, "title": ["Example"]}}
    monkeypatch.setattr("wildfire_researcher.benchmarks.providers.safe_json", fetch)
    PaperProvider().get_benchmark(DOI)
    assert observed == ["https://api.crossref.org/works/10.1234%2Fexample"]
