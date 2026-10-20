"""Read the Learning owner through Library's stable, bounded RAM capture."""
from contextlib import contextmanager
import copy
import sqlite3
from .store import APPLICATION_ID
from .validation import PackageError, require
from personal_learning_assistant.repositories.sqlite.learning_library_repository import LearningLibraryRepository, LibraryUnavailableError

class FrozenStudioStore:
    def __init__(self, payload, path):
        self._payload = payload
        self.path = path

    @contextmanager
    def connection(self, *, write=False):
        require(write is False, 'A frozen Learning snapshot cannot write.', 405)
        con = sqlite3.connect(':memory:', isolation_level=None)
        try:
            con.deserialize(self._payload)
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA query_only=ON')
            require(con.execute('PRAGMA application_id').fetchone()[0] == APPLICATION_ID and
                    con.execute('PRAGMA user_version').fetchone()[0] in (1,2),
                    'Unsupported Learning snapshot.', 503)
            con.execute('BEGIN')
            yield con
        except sqlite3.Error as error:
            raise PackageError('Learning snapshot unavailable.',503) from error
        finally:
            con.close()

def _no_live_loader(*args, **kwargs):
    raise PackageError('Read-only projection does not open a live registry.',405)

def frozen_studio(studio, *, catalogue=None):
    from .service import LearningStudioService
    require(isinstance(studio, LearningStudioService), 'Learning owner service required.')
    if isinstance(studio.store, FrozenStudioStore):
        clone = copy.copy(studio)
    else:
        try:
            studio.store._safe()
            payload = LearningLibraryRepository(studio.store.path)._capture_delete_source(studio.store.path)
        except (LibraryUnavailableError, OSError, ValueError) as error:
            raise PackageError('Learning requires a stable DELETE snapshot; live WAL/sidecars are unavailable.',503) from error
        clone = LearningStudioService(studio.store.path, source_loader=_no_live_loader,
            catalogue_loader=lambda:{'available':False,'courses':[]})
        clone.store = FrozenStudioStore(payload, studio.store.path)
        with clone.store.connection():
            pass
    cat = copy.deepcopy(catalogue) if catalogue is not None else {'available':False,'courses':[]}
    require(isinstance(cat,dict),'Canonical catalogue object required.')
    clone.catalogue_loader = lambda:copy.deepcopy(cat)
    clone.source_loader = _no_live_loader
    return clone
