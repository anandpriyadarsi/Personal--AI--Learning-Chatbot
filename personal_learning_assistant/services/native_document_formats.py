"""Explicit passive original-file allowlist. Code is stored as text, never run."""
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

MIMES = {
    'pdf':'application/pdf', 'ppt':'application/vnd.ms-powerpoint',
    'pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'doc':'application/msword','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp',
    'txt':'text/plain','md':'text/markdown','csv':'text/csv','py':'text/plain',
}
TEXT_KINDS = frozenset(('txt','md','csv','py'))


def validate(path, kind, prefix):
    if kind in TEXT_KINDS:
        if b'\0' in prefix: raise ValueError('Binary file is not UTF-8 text')
        # Full stream validation with constant memory, including boundaries.
        import codecs
        decoder=codecs.getincrementaldecoder('utf-8')('strict')
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(256*1024),b''):
                if b'\0' in chunk: raise ValueError('Binary file is not UTF-8 text')
                decoder.decode(chunk)
        decoder.decode(b'',final=True)
        return
    signatures = {
        'pdf': b'%PDF-' in prefix[:1024],
        'ppt': prefix.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'),
        'doc': prefix.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'),
        'png': prefix.startswith(b'\x89PNG\r\n\x1a\n'),
        'jpg': prefix.startswith(b'\xff\xd8\xff'), 'jpeg': prefix.startswith(b'\xff\xd8\xff'),
        'webp': prefix.startswith(b'RIFF') and prefix[8:12]==b'WEBP',
    }
    if kind in ('pptx','docx'):
        try:
            with ZipFile(path) as archive:
                infos=archive.infolist(); names=[i.filename for i in infos]
                required=('ppt/presentation.xml','ppt/_rels/presentation.xml.rels') if kind=='pptx' else ('word/document.xml',)
                if (len(infos)>20000 or sum(i.file_size for i in infos)>250_000_000
                    or len(names)!=len(set(names)) or '[Content_Types].xml' not in names
                    or any(n not in names for n in required)
                    or any('vbaproject' in n.casefold() or '\\' in n or '..' in n.split('/') for n in names)):
                    raise ValueError('Unsafe or invalid Office container')
                for name in ('[Content_Types].xml',*required):
                    if archive.getinfo(name).file_size>8_000_000: raise ValueError('Office XML exceeds limits')
                    raw=archive.read(name)
                    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('Unsafe Office XML')
                    ET.fromstring(raw)
                return
        except (BadZipFile,KeyError,ET.ParseError) as error:
            raise ValueError('Invalid Office container') from error
    if not signatures.get(kind,False): raise ValueError('File does not match its format')
