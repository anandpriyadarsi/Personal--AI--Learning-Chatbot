"""PDF resource cues; no OCR, visual interpretation or complete extraction claim."""
import io
from pypdf import PdfReader
from .validation import MAX_SOURCE,require

def pdf_features(source):
    require(isinstance(source,bytes) and len(source)<=MAX_SOURCE,'Invalid original PDF bytes.')
    pdf=PdfReader(io.BytesIO(source),strict=True)
    require(not pdf.is_encrypted and len(pdf.pages)<=500,'Unsupported PDF.')
    pages=[]
    for number,page in enumerate(pdf.pages,1):
        resources=page.get('/Resources');resources=resources.get_object() if resources is not None else {}
        objects=resources.get('/XObject');objects=objects.get_object() if objects is not None else {}
        counts={'/Image':0,'/Form':0}
        for obj in objects.values():
            subtype=obj.get_object().get('/Subtype')
            if subtype in counts:counts[subtype]+=1
        pages.append({'page':number,'raster_resources':counts['/Image'],'form_resources':counts['/Form'],
                      'text_available':bool((page.extract_text() or '').strip())})
    return {'pages':pages,'semantic_certification':False,'vector_formula_speaker_notes':'unsupported / needs review',
        'limitation':'Direct PDF resources only; unused resources may be counted. Nested drawings and formula meaning are not inspected. PPTX ingestion is unsupported.'}
