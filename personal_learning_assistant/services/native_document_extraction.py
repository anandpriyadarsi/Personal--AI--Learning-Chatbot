"""Bounded, local-only page/slide text extraction. Never rewrites an original."""
from __future__ import annotations
from pathlib import PurePosixPath
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import re
import shutil
import subprocess
import unicodedata

MAX_PAGES = 2500
MAX_TEXT = 12_000_000
MAX_XML = 8_000_000
MAX_DECODED_PAGE = 8_000_000
MAX_DECODED_TOTAL = 32_000_000


def normalize(value):
    value = unicodedata.normalize('NFKC', str(value)).casefold()
    return ' '.join(re.findall(r'[^\W_]+', value, re.UNICODE))


def ocr_available():
    if not shutil.which('tesseract'):
        return False
    try:
        import fitz  # Optional desktop renderer, not assumed on Android.
        return True
    except ImportError:
        return False


def extract_pages(path, kind, *, ocr=False, cancelled=lambda: False):
    if kind == 'ppt':
        return [], 'conversion_required', 'Legacy PPT: convert a copy to PPTX for content search. Original preserved.'
    if kind == 'pptx':
        pages = list(_slides(path, cancelled))
        return pages, ('ready' if any(t.strip() for _, t in pages) else 'unavailable'), 'PowerPoint slide text; image-only text is not indexed.'
    from pypdf import PdfReader, apply_configuration
    # Configuration is ContextVar scoped: never weaken other academic readers.
    # A file handle avoids PdfReader(path)'s whole-file BytesIO copy.
    with path.open('rb') as stream, apply_configuration(
            maximum_declared_stream_length=MAX_DECODED_PAGE,
            array_based_stream_maximum_output_length=MAX_DECODED_PAGE,
            zlib_maximum_output_length=MAX_DECODED_PAGE,
            lzw_maximum_output_length=MAX_DECODED_PAGE,
            run_length_maximum_output_length=MAX_DECODED_PAGE,
            jbig2_maximum_output_length=MAX_DECODED_PAGE,
            image_maximum_buffer_size=MAX_DECODED_PAGE,
            xform_maximum_invocations_per_extraction=200,
            page_tree_maximum_entries=MAX_PAGES*4):
        return _pdf_text(PdfReader(stream, strict=False), path, ocr, cancelled)


class _PDFBudget:
    """Charge each decoded text/form/font stream once across the whole PDF."""
    def __init__(self):
        self.seen, self.resources, self.total = set(), set(), 0

    def charge(self, value):
        from pypdf.generic import ArrayObject, StreamObject
        if value is None: return
        value = value.get_object()
        if isinstance(value, ArrayObject):
            for child in value: self.charge(child)
        elif isinstance(value, StreamObject) and id(value) not in self.seen:
            self.seen.add(id(value))
            data = value.get_data()
            self.total += len(data)
            if len(data)>MAX_DECODED_PAGE or self.total>MAX_DECODED_TOTAL:
                raise ValueError('PDF decoded-content resource limit exceeded')

    def inspect_resources(self, value, depth=0):
        from pypdf.generic import DictionaryObject
        if value is None: return
        value = value.get_object()
        if not isinstance(value,DictionaryObject) or id(value) in self.resources: return
        if depth>30 or len(self.resources)>5000:
            raise ValueError('PDF resource nesting limit exceeded')
        self.resources.add(id(value))
        fonts = value.get('/Font',{})
        if hasattr(fonts,'get_object'): fonts=fonts.get_object()
        for font in fonts.values():
            font=font.get_object()
            self.charge(font.get('/ToUnicode'))
        objects=value.get('/XObject',{})
        if hasattr(objects,'get_object'): objects=objects.get_object()
        for obj in objects.values():
            obj=obj.get_object()
            if obj.get('/Subtype')=='/Form':
                self.charge(obj)
                self.inspect_resources(obj.get('/Resources'),depth+1)


def _pdf_text(reader, path, ocr, cancelled):
    if reader.is_encrypted:
        return [], 'unavailable', 'Password-protected PDF: search unavailable. Original preserved.'
    if len(reader.pages) > MAX_PAGES:
        raise ValueError('Page limit exceeded')
    pages, blank, total = [], 0, 0
    renderer, budget = None, _PDFBudget()
    try:
        for number, page in enumerate(reader.pages, 1):
            if cancelled(): raise ValueError('Indexing cancelled')
            budget.charge(page.get('/Contents'))
            budget.inspect_resources(page.get('/Resources'))
            text = page.extract_text() or ''
            if not normalize(text):
                blank += 1
                if ocr:
                    if not ocr_available():
                        return [], 'ocr_required', 'OCR requires local Tesseract and PyMuPDF; no OCR was run.'
                    if len(reader.pages) > 100:
                        return [], 'ocr_required', 'Optional OCR is limited to 100 pages per document.'
                    if renderer is None:
                        import fitz
                        renderer = fitz.open(path)
                    p = renderer[number-1]
                    scale = min(2.0, 2200 / max(p.rect.width, p.rect.height))
                    image = p.get_pixmap(matrix=__import__('fitz').Matrix(scale, scale), alpha=False)
                    result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng'], input=image.tobytes('png'),
                        capture_output=True, check=True, timeout=45)
                    text = result.stdout.decode('utf-8', errors='replace')
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError('Text resource limit exceeded')
            pages.append((number, text))
    finally:
        if renderer is not None: renderer.close()
    if not any(normalize(text) for _, text in pages):
        return pages, 'ocr_required', 'No searchable text found. Scanned/image-only or blank PDF; optional OCR required.'
    if blank and not ocr:
        return pages, 'partial', f'Embedded text indexed. {blank} page(s) have no text; optional OCR required for those pages.'
    return pages, 'ready', ('Embedded text plus optional OCR (English); OCR may contain errors.' if ocr else 'Searchable PDF — embedded page text indexed.')


def _slides(path, cancelled):
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 20_000 or sum(i.file_size for i in members) > 250_000_000:
            raise ValueError('PowerPoint resource limit exceeded')
        if len({i.filename for i in members}) != len(members):
            raise ValueError('Duplicate archive members')
        def xml(name):
            info = archive.getinfo(name)
            if info.file_size > MAX_XML:
                raise ValueError('Slide XML resource limit exceeded')
            data = archive.read(info)
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError('Unsafe XML')
            return ET.fromstring(data)
        rels = {}
        for rel in xml('ppt/_rels/presentation.xml.rels'):
            target = rel.attrib.get('Target', '')
            if rel.attrib.get('TargetMode') == 'External':
                continue
            if target.startswith('/ppt/'):
                target = target[1:]
            else:
                target = 'ppt/' + target
            parts = PurePosixPath(target).parts
            if '..' in parts or '\\' in target or not target.startswith('ppt/slides/'):
                continue
            rels[rel.attrib.get('Id')] = target
        ns = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
              'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        ids = xml('ppt/presentation.xml').findall('./p:sldIdLst/p:sldId', ns)
        if len(ids) > MAX_PAGES:
            raise ValueError('Slide limit exceeded')
        total = 0
        for number, slide in enumerate(ids, 1):
            if cancelled(): raise ValueError('Indexing cancelled')
            rid = slide.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            if rid not in rels:
                raise ValueError('Missing slide relationship')
            root = xml(rels[rid])
            paragraphs = [''.join('\n' if t.tag == '{'+ns['a']+'}br' else t.text or ''
                for t in p.iter() if t.tag in ('{'+ns['a']+'}t','{'+ns['a']+'}br'))
                for p in root.findall('.//a:p', ns)]
            text = '\n'.join(paragraphs)
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError('Text resource limit exceeded')
            yield number, text
