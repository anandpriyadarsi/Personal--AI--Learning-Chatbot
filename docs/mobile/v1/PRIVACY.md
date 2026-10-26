# Privacy threat model — recorded before implementation

Scope: one owner's private application. Cloud development uses only disposable,
synthetic academic stores. Existing installed files are never copied or opened.

| Boundary | Threat | Control / residual limitation |
| --- | --- | --- |
| Android phone | Other apps, unlocked phone, screenshots, browser profile compromise | No academic offline persistence; OS lock/encryption and trusted browser required. Rendered data and browser memory remain visible to the user/device. |
| Host | Theft, malware, unauthorized LAN requests | Existing local SQLite authority; loopback-only launcher. No cloud database/sync. Host disk/backups remain owner's responsibility. |
| Browser cache | Academic HTML/API transcripts retained | no-store for private responses. SW allowlist holds only public application assets and generic fallback. No local/session storage of academic text. Display/navigation preferences only; legacy palette keys include a session identifier, never answers. Browser history/OS screenshots cannot be erased by HTTP headers. |
| Service worker | Stale shell, poisoned runtime cache, session interruption | Exact same-origin reviewed paths; no runtime page/API writes; versioned cache; network-first navigations with generic fallback; no skipWaiting/clients.claim/reload. Close saved sessions before upgrade. |
| Logs | Student text, IDs or keys in debug/access/error logs | Private launcher disables Werkzeug access logging and debug. No payload logging added; exception details are not sent to client. Reverse proxy logs need separate review/redaction. |
| GitHub/Actions | Secrets or records in source/artifacts | Synthetic-only fixtures; no provider secrets in mobile CI; explicit staged-file review. Screenshots and JUnit contain only synthetic data. No forks receive credentials. |
| AI providers | Questions, sources, transcript sent off device | Private mode denies HTTP provider even if host keys exist. Explicit host-side opt-in requires acknowledgement of question/source/history transmission. No automatic AI call or browser opt-in switch. Existing deterministic local help remains available. |
| Browser outbound | Remote fonts/scripts/math/telemetry | Private-mode CSP restricts resource loading and fetch to same origin, blocks third-party frames/objects; locally served assets. External links are deliberate user navigation. |
| Cross-device | LAN sniffing, arbitrary host access | No supported raw LAN/public binding. Authenticated TLS gateway not included: cross-device use BLOCKED until separately configured/validated. HTTPS alone is not authentication. |
| Failed connections | Unsaved writes mistaken for successful saves | No queued/replayed mutations; connection status describes limitations. Refresh only after checking saves. Existing persisted state and assessment clock remain authoritative. |

Private cloud-AI opt-in is host configuration, not an HTTP request parameter:
ANVAYA_MOBILE_ALLOW_CLOUD_AI=true plus
ANVAYA_MOBILE_AI_DATA_ACK=questions-sources-history-leave-device.
Opt-in does not initiate a call; explicit existing Tutor actions are still required.
No encryption-at-rest or fully standalone Android capability is claimed.
