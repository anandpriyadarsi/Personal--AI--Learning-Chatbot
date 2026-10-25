"""A reader metadata request must not allocate its embedded source PDF."""
import io
import tracemalloc
from pypdf import PdfWriter
from .helpers import package, catalogue
from personal_learning_assistant.learning_studio.service import LearningStudioService


def test_metadata_reads_do_not_copy_pdf_blob(tmp_path):
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=612, height=792)
    writer.add_attachment('synthetic-padding.txt', b'x' * 4_000_000)
    buffer = io.BytesIO(); writer.write(buffer); raw = buffer.getvalue()
    service = LearningStudioService(tmp_path/'learning_studio.sqlite3',
        source_loader=lambda _: raw, catalogue_loader=catalogue)
    service.stage(package(raw)); service.publish('synthetic', 1)
    tracemalloc.start()
    try:
        result = service.module('synthetic', 1)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result['module_id'] == 'synthetic'
    assert peak < 1_000_000, f'Metadata read copied the PDF: {peak} bytes'
    assert service.source('synthetic', 1) == raw
