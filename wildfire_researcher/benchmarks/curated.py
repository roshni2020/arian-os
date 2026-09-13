"""Small source-reviewed library; unsupported and incomplete examples remain partial.

Evidence independently audited in artifacts/benchmark_verification/source_evidence.md.
Refresh requires live provider reads. This module never loads a dataset or repository code.
"""
from copy import deepcopy
from .compatibility import wildfire_benchmark


def field(b, name, value, provider, url, status="verified"):
    b[name] = deepcopy(value)
    b.setdefault("provenance", {})[name] = {"value": deepcopy(value), "source_provider": provider,
        "source_url": url, "status": status, "confidence": "high" if status == "verified" else "medium"}


def enrich(b):
    sources = {(s["provider"], s["external_id"].lower()) for s in b.get("sources", [])}
    repo = (b.get("repository_url") or "").lower().removesuffix("/")
    if repo == "https://github.com/diux-xview/xview2_baseline":
        paper = "https://arxiv.org/abs/1911.09296v1"
        field(b, "title", "xBD / xView2 disaster damage", "paper", paper)
        field(b, "description", "Assess building damage from paired satellite imagery before and after disasters.", "paper", paper)
        field(b, "paper_url", paper, "paper", paper)
        field(b, "domain", "Disaster Response", "curated", paper, "inferred")
        field(b, "task_type", "building localization and damage classification", "paper", paper)
        field(b, "dataset_url", "https://xview2.org/dataset", "paper", paper)
        field(b, "dataset_identifier", "xBD", "paper", paper)
        # Building annotations are not an image count; unmatched F1 scores stay absent.
        field(b, "leakage_notes", "Dataset access requires registration according to the official README; anonymous access and license are not verified. Geographic/event separation requires review. Paper describes 80/10/10 train/test/holdout, with validation carved from training. Exact frozen revision and seeds remain unverified. The paper weighted-F1 result is not established as the challenge composite.", "curated", paper, "inferred")
    elif repo == "https://github.com/phelber/eurosat":
        paper = "https://arxiv.org/abs/1709.00029v2"
        field(b, "title", "EuroSAT land-use classification", "paper", paper)
        field(b, "description", "Classify Sentinel-2 satellite images into ten land-use and land-cover categories.", "paper", paper)
        field(b, "paper_url", paper, "paper", paper)
        field(b, "domain", "Remote Sensing", "curated", paper, "inferred")
        field(b, "task_type", "multiclass classification", "paper", paper)
        field(b, "dataset_url", "https://zenodo.org/record/7711810", "github", b["repository_url"])
        field(b, "dataset_identifier", "EuroSAT", "paper", paper)
        field(b, "sample_count", 27000, "paper", paper)
        field(b, "train_split", "class-wise 80% training (recipe; frozen indices unavailable)", "paper", paper)
        field(b, "test_split", "class-wise 20% test (recipe; frozen indices unavailable)", "paper", paper)
        field(b, "metric_name", "overall accuracy", "paper", paper)
        field(b, "metric_direction", "maximize", "paper", paper)
        field(b, "leakage_notes", "Exact seeds, frozen split indices, independent validation split and dataset revision tied to the paper result are unverified. RGB pretrained result is not interchangeable with multispectral or from-scratch results.", "curated", paper, "inferred")
        # Explicit result context; the user must choose a target in the review.
        results = [{"id": "eurosat-rgb-pretrained-resnet50", "model": "ResNet-50, ILSVRC-2012 pretrained, RGB (Table III)",
            "metric_name": "overall accuracy", "metric_direction": "maximize", "metric_definition": "Correct predictions / examples; source reports 98.57 percent, stored as fraction",
            "score": 0.9857, "dataset_identifier": "EuroSAT", "dataset_revision": None,
            "split": "class-wise 80/20 train/test; exact indices/seeds unavailable", "source_url": paper}]
        field(b, "results", results, "paper", paper)
    elif any(provider == "openml" and external in {"t/15", "task/15", "15"} for provider, external in sources) or b.get("openml_task_id") == 15:
        url = "https://www.openml.org/t/15"
        field(b, "domain", "Healthcare", "curated", url, "inferred")
        field(b, "description", "Wisconsin original breast-cancer classification task. Published target score and task metric have not been established.", "curated", url, "inferred")
    elif any(provider == "openml" and external in {"t/59", "task/59"} for provider, external in sources) or b.get("openml_task_id") == 59:
        field(b, "domain", "Tabular", "curated", "https://www.openml.org/t/59", "inferred")
    return b


def seed_library(st):
    from .providers import HuggingFaceProvider, ProviderError
    from .openml import OpenMLProvider
    from .github import GitHubProvider
    providers = [(HuggingFaceProvider(), "WildfireIA/Anonymous-WildfireIA"),
                 (OpenMLProvider(), "t/15"), (GitHubProvider(), "DIUx-xView/xView2_baseline"),
                 (GitHubProvider(), "phelber/EuroSAT"), (OpenMLProvider(), "t/59")]
    items, warnings = [], []
    for adapter, identity in providers:
        try:
            b = adapter.get_benchmark(identity)
            b = wildfire_benchmark() if identity == "WildfireIA/Anonymous-WildfireIA" else enrich(b)
            items.append(st.upsert(b))
        except ProviderError:
            warnings.append(f"Could not refresh curated source {identity}; previous snapshot preserved.")
    return {"items": items, "warnings": warnings}
