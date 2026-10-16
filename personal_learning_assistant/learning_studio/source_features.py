"""PDF resource cues; no OCR, visual interpretation or complete extraction claim."""
import io
from pypdf import PdfReader
from .validation import MAX_SOURCE,PackageError,require

def pdf_features(source):
    require(isinstance(source,bytes) and 0<len(source)<=MAX_SOURCE,'Invalid original PDF bytes.')
    try:
        pdf=PdfReader(io.BytesIO(source),strict=True)
        require(not pdf.is_encrypted and len(pdf.pages)<=500,'Unsupported PDF.')
        pages=[]
        for number,page in enumerate(pdf.pages,1):
            resources=page.get('/Resources')
            resources=resources.get_object() if resources is not None else {}
            require(isinstance(resources,dict),'Malformed PDF page resources; source review required.')
            objects=resources.get('/XObject')
            objects=objects.get_object() if objects is not None else {}
            require(isinstance(objects,dict),'Malformed PDF XObject resources; source review required.')
            counts={'/Image':0,'/Form':0}
            for obj in objects.values():
                entry=obj.get_object()
                require(isinstance(entry,dict),'Malformed PDF XObject entry; source review required.')
                subtype=entry.get('/Subtype')
                if subtype in counts:counts[subtype]+=1
            pages.append({'page':number,'raster_resources':counts['/Image'],'form_resources':counts['/Form'],
                          'text_available':bool((page.extract_text() or '').strip())})
    except PackageError:
        raise
    except Exception as exc:
        raise PackageError('PDF resources could not be safely inspected; source review required.') from exc
    return {'pages':pages,'semantic_certification':False,'vector_formula_speaker_notes':'unsupported / needs review',
        'limitation':'Direct PDF resources only; unused resources may be counted. Nested drawings and formula meaning are not inspected. PPTX ingestion is unsupported.'}
