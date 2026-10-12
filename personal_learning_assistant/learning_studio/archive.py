"""Bounded in-memory archive reads. Never extracts uploaded paths to disk."""
import io
import json
from pathlib import PurePosixPath
import stat
import struct
import zipfile
import zlib
from .validation import PackageError, require, MAX_JSON

MAX_ARCHIVE = 25_000_000
MAX_EXPANDED = 30_000_000


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON object key.')
        result[key] = value
    return result


def decode_json(raw):
    require(isinstance(raw, bytes) and len(raw) <= MAX_JSON, 'JSON exceeds 2 MB.', 413)
    try:
        result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(PackageError('Non-finite JSON value.')))
        require(isinstance(result, dict), 'JSON package must be an object.')
        return result
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        if isinstance(error, PackageError): raise
        raise PackageError('Invalid JSON data.') from error


def read_zip(raw, *, pilot=False):
    require(isinstance(raw, bytes) and len(raw) <= MAX_ARCHIVE, 'ZIP exceeds 25 MB.', 413)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = z.infolist()
            require(0 < len(members) <= 550, 'Invalid archive member count.')
            require(sum(i.file_size for i in members) <= MAX_EXPANDED, 'Expanded archive exceeds 30 MB.', 413)
            names = set()
            result = {}
            for i in members:
                name = i.filename
                path = PurePosixPath(name)
                require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and '\x00' not in name,
                        'Unsafe archive path.')
                require(name not in names and not i.is_dir(), 'Duplicate or directory archive entry.'); names.add(name)
                mode = i.external_attr >> 16
                require(not stat.S_ISLNK(mode) and (not stat.S_IFMT(mode) or stat.S_ISREG(mode)), 'Archive symlinks/special files are not supported.')
                require(not i.flag_bits & 1, 'Encrypted archives are not supported.')
                require(i.file_size <= 4_000_000 and i.file_size / max(1, i.compress_size) <= 150,
                        'Oversized or excessively compressed archive member.', 413)
                if not pilot:
                    require(name == 'module.json' or (name.startswith('assets/') and len(path.parts) == 2 and path.suffix in {'.webp', '.png', '.jpg', '.jpeg'}),
                            'Canonical ZIP accepts module.json and owned raster assets only.')
                # Do not trust declared uncompressed size: ZipFile.read can inflate
                # much more before truncating to attacker-controlled file_size.
                require(i.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, 'Unsupported compression method.')
                offset = i.header_offset
                require(offset >= 0 and offset+30 <= len(raw), 'Invalid local ZIP header.')
                header = struct.unpack_from('<IHHHHHIIIHH', raw, offset)
                require(header[0] == 0x04034b50 and header[3] == i.compress_type, 'ZIP header mismatch.')
                start = offset + 30 + header[-2] + header[-1]
                end = start + i.compress_size
                require(start <= end <= z.start_dir, 'ZIP member exceeds archive bounds.')
                compressed = raw[start:end]
                if i.compress_type == zipfile.ZIP_STORED:
                    data = compressed
                else:
                    decoder = zlib.decompressobj(-15)
                    data = decoder.decompress(compressed, i.file_size + 1)
                    require(len(data) <= i.file_size and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                            'ZIP stream exceeds its declared bounded size.', 413)
                require(len(data) == i.file_size and zlib.crc32(data) == i.CRC, 'Archive member size/CRC mismatch.')
                result[name] = data
            return result
    except PackageError: raise
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error, struct.error) as error:
        raise PackageError('Invalid or unsupported ZIP archive.') from error


def decode_upload(raw, filename):
    if str(filename).lower().endswith('.json'):
        return decode_json(raw), {}
    require(str(filename).lower().endswith('.zip'), 'Choose a canonical JSON or ZIP package.')
    files = read_zip(raw)
    require('module.json' in files, 'Canonical ZIP requires module.json. Convert the proposed pilot first.')
    return decode_json(files.pop('module.json')), files
