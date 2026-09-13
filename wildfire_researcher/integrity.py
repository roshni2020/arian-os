"""Fail-closed source/data/cache verification. Never infer provenance from a label."""
import hashlib
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from . import config, protocol


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require_clean_code():
    if protocol.repo_commit() != protocol.PINNED_COMMIT:
        raise ValueError('Unknown or unpinned WildfireIA revision')
    result = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'],
                            cwd=config.WILDFIREIA_DIR, capture_output=True, text=True, check=True)
    if result.stdout.strip():
        raise ValueError('WildfireIA tracked source has local modifications')


def verify_dataset():
    """Compare local required files with upstream git/LFS hashes at the pinned revision."""
    from .cli import CANONICAL_FILES
    url = f'https://huggingface.co/api/datasets/{protocol.DATASET_REPO}/tree/{protocol.DATASET_REVISION}/data/canonical/raw_feature_tables'
    with urllib.request.urlopen(url, timeout=60) as response:
        entries = json.load(response)
    remote = {Path(x['path']).name: x for x in entries if x['type'] == 'file'}
    files = {}
    for name in CANONICAL_FILES:
        item = remote[name]
        path = config.CANONICAL_DIR / name
        if 'lfs' in item:
            actual = digest(path)
            expected = item['lfs']['oid']
        else:
            data = path.read_bytes()
            actual = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
            expected = item['oid']
        if actual != expected:
            raise ValueError(f'Dataset hash mismatch: {name}')
        files[name] = digest(path)
    result = {'dataset_revision': protocol.DATASET_REVISION, 'files': files}
    from .tracking import write_json
    write_json(config.DATA_DIR / 'verified_dataset.json', result)
    return result


def dataset_manifest():
    path = config.DATA_DIR / 'verified_dataset.json'
    if not path.exists():
        raise ValueError('Run python -m wildfire_researcher.cli verify-data before official evaluation')
    manifest = json.loads(path.read_text())
    from .cli import CANONICAL_FILES
    if manifest.get('dataset_revision') != protocol.DATASET_REVISION or set(manifest['files']) != set(CANONICAL_FILES):
        raise ValueError('Incomplete or wrong dataset verification manifest')
    for name, expected in manifest['files'].items():
        if digest(config.CANONICAL_DIR/name) != expected:
            raise ValueError(f'Canonical file changed: {name}')
    return manifest


def verified_cache(feature_protocol, weather_days):
    """Rebuild independently before first attestation; later verify every file hash."""
    import numpy as np
    import pandas as pd
    require_clean_code()
    source = dataset_manifest()
    cache = protocol.ensure_tabular_cache(feature_protocol, weather_days)
    fingerprint = {'code':protocol.PINNED_COMMIT,'source':source,'feature_protocol':feature_protocol,'weather_days':weather_days}
    marker = cache/'verified_cache.json'
    if marker.exists():
        record = json.loads(marker.read_text())
        if record.get('input') != fingerprint:
            raise ValueError('Cache input provenance changed; rebuild and reverify explicitly')
        for name, expected in record['files'].items():
            if digest(cache/name) != expected:
                raise ValueError(f'Cache changed: {name}')
        return record
    dl = protocol.official().dataloader
    paths = dl.canonical_paths(config.CANONICAL_DIR)
    manifest = dl.load_json(paths['feature_manifest'])
    with tempfile.TemporaryDirectory(prefix='wildfire-verify-') as tmp:
        args = SimpleNamespace(base_dir=config.WILDFIREIA_DIR, canonical_dir=config.CANONICAL_DIR,
            output_dir=Path(tmp),task=protocol.TASK,representation='tabular',weather_days=weather_days,
            input_protocol=feature_protocol,standardize=True,overwrite=False)
        rebuilt = Path(dl.build_tabular_cache(args, paths, manifest))
        for path in rebuilt.glob('*.npy'):
            a, b = np.load(path,allow_pickle=True), np.load(cache/path.name,allow_pickle=True)
            if not np.array_equal(a,b):
                raise ValueError(f'Cache differs from official rebuild: {path.name}')
        for path in rebuilt.glob('*.parquet'):
            pd.testing.assert_frame_equal(pd.read_parquet(path),pd.read_parquet(cache/path.name))
        original = json.loads((cache/'metadata.json').read_text())
        fresh = json.loads((rebuilt/'metadata.json').read_text())
        for key in ('source_feature_columns','feature_names','split_counts','preprocessing'):
            if original[key] != fresh[key]:
                raise ValueError(f'Cache metadata mismatch: {key}')
    record = {'input':fingerprint,'files':{p.name:digest(p) for p in cache.iterdir() if p.is_file() and p.suffix in {'.npy','.json','.parquet'}}}
    from .tracking import write_json
    write_json(marker,record)
    return record
