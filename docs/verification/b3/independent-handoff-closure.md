# Independent generated-handoff consistency review

Date: 2026-10-14. Scope: actual six generated B3 delivery documents and their tracked evidence records for accepted executable/test/workflow revision `63c5a636f4e737c204a791360e2bc715c9ac945f`, run `38525732263`. No source/architecture audit, test rerun, production access or tracked-file edits. This is a targeted continuation of the handoff preflight.

## Final disposition: H1, H2 and D1–D3 CLOSED

No outstanding Important/Critical finding in the generated documents/evidence within this targeted review. The H2 finding and its verified repair are retained below as review history. The forthcoming documentation-only successor still requires its own exact-source acceptance before final delivery.

### H2 — Important: case_manifest_sha256 does not identify CASE_MANIFEST.json bytes

The generated `docs/verification/b3/SOURCE_ACCEPTANCE.json` contains:

```text
case_manifest_sha256 = a9c63d0f682748a63d5c0de9a458be57b3de835fed152461fd8c937ad3ffe93b
```

But SHA-256 of the actual adjacent `CASE_MANIFEST.json` bytes is:

```text
534b29557bb1047d9d367206c3e4316839fc34de9104dfff6846cbe0d9f7c9c9
```

Independently confirmed the claimed digest instead equals `sha256(json.dumps(manifest['cases'], sort_keys=True).encode())`. The verifier hashes only the canonical cases subobject, whereas the field name presents it as the manifest hash. Source/CI/case contents themselves are consistent; this is an evidence-integrity labelling issue, not a test failure or corrupt downloaded artifact.

Required correction: store the actual file-byte SHA under `case_manifest_sha256`, or rename this field to `case_inventory_sha256` and explicitly specify its canonical JSON encoding. An actual file digest is simplest for reproducible archive integrity. Verify the corrected tracked record against the actual tracked manifest before final closure.

### H2 repair independently verified

After the implementer repaired the verifier and regenerated the evidence, independently recomputed both digests from the actual tracked manifest. `case_manifest_sha256` now equals the file-byte digest `534b29557bb1047d9d367206c3e4316839fc34de9104dfff6846cbe0d9f7c9c9`. The former digest is retained under the accurately named `case_inventory_sha256` and equals `a9c63d0f682748a63d5c0de9a458be57b3de835fed152461fd8c937ad3ffe93b`, independently recomputed from the sorted-key JSON encoding of the `cases` subobject. Exact source remains63c5. Both assertions passed; H2 is CLOSED. No product or workflow source change was needed.

## Closed handoff findings

- **H1 CLOSED:** actual implementation report now distinguishes unavailable original command/browser-failure logs from historical transcript counts, fresh verification and authentic recovered hosted artifacts. Recovery and validation documents agree about lost originals; they do not fabricate retained failure bytes.
- **D1 CLOSED:** actual Windows command pins full `ed2bf73e4b3f1c52d372196da7006889afeb46c9`, verifies the commit object, and uses it for both wrapper extraction and ToolsRef. Independently compared Git blobs for `scripts/architecture_local_collector.py` and `scripts/b3_collect_authority.ps1` between that pin and accepted `63c5a636`: both are identical.
- **D2 CLOSED for the documented default-policy scenario:** actual handoff uses the in-memory command body, not temporary script-file execution. Read the raw exact-63c5 `B3_POLICY_ACCEPTANCE.json` and matched it against tracked `SOURCE_ACCEPTANCE.json`: process Restricted, persistent policies unchanged, default no-DB access and status PASS. This review did not rerun native Windows or claim compatibility with every organization policy.
- **D3 CLOSED:** actual report identifies accepted executable revision63c5/run38525732263, records successful fresh local and hosted results, removes stale rerun-required language and preserves failure/recovery history. Accepted executable source is distinguished from the forthcoming documentation/evidence-only successor. No successor SHA or successor PASS result is invented. Its own final exact-source validation and archive DELIVERY.json remain delivery obligations; this review does not certify an uncreated successor.

## Independent actual-output consistency checks

- Read all six documents: implementation report, automated validation report, authority contract, Windows handoff, next-work prompt and Gate C readiness.
- `SOURCE_ACCEPTANCE.json`, aggregate, native policy and case manifest all identify exact source `63c5a636f4e737c204a791360e2bc715c9ac945f`; aggregate is PASS and installed authority remains BLOCKED.
- Both platform summaries show clean sources, all15 categories PASS and exit0. Reported physical fingerprints match the tracked summaries.
- Parsed the downloaded full pytest XML independently for each platform: **1968 case IDs** equal the tracked case inventory and each other, with no failure/error/skipped nodes.
- Case inventory contains focused54, fixture orders41/41, characterization17 and separate Chromium43, with empty failure/error/skip inventories.
- Read both downloaded Node logs: tests20/pass20/fail0, consistent with the report. Both hosted environment summaries identify Node22, distinct from the reported local Node24 environment.
- Reviewed FRESH_LOCAL_ACCEPTANCE, FAILED_ATTEMPT, PRESERVATION and WORKSPACE_RECOVERY for consistency with reported counts, missing evidence, historical failed attempts and preserved migration/source scope.
- 103 B3 cases =35 authority +42 attribution +26 collector; adding45 unchanged B1 and four original collector cases yields152 focused cases. No count contradiction found.
- Current pending tracked changes are delivery Markdown/JSON evidence; no executable/test/workflow change is represented as part of the final handoff-only successor. `git diff --check` passed.

B3-B and installed production authority remain BLOCKED, deployment NOT AUTHORIZED, and Gate C remains conditional. No text authorizes a main merge, live binding, production migration or academic-data mutation. Source-only future merge review is correctly distinguished from release/production readiness.

No outstanding Important/Critical finding within this targeted review. A minor duplicate acceptance-introduction paragraph appeared when the generator was rerun against already-generated documents; it was reported and the next read confirmed a single introduction in both implementation and next-work reports. This cleanup does not alter the evidence/gate conclusions. API artifact digest verification was performed by the implementer; this review inspected the downloaded records/XML/logs and their internal consistency, not a new remote artifact download.
