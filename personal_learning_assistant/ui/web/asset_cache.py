"""Content-versioned packaged assets only; never cache academic HTML or APIs."""
from functools import lru_cache
import hashlib
from pathlib import Path
from flask import current_app, request


@lru_cache(maxsize=512)
def _digest(path, mtime_ns, ctime_ns, size):
    # File identity invalidates the digest after installed package changes.
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:20]


def asset_version(filename):
    root = Path(current_app.static_folder).resolve()
    path = (root/filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    info = path.stat()
    return _digest(str(path),info.st_mtime_ns,info.st_ctime_ns,info.st_size)


def register_asset_cache(app):
    @app.url_defaults
    def version(endpoint,values):
        if endpoint == 'static' and 'filename' in values and 'v' not in values:
            digest = asset_version(values['filename'])
            if digest:
                values['v'] = digest

    @app.after_request
    def cache(response):
        if request.endpoint == 'static' and request.method in ('GET','HEAD') and response.status_code in (200,304):
            version = asset_version(request.view_args.get('filename',''))
            response.headers['Cache-Control'] = ('private, max-age=300' if
                version and request.args.get('v') == version else 'private, max-age=0, must-revalidate')
        else:
            response.headers['Cache-Control'] = 'private, no-store' if response.cache_control.private else 'no-store'
        return response
