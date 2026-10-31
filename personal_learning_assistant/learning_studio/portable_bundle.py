"""Validate self-contained Learning Studio ZIPs without executing their contents.

V1 ZIP layout:
  bundle.json ({"schema": "anvaya.learning-bundle.v1", "modules": ["theory", ...]})
  modules/<slug>/module.json
  modules/<slug>/source.pdf                (unchanged original PDF bytes)
  modules/<slug>/assets/<basename>         (optional owned raster previews)
  modules/<slug>/coverage.json             (optional source coverage report)
  extras/...                               (optional inert downloadable study files)

The source ID is deterministically bound to its exact SHA-256. The Studio
owns the PDF snapshot and checks it again before publication.
"""
from __future__ import annotations

import hashlib
import re

from .archive import decode_json
from .validation import require

SCHEMA = 'anvaya.learning-bundle.v1'
SLUG = re.compile(r'[a-z][a-z0-9_-]{0,39}\Z')
EXTRA = re.compile(r'extras/(?:Google_Colab|Study_Resources)/[A-Za-z0-9_.-]+\.(?:ipynb|md|csv|json)\Z')


def is_self_contained_bundle(members):
    return 'bundle.json' in members


def decode_self_contained_bundle(members):
    """Return (package, assets, coverage, PDF) tuples for validated staging.

    Call only with archive.read_zip(raw, pilot=True), which enforces bounded
    size, member count, safe paths, decompression ratios, and checksums.
    """
    require(isinstance(members, dict) and 'bundle.json' in members,
            'Self-contained package needs bundle.json.')
    manifest = decode_json(members['bundle.json'])
    require(set(manifest) == {'schema', 'modules'} and manifest['schema'] == SCHEMA,
            'Unsupported self-contained Learning Studio manifest.')
    names = manifest['modules']
    require(isinstance(names, list) and 1 <= len(names) <= 8 and
            all(isinstance(n, str) for n in names) and
            len(set(names)) == len(names) and
            all(SLUG.fullmatch(n) for n in names),
            'Self-contained modules need unique, safe names (up to eight).')
    expected = {'bundle.json'}
    prepared = []
    seen_ids = set()
    for name in names:
        prefix = f'modules/{name}/'
        module_name, source_name = prefix + 'module.json', prefix + 'source.pdf'
        require(module_name in members and source_name in members,
                'Each bundled module needs module.json and its exact original source.pdf.')
        expected.update((module_name, source_name))
        package = decode_json(members[module_name])
        require(isinstance(package.get('source'), dict) and isinstance(package.get('module_id'), str),
                'Bundled module has no source or stable module ID.')
        require(package['module_id'] not in seen_ids, 'Duplicate module identity in bundled import.')
        seen_ids.add(package['module_id'])
        source = members[source_name]
        digest = hashlib.sha256(source).hexdigest()
        require(source.startswith(b'%PDF-') and package['source'].get('sha256') == digest,
                'Bundled PDF does not match its immutable source checksum.')
        package['source']['source_id'] = 'portable.' + digest
        assets = {}
        for path, raw in members.items():
            if path.startswith(prefix + 'assets/'):
                filename = path[len(prefix):]
                require(re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(?:png|jpe?g|webp)', filename),
                        'Bundled asset is not a safe raster filename.')
                assets[filename] = raw
                expected.add(path)
        coverage_name = prefix + 'coverage.json'
        coverage = None
        if coverage_name in members:
            coverage = decode_json(members[coverage_name])
            expected.add(coverage_name)
        prepared.append((package, assets, coverage, source))
    extra_files = {name for name in members if name.startswith('extras/')}
    require(all(EXTRA.fullmatch(name) for name in extra_files),
            'Extras must be inert notebooks, Markdown, CSV or JSON study files.')
    require(set(members) == expected | extra_files,
            'Self-contained package has unrecognized or unlisted module entries.')
    return prepared
