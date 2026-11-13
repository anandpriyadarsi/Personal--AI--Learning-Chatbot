# Provider request recovery

This command is for a stopped application, using the existing **Native Library** SQLite database containing `mm_provider_requests`. It does not activate or migrate a database. No startup repair or public recovery endpoint exists.

First stop **every ANVAYA app process and worker writing this owner**, then verify they have stopped. `--writers-stopped` is your acknowledgement, not process detection or proof that another writer has died. A sending row has no timestamp or lease; its age cannot establish that it is abandoned. Follow the existing backup procedure before any operator mutation.

Inspect without mutation (the default is a read-only SQLite connection):

```sh
python -m scripts.multimodal_requests --database /path/to/native_library/library.sqlite3 --list
python -m scripts.multimodal_requests --database /path/to/native_library/library.sqlite3 --operation EXACT_ID --dry-run
```

The output includes only operation ID, accounting month, reserved/actual micro-dollar values and status. It omits consent scope, permission ID, source text and credentials. A missing database or missing request table fails without creating or migrating either.

After checking the exact ID and stopping all writers:

```sh
python -m scripts.multimodal_requests --database /path/to/native_library/library.sqlite3 --operation EXACT_ID --mark-unknown --writers-stopped
```

The transaction changes only `sending` → `outcome_unknown`. Reserved cost, actual cost, permission ID, accounting month and unique operation ID remain intact. A repeated recovery returns `changed: false`; missing/invalid/complete/failed operations are rejected. A complete operation whose artifact was lost must remain complete: recovery cannot refund it or make it dispatchable again. A concurrent normal finish cannot overwrite an already-recovered outcome.

Recovery does not refund, delete, resend, clear a source cache, or grant consent. It releases the global “sending” exclusion so separately authorized, distinctly identified future work can proceed, while the recovered operation still consumes its existing accounting amount and remains blocked against replay. Default zero budgets still disable paid work. Never change IDs merely to bypass an unknown outcome. A timeout or lost response cannot establish whether the provider billed the request.

## Transport containment

Vision extraction and the existing multimodal-guarded answer/repair path use a dedicated Python subprocess that owns the HTTP connection. Credentials and selected evidence pass through bounded stdin, not command arguments, files or logs. The child imports the transport module directly, not the app entrypoint, and does not inherit SQLite objects or app threads.

The parent enforces a 90-second elapsed deadline across child startup, request transfer, DNS/TLS/headers and response streaming. Socket timeouts remain 5 seconds for connect and 60 seconds for read, but these do not replace the total deadline. A slow stream cannot keep the request alive indefinitely. After expiry/error/caller interruption, the parent terminates the child, escalates to kill if needed, reaps it and closes pipes. Reaping allows two additional waits of at most 0.5 seconds each; OS process creation/termination scheduling is not a real-time guarantee. Windows uses the same subprocess API but requires actual runtime verification.

There are no redirects or automatic retries. Response bytes stay limited to 128,000; request serialization is limited to 13,000,000 bytes. Non-200 responses, malformed JSON, overflow, missing replies and child failures produce one generic error without raw upstream details. Existing guard callers retain unknown reservations after failures. Existing source, consent, cancellation and publication fences still run after a response; cancellation/revocation never grants permission to persist an answer. Killing the local connection cannot cancel or reverse a request already accepted by the remote provider.

## Offline verification

The transport tests use a real loopback HTTP server and synthetic keys only. They test a stream where each read succeeds but the total deadline expires, successful bounded replies, oversized replies, malformed replies, non-200 replies, redirect rejection, one-request-only behavior, process reaping and closed pipes. Recovery tests cover duplicate/concurrent recovery, accounting/replay retention, read-only CLI safety, revoked/cancelled in-flight work and a response-before-artifact crash. Fake-provider tests verify accounting and containment behavior, not live model quality.

```sh
python -m pytest -q tests/test_multimodal_request_recovery.py tests/test_multimodal_provider_transport.py tests/test_multimodal_vision.py tests/test_multimodal_contracts.py tests/test_multimodal_grounding.py
```

No paid call, personal-store mutation or schema change is needed for these tests.
