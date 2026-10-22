"""Standalone PDF parser process; stdin/stdout only, no application owner access."""
import hashlib
import io
import json
import sys


def extract(source):
    from pypdf import PdfReader
    pdf=PdfReader(io.BytesIO(source),strict=True)
    if pdf.is_encrypted or not 1<=len(pdf.pages)<=50:
        raise ValueError('Unsupported PDF')
    pages=[];total=0
    for number,page in enumerate(pdf.pages,1):
        text=page.extract_text() or ''
        total+=len(text)
        if len(text)>30_000 or total>100_000:
            raise ValueError('Extraction bound exceeded')
        flags=['Text extraction cannot certify equations, reading order, diagrams, tables or visual fidelity.',
            'Figures and speaker notes are not converted. Compare the preserved original.']
        if not text.strip():flags.append('No extractable text; OCR or manual review is required.')
        pages.append({'page':number,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'semantic_confidence':'unknown','review_flags':flags})
    return {'schema':'anvaya.note-draft.v1','source_sha256':hashlib.sha256(source).hexdigest(),
        'method':'pypdf.extract_text; unchanged extracted text in original page order',
        'parser_version':__import__('pypdf').__version__,
        'review_status':'needs_review','publishable':False,'pages':pages,
        'isolation':'separate process, 12s timeout; not an OS security sandbox',
        'next_step':'Human compare/re-author → existing preflight → explicit stage → explicit owner publication. This preview has no publication action.'}


def main():
    if sys.platform!='win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(384*1024*1024,384*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(8,8))
    source=sys.stdin.buffer.read(8_000_001)
    if not 0<len(source)<=8_000_000 or not source.startswith(b'%PDF-'):
        raise ValueError('Invalid PDF')
    sys.stdout.write(json.dumps(extract(source),ensure_ascii=True))

if __name__=='__main__':
    main()
