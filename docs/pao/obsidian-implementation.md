# Obsidian implementation and measured boundaries

External Markdown remains authoritative. Explicit connection/snapshot/manifest commands own a portable derived projection with connection UUID, source UUIDs, hashes, versions, aliases and missing-source tombstones. Legacy unqualified assistant UUID histories are not assigned to the current vault. Qualified earlier path histories remain readable separately after first-manifest adoption.

Same-vault duplicate external IDs block tracking/annotations but allow safe reading. Identical files keep separate source UUIDs. Confirmed rename, ZIP Refresh and explicit verified root relocation retain source identity; Replace creates a distinct connection. No source frontmatter is inserted or rewritten.

Tracking validates the selected source version without rebuilding backlinks. Unified search reuses one workspace projection for all results. Markdown and ingestion share bounded descriptor reads with non-symlink path checks, regular-file checks, before/after file identity and version verification. Local raster images use the guarded asset route; remote images are omitted under the reader policy. Fenced/inline code and frontmatter do not become links/backlinks. Wiki/Markdown links preserve relative targets, aliases and heading/block anchors.

Copies are independent native Notes with immutable copied_from provenance. Selection carries expected hashes; stale source bytes block the copy. ZIP refresh/replacement and omissions are explicit. Original Markdown export is byte preserving and excludes plugins, attachments and companion history. Disconnect does not delete snapshots, original sources or native copies.

Synthetic warm-filesystem benchmark (Linux x86_64,9 logical CPUs,20 validations per size; JSON config reloaded every validation):

| Notes | Manifest refresh | Validation p50 | Validation p95 | Source opens/validation |
|---|---:|---:|---:|---:|
|100|0.017s|0.437ms|0.544ms|1|
|1,000|0.186s|3.796ms|4.504ms|1|
|10,000|1.525s|54.087ms|72.435ms|1|

Only one source note is opened for a heartbeat regardless of vault size. Config decoding/path lookup still scales with manifest size; this is disclosed rather than described as constant CPU cost. The measured synthetic desktop filesystem is not a physical Galaxy M11 benchmark. See benchmark.json and scripts/pao_obsidian_benchmark.py.
