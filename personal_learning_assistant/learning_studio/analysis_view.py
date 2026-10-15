"""Bounded read-only Learning Studio component for the existing Analysis hub."""
from __future__ import annotations
import sqlite3
from .service import OWNER
from .validation import PackageError

MAX_SIGNALS = 8


def component(studio):
    empty = {'available': True, 'evidence_label': 'No evidence', 'signals': [],
             'message': 'Try a lesson self-check; recorded misses will appear here.', 'truncated': False}
    try:
        evidence = studio.evidence()
        empty['evidence_label'] = evidence['evidence_label']
        with studio.store.connection() as con:
            if con is None:
                return empty
            # Bound module context reads independently of total history size.
            rows = con.execute('''SELECT module_id,revision,max(seq) latest FROM attempts
                WHERE owner=? GROUP BY module_id,revision ORDER BY latest DESC LIMIT ?''',
                (OWNER, MAX_SIGNALS + 1)).fetchall()
        empty['truncated'] = len(rows) > MAX_SIGNALS
        signals = []
        for row in rows[:MAX_SIGNALS]:
            try:
                context = studio.review_context(row['module_id'], row['revision'])
            except PackageError:
                signals.append({'title': 'Source unavailable', 'mapping_status': 'needs_review',
                                'evidence_label': 'Limited evidence', 'unavailable': True,
                                'reason': 'The historical source could not be verified. Recheck its registration.'})
                continue
            misses = context['missed_questions']
            base = f"/learning/modules/{row['module_id']}/{row['revision']}"
            if not misses:
                signals.append({'title': context['title'], 'mapping_status': context['mapping_status'],
                                'evidence_label': context['evidence_label'], 'unavailable': False,
                                'currently_wrong': 0, 'recovered': 0,
                                'reason': 'No recorded misses in this revision. Try another question; correct responses alone do not establish mastery.',
                                'review_url': base + '?view=learn', 'recheck_url': base + '?view=practice',
                                'revision_url': base + '?view=revision',
                                'unverified_pages': context['semantic_review_pages']})
                continue
            # Stable sorts: unresolved repeated misses first, recent first for ties.
            ordered = sorted(misses, key=lambda m: m['last_incorrect'], reverse=True)
            ordered.sort(key=lambda m: (m['latest_correct'], -m['incorrect_count']))
            miss = ordered[0]
            current_wrong = sum(not m['latest_correct'] for m in misses)
            recovered = len(misses) - current_wrong
            reason = (f"{miss['incorrect_count']} recorded misses; reread the cited lesson."
                      if not miss['latest_correct'] else
                      'A correct retry followed a miss; recheck without the explanation.')
            signals.append({'title': context['title'], 'mapping_status': context['mapping_status'],
                            'evidence_label': context['evidence_label'], 'unavailable': False,
                            'currently_wrong': current_wrong, 'recovered': recovered, 'reason': reason,
                            'review_url': miss['lesson_url'], 'recheck_url': miss['question_url'],
                            'revision_url': base + '?view=revision',
                            'unverified_pages': context['semantic_review_pages']})
        empty['signals'] = signals
        return empty
    except (PackageError, sqlite3.Error, OSError):
        return {**empty, 'available': False, 'message': 'Learning Studio evidence is unavailable. Open the library to check its source or store.'}
