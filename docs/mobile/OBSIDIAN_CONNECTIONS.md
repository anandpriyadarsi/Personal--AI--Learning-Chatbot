# Optional Obsidian connection

Obsidian lives under **Library → Connected Sources**. ANVAYA Notes remains the
independent default note store. Disconnecting or replacing an Obsidian connection
does not remove ANVAYA Notes or write to an original Obsidian vault.

## Android: supported ZIP snapshot workflow

1. Export or ZIP one vault, including its hidden `.obsidian` folder. Either the
   vault contents or one enclosing vault folder may be at the ZIP root.
2. Open Obsidian connection settings and choose **Import snapshot**. The device
   file chooser selects the ZIP; ANVAYA copies only UTF-8 Markdown into a new
   private snapshot folder.
3. Browse and search with the existing Markdown reader, wikilinks and backlinks.
   Select up to 20 notes and choose **Copy selected to ANVAYA Notes** to make
   independently editable copies. Copies retain Markdown text; links are not
   retargeted, attachments are not imported, and Obsidian settings are not run.
4. Export and upload another ZIP to refresh. A successful upload replaces the
   current connection. This is an explicit snapshot refresh, **not live sync**.
   Repeated note copies create additional ANVAYA Notes.

Limits: 25 MB compressed, 100 MB declared expanded, 2,000 ZIP entries, and 500 KB
per Markdown file. ZIP traversal, absolute and Windows-drive paths, symlinks,
special filesystem entries, encrypted entries, and duplicate paths are rejected.
Missing/ambiguous vault markers and invalid UTF-8 Markdown are rejected. The
existing connection is updated only after the new snapshot is fully validated
and written. Configuration uses an atomic replacement; failed imports remove
their incomplete new snapshot.

Disconnect removes only the configuration reference. Original vaults, previous
private snapshots, and independent ANVAYA Notes are retained. There is currently
no snapshot deletion UI. Keep this in mind on devices with limited storage.
Selections and native note payloads are validated before note creation. The
selected text-only notes are saved in one atomic index replacement, so a failed
batch copy leaves the original native note index unchanged.

Native Android backup exports the complete `data/` tree, including imported
snapshots, their inert `.obsidian/app.json` markers, and independent ANVAYA Notes.
Snapshot IDs resolve against the restored data root rather than an old absolute
runtime path. Backup's separate 100 MB / 1,000-file total limit still applies to
the entire store: accumulated snapshots can make a backup too large even when
each individual vault import meets its limits. Keep the original ZIP separately.
The legacy desktop `backup_database()` covers only its legacy notes/resources
files and does not back up Obsidian snapshots or external desktop vaults.

## Android folder access investigation

The Android wrapper's `MainActivity.onShowFileChooser` supports
`ACTION_OPEN_DOCUMENT` for individual files and hands read-only content URIs to
WebView. It does not implement `ACTION_OPEN_DOCUMENT_TREE`, persist a tree URI
permission, or adapt an Android `DocumentFile` tree to the Python path-based
vault reader. A content URI cannot truthfully be used as a host filesystem vault
path. This build therefore uses the working ZIP picker workflow and hides desktop
folder fields when `PRIVATE_MOBILE_MODE` is enabled. Direct shared-folder access,
background refresh, bidirectional edits, and cloud synchronization are unavailable.

## Desktop

The connection page also accepts an existing vault folder on the ANVAYA host.
That connection reads current Markdown using the existing safe filesystem reader.
It does not write notes back to the vault. Existing reading history, companion,
links, backlinks and search behavior remain available.

The reader offers **Open in Obsidian** for desktop-folder connections. The link
requires Obsidian and that vault on the current device. The reader stays usable
if no handler is available. Snapshot connections hide this link because their
private copied folder is not the user's Obsidian vault.

## Wiring and tests

Register `register_obsidian_connections(app)` after `register_notes_media(app)`.
The settings endpoint is `obsidian_connections.settings` at
`/library/connected-sources/obsidian`. All new POST actions require the shared
`notes_media_csrf` token, supplied as `csrf_token` or `X-Notes-CSRF`.
The desktop-only connect POST also enforces the mobile gate on the server.

Run `python -m pytest tests/test_obsidian_connections.py` for snapshot validation,
atomic failure behavior, original-source preservation, Markdown reader integration,
independent note copies, Android field gating, and actual upload/copy/disconnect
routes.
