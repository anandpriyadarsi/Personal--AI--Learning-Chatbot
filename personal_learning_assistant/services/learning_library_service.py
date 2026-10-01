"""Pure presentation assembly for the Learning Library. No runtime factories."""
from __future__ import annotations

from collections import Counter
from urllib.parse import parse_qsl, quote, urlsplit

from personal_learning_assistant.domain.learning_library_models import (
    LibraryAcademicLabel, LibraryDocumentView, LibraryItem, LibraryItemRef,
    LibraryPage, LibraryQuery, LibraryResourceDetail,
)
from personal_learning_assistant.repositories.sqlite.learning_library_repository import (
    LearningLibraryRepository, LibraryNotFoundError, LibraryUnavailableError, document_title,
)


def _external_url(value):
    # Same HTTP(S)+host boundary as existing readers, tightened to suppress credentials.
    text = str(value or '').strip()
    try:
        parts = urlsplit(text)
        if (parts.scheme.lower() not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or '\\' in text or any(ord(c) < 33 for c in text)):
            return None
        parts.port  # Reject malformed ports.
        keys = [key.casefold() for key, _ in parse_qsl(parts.query) + parse_qsl(parts.fragment)]
        if any(any(secret in key for secret in ('token', 'secret', 'password', 'signature', 'credential', 'api_key', 'apikey', 'authorization')) for key in keys):
            return None
    except ValueError:
        return None
    return text


def _labels(rows):
    return tuple(LibraryAcademicLabel(r['id'], r['label']) for r in rows)


def _source_target(identifier):
    return '/knowledge/item/' + quote(identifier, safe='')


def _extraction_summary(statuses):
    counts = Counter(statuses)
    if not counts:
        return 'No linked documents'
    return ' · '.join(f'{count} {status.replace("_", " ")}' for status, count in sorted(counts.items()))


class LearningLibraryService:
    def __init__(self, *, database_path='data/learning_assistant.db'):
        self.repository = LearningLibraryRepository(database_path)

    def list_items(self, query: LibraryQuery) -> LibraryPage:
        rows, relations, courses, total, total_all = self.repository.list_items(query)
        items = []
        for row in rows:
            is_resource = row['kind'] == 'resource'
            rel = relations.get(row['id'], {}) if is_resource else {}
            documents = rel.get('documents', ())
            items.append(LibraryItem(
                key=row['kind'] + ':' + row['id'],
                reference=LibraryItemRef(row['kind'], row['id']), title=row['title'],
                item_type=row['item_type'], provider=row['provider'],
                courses=_labels(rel.get('courses', ())), topics=_labels(rel.get('topics', ())),
                learning_status=row['learning_status'], document_count=len(documents) if is_resource else 1,
                note_count=len(rel.get('notes', ())),
                extraction_summary=_extraction_summary([d['extraction_status'] for d in documents]
                                                       if is_resource else [row['extraction_status']]),
                open_target='/library/resources/' + quote(row['id'], safe='') if is_resource else _source_target(row['id']),
            ))
        state = 'ready' if items else ('empty' if total_all == 0 else 'no_matches')
        return LibraryPage(tuple(items), query, _labels(courses), total,
                           (total + query.page_size - 1) // query.page_size, state)

    def resource_detail(self, resource_id: str) -> LibraryResourceDetail:
        row, rel = self.repository.resource_detail(resource_id)
        documents = tuple(LibraryDocumentView(
            d['id'], document_title(d['path_key']), d['kind'], d['mime_type'],
            d['content_hash'], d['extraction_status'], _source_target(d['id']),
        ) for d in rel['documents'])
        return LibraryResourceDetail(
            row['id'], row['title'], row['resource_type'], row['provider'], row['status'], row['updated_at'],
            _labels(rel['courses']), _labels(rel['topics']), documents, _labels(rel['notes']),
            _external_url(row['canonical_uri']),
        )
