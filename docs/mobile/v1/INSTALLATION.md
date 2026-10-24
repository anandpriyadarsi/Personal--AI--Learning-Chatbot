# Private installation and runtime

## What you can use now

This branch is a private PWA client for the existing Python application. It is
not a standalone Android application. The development environment does not host
your real academic data and is not a permanent phone-access service.

On a trusted machine with your existing ANVAYA environment:

1. Check out `feature/mobile-v1-private-pwa-2026-10` (keep your normal backups).
2. Activate your existing Python environment. For synthetic validation only,
   `python -m pip install -r requirements-mobile.txt` installs the test subset.
3. Run `python mobile_web.py`.
4. Open `http://127.0.0.1:5000` **on that same machine**. The usual local startup
   owns backup-first Assessment activation and WAL publication; mobile adds no
   migration. Do not point cloud tests at an installed database.
5. Open **App & privacy** in the navigation to choose a theme and review the
   connection/installation limits.

The private launcher binds only to loopback, disables debug/reloader/access logs,
checks loopback peers and trusted hostnames, denies cross-site writes and cloud
AI, and applies same-origin browser resource policies. Do not change the bind to
`0.0.0.0` or expose a public tunnel to work around phone access.

## On your Android phone

**No personal laptop/authorized Python host available: academic use is BLOCKED.**
You cannot install the Python backend merely by installing this PWA. Cloud
screenshots and CI still work without your laptop; personal academic operation
needs an authorized runtime.

Once a separate authenticated, encrypted cross-device connection is implemented
and validated, the intended Android sequence is: open that trusted HTTPS URL in
Chrome → browser menu → **Add to Home screen → Install** → launch ANVAYA. The
Python host must remain available. That gateway is not supplied or activated by
this branch; no URL for personal academic access is claimed here.

Same-device localhost is a browser secure-context exception for PWA development.
A laptop's `127.0.0.1` refers to the laptop; entering it on your phone refers to
the phone. Plain LAN HTTP does not satisfy this release's transport requirements.

## Offline, saves and upgrades

Only five generic app resources are stored in Cache Storage: fallback HTML,
mobile CSS/JS and two icons. Academic pages, APIs, files, answers and transcripts
are never added. Offline operation shows a connection explanation, not private
learning content. There is no mutation queue or automatic replay.

A response can reach the host while its acknowledgement is lost: after a
connection failure, check saved state before resubmitting. The interface never
claims a successful save without the existing server acknowledgement. Assessment
time follows the original server rules. Pausing takes effect only after a
successful response. A connection banner does not pause an assessment.

Save/pause first, then close all ANVAYA tabs/windows to activate a waiting update.
The worker does not force activation, claim open clients or reload a page.
To remove generic cached assets, uninstall the PWA and clear site storage in the
browser. This does not remove host academic records or backups.

## Explicit cloud-AI opt-in (host only)

Private mode ignores configured provider keys unless BOTH environment values are
set by the owner:

```
ANVAYA_MOBILE_ALLOW_CLOUD_AI=true
ANVAYA_MOBILE_AI_DATA_ACK=questions-sources-history-leave-device
```

This acknowledges that explicit provider actions can transmit questions, source
excerpts and conversation history to the configured provider. Keys remain only
on the host. There is no browser switch or automatic provider call. Remove either
value and restart to restore default denial. Local help and source browsing do
not require this permission. Live model teaching quality is not certified by
mobile's deterministic provider tests; Tutor PR #32 retains its separate gates.
