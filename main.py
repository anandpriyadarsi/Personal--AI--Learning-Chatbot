"""Command-line entry point for Personal AI Learning Assistant V13."""

from importlib import import_module


class FeatureLoadError(RuntimeError):
    """Raised when a lazily loaded feature cannot be imported."""


def _load_callable(module_name, function_name):
    """
    Import one feature only when the user selects it.

    This keeps main.py startup independent from optional semantic,
    RAG, vision, YouTube, and document dependencies.
    """
    try:
        module = import_module(
            module_name
        )
    except ImportError as error:
        raise FeatureLoadError(
            f"{module_name}.{function_name} could not be loaded: {error}"
        ) from error

    try:
        return getattr(
            module,
            function_name
        )
    except AttributeError as error:
        raise FeatureLoadError(
            f"{module_name} does not provide {function_name}."
        ) from error


def _run_feature(module_name, function_name):
    try:
        function = _load_callable(
            module_name,
            function_name
        )
    except FeatureLoadError as error:
        print(
            "\nFeature unavailable."
        )
        print(error)
        return None

    return function()


FEATURE_ACTIONS = {
    "1": ("dashboard", "show_dashboard"),
    "2": ("notes", "view_notes"),
    "3": ("notes", "add_note"),
    "4": ("notes", "search_notes"),
    "5": ("notes", "count_notes"),
    "6": ("resources", "view_resources"),
    "7": ("resources", "add_resource"),
    "8": ("resources", "search_resources"),
    "9": ("resources", "count_resources"),
    "10": ("resources", "update_status"),
    "11": ("backup", "backup_database"),
    "12": ("backup", "restore_database"),
    "13": ("backup", "export_notes"),
    "14": ("backup", "export_resources"),
    "15": ("knowledge", "show_knowledge_library"),
    "17": ("knowledge", "preview_document"),
    "18": ("rag_answer", "rag_chat_loop"),
    "19": ("learning_memory", "memory_menu"),
    "20": ("obsidian_integration", "obsidian_menu"),
    "21": ("youtube_ingestion", "youtube_menu"),
    "22": ("youtube_analysis", "lecture_analysis_menu"),
    "23": ("course_manager", "course_manager_menu"),
    "24": ("rag_answer", "course_rag_chat_loop"),
    "25": ("academic_progress", "academic_progress_menu"),
    "26": ("weekly_planner", "weekly_planner_menu"),
    "27": ("multi_course_planner", "multi_course_planner_menu"),
    "28": ("assignment_exam_assistant", "assignment_exam_menu"),
    "29": (
        "assessment_question_workspace",
        "assessment_question_workspace_menu"
    ),
    "30": (
        "assignment_file_importer",
        "assignment_file_importer_menu"
    ),
    "31": (
        "automatic_topic_mapping",
        "automatic_topic_mapping_menu"
    ),
    "32": (
        "assessment_performance",
        "performance_engine_menu"
    ),
    "33": (
        "intelligent_study_planner",
        "intelligent_study_planner_menu"
    ),
    "34": (
        "academic_intelligence_dashboard",
        "academic_intelligence_dashboard_menu"
    ),
    "35": (
        "semester_grade_intelligence",
        "semester_grade_intelligence_menu"
    ),
    "36": (
        "academic_calendar_planner",
        "academic_calendar_menu"
    ),
    "37": (
        "daily_academic_brief",
        "daily_brief_menu"
    ),
    "38": (
        "personal_academic_agent",
        "personal_academic_agent_menu"
    ),
}


def about():
    print("\n" + "=" * 55)
    print("      PERSONAL AI LEARNING CHATBOT")
    print("          Version 3.0.0 (V13)")
    print("=" * 55)

    print("\n👨‍💻 Developer : Anand Priyadarsi")

    print("\n🎯 Purpose")
    print("This chatbot helps me organize and understand")
    print("my learning using notes, resources, PDFs,")
    print("academic documents, and retrieval-based AI.")

    print("\n✨ Features")
    print("✔ Notes Manager")
    print("✔ Learning Resources Manager")
    print("✔ Learning Dashboard")
    print("✔ Knowledge Library")
    print("✔ Markdown / Text / PDF Support")
    print("✔ Hybrid Knowledge Retrieval")
    print("✔ Semantic Search")
    print("✔ RAG Academic Answer Generation")
    print("✔ Source-grounded Answers")
    print("✔ Conversation-aware Tutoring")
    print("✔ Academic Tutor Modes")
    print("✔ Persistent Learning Memory")
    print("✔ Course Catalogue and Active Course")
    print("✔ Course-wise Topic Progress")
    print("✔ Course-tagged Knowledge Sources")
    print("✔ Strict Course-focused Retrieval")
    print("✔ Course-aware Revision and Next-step Guidance")
    print("✔ Course Planner + Academic Progress Engine")
    print("✔ Priority Topic Ranking + Weekly Progress Trends")
    print("✔ Intelligent 7-Day Course Study Planner")
    print("✔ Balanced Multi-Course Weekly Planner")
    print("✔ Assignment & Exam Tracking")
    print("✔ Deadline-Aware Preparation Plans")
    print("✔ Source-Grounded Assessment Preparation")
    print("✔ Question-by-Question Assessment Workspace")
    print("✔ Source-Grounded Help for Individual Questions")
    print("✔ Assignment Question-Sheet File Import")
    print("✔ Question-to-Source Page Mapping")
    print("✔ Automatic Assessment Topic Mapping")
    print("✔ Confidence-Based Topic Suggestions")
    print("✔ Assessment Performance Engine")
    print("✔ Topic Evidence + Mistake Tracking")
    print("✔ Intelligent Daily Study Planning")
    print("✔ Deadline + Progress + Performance Prioritization")
    print("✔ Intelligent 7-Day Study Planning")
    print("✔ Assessment Weightage + Course Credit Tracking")
    print("✔ Math-Aware PDF / Matrix / Table Ingestion")
    print("✔ Math-Preserving Retrieval Chunks")
    print("✔ Vision Math Reader for Scanned PDFs")
    print("✔ Image-to-LaTeX Matrix / Equation Transcription")
    print("✔ Unified Academic Intelligence Dashboard")
    print("✔ Academic Risk + Priority Overview")
    print("✔ Daily Academic Brief")
    print("✔ Semester Grade + SGPA Intelligence")
    print("✔ Course Score Projection + Target Analysis")
    print("✔ Academic Calendar + Deadline Planner")
    print("✔ Deadline-Aware Study Block Scheduling")
    print("✔ Academic Overload Detection")
    print("✔ Daily Academic Brief 2.0")
    print("✔ One-Command Best Next Action")
    print("✔ Natural-Language Personal Academic Agent")
    print("✔ Intent Routing Across Academic Engines")
    print("✔ Automatic Knowledge Re-indexing")
    print("✔ Direct Obsidian Vault Integration")
    print("✔ YouTube Lecture Transcript Integration")
    print("✔ YouTube Lecture Analysis")
    print("✔ Backup & Restore")
    print("✔ Export System")

    print("\nRelease Version : v3.0.0 - Personal Academic Agent")

    print("\nThank you for using my project!")
    print("=" * 55)


def search_hybrid_knowledge():
    print("\nLoading semantic index...")

    try:
        load_semantic_index = _load_callable(
            "semantic_retrieval",
            "load_semantic_index"
        )
        hybrid_search_loop = _load_callable(
            "hybrid_retrieval",
            "hybrid_search_loop"
        )
    except FeatureLoadError as error:
        print("\nHybrid search is unavailable.")
        print(error)
        return

    semantic_chunks = load_semantic_index()

    if semantic_chunks is None:
        print("\n❌ No saved semantic index found.")
        print(
            "Run semantic_retrieval.py and "
            "build the index first."
        )
        return

    print(
        "\n✅ Hybrid Knowledge Retrieval ready."
    )

    hybrid_search_loop(
        semantic_chunks
    )


def show_menu():
    print("\n" + "=" * 55)
    print("🤖      PERSONAL AI LEARNING CHATBOT v3.0.0")
    print("=" * 55)

    print("\n📊 Dashboard")
    print("1.  Learning Dashboard")

    print("\n📝 Notes")
    print("2.  View Notes")
    print("3.  Add Note")
    print("4.  Search Notes")
    print("5.  Count Notes")

    print("\n📚 Learning Resources")
    print("6.  View Resources")
    print("7.  Add Resource")
    print("8.  Search Resources")
    print("9.  Count Resources")
    print("10. Update Resource Status")

    print("\n💾 Data Management")
    print("11. Backup Database")
    print("12. Restore Database")
    print("13. Export Notes")
    print("14. Export Resources")

    print("\n🧠 Knowledge Library")
    print("15. View Knowledge Library")
    print("16. Search Knowledge (Hybrid V3.5)")
    print("17. Preview Document")

    print("\n🤖 AI")
    print("18. Academic Tutor Modes (RAG V5)")
    print("19. Persistent Learning Memory")
    print("20. Obsidian Vault Integration")
    print("21. YouTube Learning Integration")
    print("22. YouTube Lecture Analysis")

    print("\n🎓 Course-Aware V8")
    print("23. Course Manager")
    print("24. Course-Aware Academic Assistant")

    print("\n📈 Academic Progress V9")
    print("25. Course Planner + Academic Progress Engine")
    print("26. Intelligent Weekly Planner")
    print("27. Multi-Course Weekly Planner")
    print("28. Assignment & Exam Assistant")
    print("29. Assessment Question Workspace")
    print("30. Assignment File Importer")
    print("31. Automatic Topic Mapping")
    print("32. Assessment Performance Engine")
    print("33. Intelligent Study Planner")
    print("34. Academic Intelligence Dashboard")
    print("35. Semester Grade & CGPA Intelligence")
    print("36. Academic Calendar + Deadline Planner")
    print("37. Daily Academic Brief 2.0")
    print("38. Personal Academic Agent")

    print("\nℹ️ Information")
    print("39. About")
    print("40. Exit")

    print("=" * 55)


def run_chatbot():
    print("=" * 55)
    print("🤖 Welcome to Personal AI Learning Chatbot")
    print("Version : 3.0.0 (Personal Academic Agent)")
    print("Developer : Anand Priyadarsi")
    print("=" * 55)

    while True:
        show_menu()

        choice = input(
            "\nEnter your choice (1-40): "
        ).strip()

        if choice in FEATURE_ACTIONS:
            module_name, function_name = (
                FEATURE_ACTIONS[choice]
            )
            _run_feature(
                module_name,
                function_name
            )

        elif choice == "16":
            search_hybrid_knowledge()

        elif choice == "39":
            about()

        elif choice == "40":
            print(
                "\n👋 Thank you for using "
                "Personal AI Learning Chatbot!"
            )
            print("Goodbye, Anand!")
            break

        else:
            print(
                "\n❌ Invalid choice. "
                "Please enter a number from 1 to 40."
            )


if __name__ == "__main__":
    run_chatbot()
