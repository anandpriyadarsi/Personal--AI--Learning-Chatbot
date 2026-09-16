"""Versioned local source extractors for Phase 5.6."""
from __future__ import annotations
import io
import re
import zipfile
from pathlib import PurePosixPath
from typing import Callable, Optional, Sequence, Tuple
from xml.etree import ElementTree
from personal_learning_assistant.domain.ingestion_models import ExtractedUnit

class ExtractionError(RuntimeError):
    pass
class UnsupportedExtractionError(ExtractionError):
    pass
class EmptyExtractionError(ExtractionError):
    pass

def _decode_utf8(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ExtractionError("source is not valid UTF-8") from error

def _normal_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")

class TextExtractor:
    name = "text"
    version = "text-v1"
    extensions = {".txt"}
    def extract(self, raw: bytes, *, source_name: str) -> Tuple[ExtractedUnit, ...]:
        text = _normal_text(_decode_utf8(raw)).strip()
        if not text:
            raise EmptyExtractionError("text source contains no extractable text")
        return (ExtractedUnit(text=text, kind="text", locator={"source": source_name}),)

class MarkdownExtractor:
    name = "markdown"
    version = "markdown-v1"
    extensions = {".md"}
    _heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    @staticmethod
    def _body_lines(text: str):
        lines = _normal_text(text).split("\n")
        if lines and lines[0].lstrip("\ufeff").strip() == "---":
            for index in range(1, len(lines)):
                if lines[index].strip() in ("---", "..."):
                    return lines[index + 1:]
        return lines
    def extract(self, raw: bytes, *, source_name: str) -> Tuple[ExtractedUnit, ...]:
        lines = self._body_lines(_decode_utf8(raw))
        sections = []
        heading_stack = []
        current = []
        current_path = ""
        in_fence = False
        fence_marker = ""
        def flush():
            text = "\n".join(current).strip()
            if text:
                sections.append(ExtractedUnit(text=text, kind="markdown", section_path=current_path, locator={"source": source_name, "section": current_path}))
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                current.append(line)
                continue
            match = None if in_fence else self._heading.match(line)
            if match:
                flush()
                current = [line]
                level = len(match.group(1))
                title = match.group(2).strip()
                heading_stack = heading_stack[:level - 1]
                while len(heading_stack) < level - 1:
                    heading_stack.append("")
                heading_stack.append(title)
                current_path = " > ".join(item for item in heading_stack if item)
            else:
                current.append(line)
        flush()
        if not sections:
            text = "\n".join(lines).strip()
            if text:
                sections.append(ExtractedUnit(text=text, kind="markdown", locator={"source": source_name, "section": ""}))
        if not sections:
            raise EmptyExtractionError("Markdown source contains no extractable text")
        return tuple(sections)

_TIMESTAMP = re.compile(r"(?P<a>\d{1,2}:)?(?P<b>\d{1,2}):(?P<c>\d{2})[,.](?P<ms>\d{3})")
def _milliseconds(value: str) -> int:
    match = _TIMESTAMP.search(value.strip())
    if not match:
        raise ExtractionError("invalid transcript timestamp: {}".format(value))
    if match.group("a"):
        hours = int(match.group("a")[:-1]); minutes = int(match.group("b")); seconds = int(match.group("c"))
    else:
        hours = 0; minutes = int(match.group("b")); seconds = int(match.group("c"))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + int(match.group("ms"))

class TranscriptExtractor:
    name = "transcript"
    version = "transcript-v1"
    extensions = {".srt", ".vtt"}
    def extract(self, raw: bytes, *, source_name: str) -> Tuple[ExtractedUnit, ...]:
        text = _normal_text(_decode_utf8(raw)).strip()
        if text.startswith("WEBVTT"):
            text = text[len("WEBVTT"):].lstrip("\n")
        units = []
        for block in re.split(r"\n\s*\n", text):
            lines = [line.rstrip() for line in block.split("\n") if line.strip()]
            timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
            if timing_index is None:
                continue
            start_text, end_text = [part.strip() for part in lines[timing_index].split("-->", 1)]
            start_ms = _milliseconds(start_text); end_ms = _milliseconds(end_text.split()[0])
            if end_ms < start_ms:
                raise ExtractionError("transcript cue end precedes start")
            cue_text = "\n".join(lines[timing_index + 1:]).strip()
            if cue_text:
                units.append(ExtractedUnit(text=cue_text, kind="transcript", timestamp_start_ms=start_ms, timestamp_end_ms=end_ms, locator={"source": source_name, "timestamp_start_ms": start_ms, "timestamp_end_ms": end_ms}))
        if not units:
            raise EmptyExtractionError("transcript contains no extractable cues")
        return tuple(units)

class PPTXExtractor:
    name = "pptx"
    version = "pptx-v1"
    extensions = {".pptx"}
    _slide_name = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
    def extract(self, raw: bytes, *, source_name: str) -> Tuple[ExtractedUnit, ...]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw), "r")
        except zipfile.BadZipFile as error:
            raise ExtractionError("PPTX is not a valid ZIP package") from error
        units = []
        with archive:
            slides = []
            for name in archive.namelist():
                match = self._slide_name.match(name)
                if match:
                    slides.append((int(match.group(1)), name))
            for slide_number, name in sorted(slides):
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError as error:
                    raise ExtractionError("PPTX slide XML is malformed at slide {}".format(slide_number)) from error
                texts = [(node.text or "").strip() for node in root.findall(".//{*}t") if (node.text or "").strip()]
                if texts:
                    title = texts[0]
                    units.append(ExtractedUnit(text="\n".join(texts), kind="pptx", section_path=title, slide_number=slide_number, locator={"source": source_name, "slide": slide_number, "section": title}))
        if not units:
            raise EmptyExtractionError("PPTX contains no extractable slide text")
        return tuple(units)

class PDFExtractor:
    name = "pdf"
    version = "pdf-v1"
    extensions = {".pdf"}
    def __init__(self, reader_factory: Optional[Callable] = None):
        self._reader_factory = reader_factory
    def _reader(self, stream):
        if self._reader_factory is not None:
            return self._reader_factory(stream)
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise ExtractionError("pypdf is required for PDF extraction") from error
        return PdfReader(stream)
    def extract(self, raw: bytes, *, source_name: str) -> Tuple[ExtractedUnit, ...]:
        try:
            reader = self._reader(io.BytesIO(raw))
        except ExtractionError:
            raise
        except Exception as error:
            raise ExtractionError("PDF could not be opened") from error
        units = []
        for page_number, page in enumerate(reader.pages, 1):
            try:
                text = _normal_text(page.extract_text() or "").strip()
            except Exception as error:
                raise ExtractionError("PDF text extraction failed on page {}".format(page_number)) from error
            if text:
                units.append(ExtractedUnit(text=text, kind="pdf", page_number=page_number, locator={"source": source_name, "page": page_number}))
        if not units:
            raise EmptyExtractionError("PDF contains no extractable text; OCR is not performed in Phase 5.6")
        return tuple(units)

class ExtractorRegistry:
    def __init__(self, extractors: Optional[Sequence[object]] = None):
        self.extractors = tuple(extractors or (MarkdownExtractor(), TextExtractor(), TranscriptExtractor(), PPTXExtractor(), PDFExtractor()))
    def select(self, *, source_name: str, kind: str = "", mime_type: str = ""):
        extension = PurePosixPath(str(source_name).replace("\\", "/")).suffix.casefold()
        for extractor in self.extractors:
            if extension in extractor.extensions:
                return extractor
        return None
