"""Read-only Learning Studio course presentation and cautious Chemistry grouping.

Course IDs, catalogue records, topic identity and learning packages are never rewritten.
These visual templates are guidance, not extra academic topics or evidence of learning.
"""

CHEMISTRY_SECTIONS = (
    {"id": "green-chemistry", "title": "Green Chemistry", "kicker": "Principles & sustainability",
     "description": "Explore greener reactions, atom economy, E-factor and sustainable design.",
     "icon": "leaf", "workflow": ("Understand the 12 principles", "Work through atom economy and E-factor", "Check misconceptions before revision")},
    {"id": "spectroscopy", "title": "Spectroscopy", "kicker": "Methods & interpretation",
     "description": "Study fundamentals, instrument diagrams and interpretation of spectra.",
     "icon": "activity", "workflow": ("Understand the underlying transitions", "Study instrument components and diagrams", "Compare spectra and practise interpretation")},
    {"id": "lab", "title": "Lab", "kicker": "Experiments & records",
     "description": "Keep experimental procedures, observations, calculations and viva preparation together.",
     "icon": "flask-conical", "workflow": ("Read the experimental aim and method", "Check observations and calculations", "Prepare precautions and viva answers")},
    {"id": "other", "title": "Other Chemistry", "kicker": "Unclassified material",
     "description": "Material not safely recognised by its existing title or topic remains visible here for review.",
     "icon": "book-open", "workflow": ("Check the original topic name", "Review the authored source", "Use the correct section after review")},
)

SUBJECT_TEMPLATES = {
    "MA103N": {"title": "Linear Algebra", "eyebrow": "Reason through the mathematics",
        "description": "From systems of equations to vector spaces: understand the proof, solve examples and revisit mistakes.",
        "pathways": ("Concepts & definitions", "Worked problems", "Mistakes & exam revision")},
    "UC100N": {"title": "Data Science and AI", "eyebrow": "Learn by coding",
        "description": "Move from Python and data handling to reproducible analysis, independent coding and viva preparation.",
        "pathways": ("Concepts & operations", "Code walkthroughs & labs", "Practice & viva recall")},
    "CY100N": {"title": "Chemistry", "eyebrow": "Theory, spectroscopy and experiments",
        "description": "One Chemistry home, with dedicated Green Chemistry, Spectroscopy and Lab learning templates.",
        "pathways": ("Green Chemistry", "Spectroscopy", "Lab")},
    "DE100N": {"title": "Design Thinking and Prototyping", "eyebrow": "Ideas into working prototypes",
        "description": "Connect the problem statement, design decisions, prototype evidence and reflections.",
        "pathways": ("Understand the problem", "Prototype & test", "Reflect & present")},
    "UC103N": {"title": "Indian Knowledge System", "eyebrow": "Read, compare and explain",
        "description": "Organise original readings, philosophical ideas, comparisons and recall questions.",
        "pathways": ("Source readings", "Key ideas & comparisons", "Active recall & revision")},
}


def subject_template(course):
    """A view-only title; never changes course.name or any canonical mapping."""
    code = str(course.get("code") or "").upper().strip()
    template = SUBJECT_TEMPLATES.get(code)
    if template is not None:
        return dict(template, code=code, chemistry=code == "CY100N")
    return {"title": course.get("name") or "Course workspace",
            "code": code, "chemistry": False,
            "eyebrow": "Build understanding from the source",
            "description": "Keep authored lectures, worked examples, questions and revision together.",
            "pathways": ("Lecture notes & resources", "Concept practice", "Exam revision")}


# Conservative, reproducible metadata-only suggestions, not canonical topic attribution.
# Lab takes priority for a module explicitly described as a spectroscopy experiment.
_CHEMISTRY_TEXT = ("lower(coalesce(m.topic_name,'') || ' ' || "
                   "coalesce(m.title,'') || ' ' || coalesce(m.unit,''))")
_CHEMISTRY_AREA_SQL = (
    "CASE "
    "WHEN instr(" + _CHEMISTRY_TEXT + ", ' laboratory')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", ' lab')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'practical')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'experiment')>0 THEN 'lab' "
    "WHEN instr(" + _CHEMISTRY_TEXT + ", 'spectroscop')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'spectra')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'infrared')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'uv-visible')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'atomic absorption')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'raman')>0 THEN 'spectroscopy' "
    "WHEN instr(" + _CHEMISTRY_TEXT + ", 'green chem')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'atom economy')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'e-factor')>0 OR "
    "instr(" + _CHEMISTRY_TEXT + ", 'e factor')>0 THEN 'green-chemistry' "
    "ELSE 'other' END"
)


def chemistry_area_sql():
    return _CHEMISTRY_AREA_SQL


def chemistry_section(section_id):
    return next((section for section in CHEMISTRY_SECTIONS if section["id"] == section_id), None)
