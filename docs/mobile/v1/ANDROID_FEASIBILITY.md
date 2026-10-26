# Android runtime and APK feasibility

22 October 2026. No APK has been produced or real-device tested.

| Option | Academic runtime | Offline academic data | Decision |
| --- | --- | --- | --- |
| Flask/Jinja PWA | Existing authorized Python host | None by default; generic fallback only | Implemented client foundation, no hosting bill or API usage |
| TWA / Capacitor / WebView wrapper | Still needs Python host | A wrapper does not supply Python, SQLite owners or reviewed offline data | Deferred; would not solve owner's no-laptop requirement |
| Embedded Python with Chaquopy | Potentially on Android in a separate private app | Needs private app storage, record import/export, backup and process lifecycle review | Feasibility candidate only; not certified compatible |
| Termux Python | Potentially phone-hosted | Owner-managed private runtime | Not validated; not presented as supported installation |

A genuinely standalone app needs an Android build environment, selected Python
ABI and package audit, native dependency support (including optional retrieval /
PDF libraries), private filesystem paths, background/foreground lifecycle,
resource URI handling, SQLite/WAL/backup restoration acceptance, local webview
security and signed-package management. The cloud workspace has no `adb` or
`sdkmanager` installed and no physical Android device. Installing a toolchain
would not establish dependency compatibility or device acceptance.

Inference from ANVAYA's existing host and library dependencies: embedding only
the minimal deterministic Flask/SQLite reader may be possible, but certifying
all ANVAYA academic engines as an Android runtime requires a separate increment.
No unverified APK shell is substituted for a working application.

Restricted offline subset: current release contains only nonsensitive connection
help. Any personal lesson subset needs explicit owner opt-in plus a separate
review of encryption/key storage, record authority, revocation, provenance,
backup/restore and conflict behavior. No such personal-data cache is enabled.

Next acceptance gates: minimal embedded-Python synthetic reader → app-private
SQLite/provenance/save/restart and backup recovery → offline assessment clock
semantics → real Android 12 device (owner's platform) → signed private APK. No
public store publication or paid infrastructure is required or authorized.

## Primary references checked

- [MDN: PWA installation and secure contexts](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)
- [Chrome: worker waiting lifecycle](https://developer.chrome.com/docs/workbox/service-worker-lifecycle)
- [Android Developers: Trusted Web Activities](https://developer.android.com/develop/ui/views/layout/webapps/trusted-web-activities)
- [Chaquopy: Android Python runtime and platform limitations](https://www.chaquo.com/chaquopy/doc/current/android.html)

These references support runtime distinctions; they do not certify this
repository on Android. Exact Android/Python/Gradle versions must be rechecked at
standalone implementation time.
