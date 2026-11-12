"""Read-only Learning Studio view of the original-file Library.

The Library remains the sole owner of original bytes, display names, folder
placements, and canonical source links. No GET creates a Library or imports data.
"""
from __future__ import annotations

import re
from flask import current_app

MIT_FOLDER_NAME = "MIT Course Materials"
_IMPORTED_PLACEHOLDER = re.compile(r"Imported PDF [0-9a-f]{8}\.pdf", re.IGNORECASE)


def ready_library():
    """Return the already-started local file manager; never initialize it on GET."""
    supplied = current_app.config.get("NATIVE_LIBRARY_SERVICE")
    return supplied if supplied is not None else current_app.extensions.get("native_document_library")


def material_snapshot(library, *, folder_id=None, page=1, folder_offset=0):
    """Browse actual folder/file metadata without copying or reclassifying anything."""
    if library is None:
        return {"available": False, "folders": [], "documents": [],
                "breadcrumbs": [], "mit_folder": None, "total": 0,
                "folder_total": 0, "page": page, "page_size": 24,
                "folder_id": folder_id, "folder_offset": folder_offset}

    roots = library.children(None, limit=100)["items"]
    mit_folder = next((item for item in roots
                       if item["name"].casefold() == MIT_FOLDER_NAME.casefold()), None)
    crumbs = library.breadcrumbs(folder_id) if folder_id else []
    folder_page = library.children(folder_id, offset=folder_offset, limit=100)
    document_page = library.list_documents(folder_id=folder_id, page=page,
                                           page_size=24, sort="name")
    return {"available": True, "folders": folder_page["items"],
            "folder_total": folder_page["total"],
            "documents": document_page["items"], "total": document_page["total"],
            "breadcrumbs": crumbs, "mit_folder": mit_folder,
            "page": page, "page_size": 24, "folder_id": folder_id,
            "folder_offset": folder_offset}


def canonical_document_titles(library, identities):
    """Find user-managed names for exact (canonical ID, content hash) source links.

    A hash alone is *not* sufficient: two distinct academic sources may have
    identical bytes but different ownership. Never infer a title from a loose
    filename, a folder name, or an unverifiable migration placeholder.
    """
    if library is None or not identities:
        return {}
    pairs = list(dict.fromkeys(
        (source_id, digest) for source_id, digest in identities
        if isinstance(source_id, str) and isinstance(digest, str)
    ))
    if not pairs:
        return {}
    result = {}
    # Stay well below SQLite's parameter bound even with large library pages.
    for start in range(0, len(pairs), 100):
        batch = pairs[start:start + 100]
        clauses = " OR ".join("(s.source_id=? AND s.content_hash=?)" for _ in batch)
        args = [value for pair in batch for value in pair]
        with library.connection() as con:
            rows = con.execute(
                "SELECT s.source_id, s.content_hash, d.display_name "
                "FROM source_links s JOIN documents d ON d.id=s.document_id "
                "WHERE s.namespace='canonical' AND d.trashed_at IS NULL "
                "AND (" + clauses + ") ORDER BY d.updated_at DESC, d.id",
                args,
            ).fetchall()
        for row in rows:
            name = str(row["display_name"] or "").strip()
            key = (row["source_id"], row["content_hash"])
            if name and not _IMPORTED_PLACEHOLDER.fullmatch(name):
                result.setdefault(key, name)
    return result
