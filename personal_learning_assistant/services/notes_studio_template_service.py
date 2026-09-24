"""Read-only academic template registry for Phase 7.5.15.4.

Templates are deterministic Markdown scaffolds, not a storage format. This
module does not write notes, touch the vault, invoke AI, or persist state.
"""
from __future__ import annotations

from typing import Iterable

from markupsafe import Markup, escape

from personal_learning_assistant.domain.notes_studio_template_models import (
    NoteTemplate,
    NoteTemplateSection,
)
from personal_learning_assistant.services.obsidian_markdown_renderer import (
    render_markdown,
)


class NotesStudioTemplateNotFoundError(LookupError):
    """The requested academic template does not exist."""


def _section(heading: str, guidance: str) -> NoteTemplateSection:
    return NoteTemplateSection(heading=heading, guidance=guidance)


_TEMPLATES = (
    NoteTemplate(
        template_id="concept",
        name="Concept Note",
        note_type="concept",
        description="Build deep understanding of one idea from intuition to examples.",
        best_for="Theory, definitions, mechanisms, derivations, and conceptual revision.",
        sections=(
            _section("Key Points", "[Add 2–5 concise points you should remember.]"),
            _section("Intuition", "[Explain the idea in simple words before formal details.]"),
            _section("Core Explanation", "[Write the definition, reasoning, derivation, or mechanism.]"),
            _section("Visual", "[Add or describe a useful diagram, flowchart, or concept map.]"),
            _section("Example", "[Work through one clear example.]"),
            _section("Common Mistakes", "[List misconceptions, traps, or typical errors.]"),
            _section("Summary", "[Compress the concept into a short revision summary.]"),
            _section("Related Notes", "[List related concepts or Obsidian note links.]"),
        ),
    ),
    NoteTemplate(
        template_id="lecture",
        name="Lecture Note",
        note_type="lecture",
        description="Capture one class, lecture, or video in a structured study record.",
        best_for="Classroom teaching, MIT/YouTube lectures, and source-based study sessions.",
        sections=(
            _section(
                "Lecture Details",
                "Date: [YYYY-MM-DD]\n\nSource: [Class / faculty / lecture / video / chapter]",
            ),
            _section("Topics Covered", "[List the main topics covered in this lecture.]"),
            _section("Notes", "[Write the main explanations, derivations, and examples.]"),
            _section("Diagrams", "[Add or describe diagrams, figures, or board work.]"),
            _section("Questions / Doubts", "[Record unresolved questions to revisit.]"),
            _section("Takeaways", "[Write the most important points to retain.]"),
        ),
    ),
    NoteTemplate(
        template_id="revision",
        name="Revision Note",
        note_type="revision",
        description="Compress a topic into a fast, exam-oriented revision sheet.",
        best_for="Quiz, mid-sem, end-sem, and spaced revision before an assessment.",
        sections=(
            _section("Must Remember", "[List the highest-priority ideas or results.]"),
            _section("Formulas / Facts", "[Collect formulas, definitions, conditions, and facts.]"),
            _section("Common Traps", "[List common mistakes and confusing cases.]"),
            _section("Quick Examples", "[Add short examples that trigger recall.]"),
            _section("Self-Test", "[Write questions you should answer without looking at the note.]"),
        ),
    ),
    NoteTemplate(
        template_id="formula-sheet",
        name="Formula Sheet",
        note_type="formula_sheet",
        description="Keep formulas and their conditions compact, searchable, and usable.",
        best_for="Mathematics, physics, chemistry, data science, and calculation-heavy topics.",
        sections=(
            _section("Definitions", "[List the symbols and definitions needed to use the formulas.]"),
            _section("Formulas", "[Write the formulas clearly, one logical group at a time.]"),
            _section("Conditions", "[State assumptions, domains, units, or validity conditions.]"),
            _section("Compact Examples", "[Add minimal examples showing when each formula is used.]"),
        ),
    ),
    NoteTemplate(
        template_id="problem-solving",
        name="Problem-Solving Note",
        note_type="problem_solving",
        description="Record how to attack, solve, verify, and improve a representative problem.",
        best_for="Worked problems, PYQs, coding logic, derivations, and difficult exercises.",
        sections=(
            _section("Problem", "[State the problem clearly, including given data and goal.]"),
            _section("Concepts Needed", "[List the concepts, theorems, or tools required.]"),
            _section("Approach", "[Explain the strategy before doing the detailed work.]"),
            _section("Working", "[Show the reasoning, calculations, code logic, or derivation.]"),
            _section("Solution", "[State the final result clearly and verify it where possible.]"),
            _section("Mistakes", "[Record wrong turns, hidden assumptions, or errors to avoid.]"),
            _section("Alternative Method", "[Add another valid method or a shorter approach if known.]"),
        ),
    ),
)


def _template_markdown(template: NoteTemplate) -> str:
    lines = ["# {}".format(template.name), ""]
    for section in template.sections:
        lines.extend(
            [
                "## {}".format(section.heading),
                "",
                section.guidance,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _summary(template: NoteTemplate) -> dict:
    return {
        "id": template.template_id,
        "name": template.name,
        "note_type": template.note_type,
        "description": template.description,
        "best_for": template.best_for,
        "section_count": len(template.sections),
        "section_names": [section.heading for section in template.sections],
    }


class NotesStudioTemplateService:
    """Expose deterministic academic template metadata and safe previews."""

    def __init__(self, *, renderer=render_markdown):
        self._renderer = renderer

    def list_templates(self):
        return [_summary(template) for template in _TEMPLATES]

    def template_view(self, template_id):
        requested = str(template_id or "").strip()
        template = next(
            (item for item in _TEMPLATES if item.template_id == requested),
            None,
        )
        if template is None:
            raise NotesStudioTemplateNotFoundError("Template not found.")

        markdown = _template_markdown(template)
        try:
            rendered = self._renderer(markdown, note_route="/notes/note")
            if not isinstance(rendered, Markup):
                rendered = Markup(escape(str(rendered)))
        except Exception:
            rendered = Markup(
                '<pre class="template-render-fallback">{}</pre>'
            ).format(escape(markdown))

        view = _summary(template)
        view.update(
            {
                "defaults": {
                    "note_type": template.note_type,
                    "revision_status": template.revision_status,
                },
                "sections": [
                    {
                        "heading": section.heading,
                        "guidance": section.guidance,
                    }
                    for section in template.sections
                ],
                "markdown": markdown,
                "rendered_preview": rendered,
            }
        )
        return view


def build_notes_studio_template_service() -> NotesStudioTemplateService:
    return NotesStudioTemplateService()
