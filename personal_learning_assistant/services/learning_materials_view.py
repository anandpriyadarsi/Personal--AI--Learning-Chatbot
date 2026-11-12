"""Read-only Learning Studio projection of the original-file Library.

Folders and document names always come from the native Library owner. The MIT
collection is a virtual, explicitly identified view; it never reparents files
or changes the subject/retrieval/lesson relationships.
"""
from __future__ import annotations

import re

_MIT_MARKER = re.compile(
    r"(?<![A-Za-z])MIT(?![A-Za-z])|Massachusetts\s+Institute\s+of\s+Technology|ocw\.mit\.edu",
    re.IGNORECASE,
)
PAGE_SIZE = 30


def is_mit_material(value: object) -> bool:
    """Match a clearly labeled MIT source, not e.g. 'limits' or 'submit'."""
    return bool(_MIT_MARKER.search(str(value or "")))


def _page_number(page: object) -> int:
    try:
        number = int(page)
    except (TypeError, ValueError) as error:
        raise ValueError("Choose a valid material page.") from error
    if isinstance(page, bool) or not 1 <= number <= 100000:
        raise ValueError("Choose a valid material page.")
    return number


def browse_materials(library, *, folder_id=None, subject_id=None,
                     collection=None, page=1):
    """Return a bounded, display-only view of the installed original files.

    A source only belongs to the MIT collection if its existing name/tags
    explicitly say MIT or it was placed inside an MIT-labeled folder. This
    deliberately avoids guessing course provenance from PDF contents.
    """
    number = _page_number(page)
    if sum(bool(item) for item in (folder_id, subject_id, collection)) > 1:
        raise ValueError("Choose one source scope.")
    if collection not in (None, "mit"):
        raise ValueError("Unknown material collection.")

    if collection == "mit":
        with library.connection() as con:
            con.create_function("is_explicit_mit", 1, is_mit_material,
                                deterministic=True)
            scope = """WITH RECURSIVE mit_folders(id) AS (
                SELECT id FROM folders WHERE is_explicit_mit(name) = 1
                UNION
                SELECT f.id FROM folders f JOIN mit_folders m ON f.parent_id = m.id
            ) """
            where = """d.trashed_at IS NULL AND (
                d.folder_id IN (SELECT id FROM mit_folders)
                OR is_explicit_mit(d.display_name) = 1
                OR is_explicit_mit(d.original_name) = 1
                OR is_explicit_mit(d.tags) = 1
            )"""
            total = con.execute(scope + "SELECT COUNT(*) FROM documents d WHERE " + where).fetchone()[0]
            records = con.execute(
                scope + "SELECT d.* FROM documents d WHERE " + where +
                " ORDER BY d.display_name COLLATE NOCASE, d.id LIMIT ? OFFSET ?",
                (PAGE_SIZE, (number - 1) * PAGE_SIZE),
            ).fetchall()
        documents = [library._doc(row) for row in records]
        return dict(title="MIT Course Materials", collection="mit", folders=[],
                    breadcrumbs=[], documents=documents, total=total,
                    page=number, page_size=PAGE_SIZE, folder_id=None,
                    subject_id=None)

    if subject_id:
        # The subject mapping is checked by the HTTP layer against the
        # canonical course catalogue. Include files in nested subfolders.
        with library.connection() as con:
            total = con.execute(
                "SELECT COUNT(*) FROM documents d WHERE d.trashed_at IS NULL AND d.subject_id=?",
                (subject_id,),
            ).fetchone()[0]
            records = con.execute(
                """SELECT d.* FROM documents d
                   WHERE d.trashed_at IS NULL AND d.subject_id=?
                   ORDER BY d.display_name COLLATE NOCASE, d.id LIMIT ? OFFSET ?""",
                (subject_id, PAGE_SIZE, (number - 1) * PAGE_SIZE),
            ).fetchall()
        return dict(title="Course source files", collection=None, folders=[],
                    breadcrumbs=[], documents=[library._doc(row) for row in records],
                    total=total, page=number, page_size=PAGE_SIZE,
                    folder_id=None, subject_id=subject_id)

    # Native Library already owns folder hierarchy, sort rules and names.
    child_page = library.children(folder_id, offset=0, limit=100)
    stored = library.list_documents(folder_id=folder_id, sort="name",
                                    page=number, page_size=PAGE_SIZE)
    crumbs = library.breadcrumbs(folder_id) if folder_id else []
    return dict(title=crumbs[-1]["name"] if crumbs else "Original study materials",
                collection=None, folders=child_page["items"],
                more_folders=child_page["total"] > len(child_page["items"]),
                breadcrumbs=crumbs, documents=stored["items"],
                total=stored["total"], page=number, page_size=PAGE_SIZE,
                folder_id=folder_id, subject_id=None)



def recover_registered_titles(native_library, items):
    """Use existing native display names only for verified canonical source links.

    An explicit registered rename takes precedence over this fallback. If no
    trustworthy name exists, the UI must still ask the owner to identify it.
    This is a read-only metadata crosswalk; never guess from file contents.
    """
    wanted = {
        item.reference.id: item.content_hash
        for item in items
        if item.reference.kind == 'document'
        and item.title.startswith('Unnamed ')
        and re.fullmatch(r'[0-9a-fA-F]{64}', item.content_hash or '')
    }
    if not wanted:
        return {}
    placeholders = ','.join('?' for _ in wanted)
    with native_library.connection() as con:
        rows = con.execute(
            """SELECT l.source_id, l.content_hash, d.display_name, d.original_name
               FROM source_links l JOIN documents d ON d.id=l.document_id
               WHERE l.namespace='canonical' AND l.source_id IN ("""
            + placeholders +
            """) AND d.sha256=l.content_hash AND d.trashed_at IS NULL
               ORDER BY d.updated_at DESC, d.id""",
            tuple(wanted),
        ).fetchall()
    found = {}
    for row in rows:
        if row['source_id'] in found or wanted.get(row['source_id']) != row['content_hash']:
            continue
        name = str(row['display_name'] or '').strip()
        if not name or len(name) > 255:
            continue
        # Migration-specific names contain only an abbreviated internal ID.
        if re.fullmatch(r'Imported PDF [0-9a-fA-F]{8}\.pdf', name):
            continue
        if re.fullmatch(r'[0-9a-fA-F]{32}(?:[0-9a-fA-F]{32})?(?:\.[A-Za-z0-9]+)?', name):
            continue
        found[row['source_id']] = name
    return found
