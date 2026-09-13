"""Command-line entry point for Personal AI Learning Chatbot V8."""

from notes import add_note, view_notes, count_notes, search_notes
from resources import (
    add_resource,
    view_resources,
    search_resources,
    count_resources,
    update_status
)
from dashboard import show_dashboard
from backup import (
    backup_database,
    restore_database,
    export_notes,
    export_resources
)
from knowledge import (
    show_knowledge_library,
    preview_document
)
from semantic_retrieval import load_semantic_index
from hybrid_retrieval import hybrid_search_loop
from rag_answer import rag_chat_loop, course_rag_chat_loop
from learning_memory import memory_menu
from course_manager import course_manager_menu
from obsidian_integration import obsidian_menu
from youtube_ingestion import youtube_menu
from youtube_analysis import lecture_analysis_menu
from academic_progress import academic_progress_menu
from weekly_planner import weekly_planner_menu
from multi_course_planner import multi_course_planner_menu
from assignment_exam_assistant import assignment_exam_menu
from assessment_question_workspace import assessment_question_workspace_menu
from assignment_file_importer import assignment_file_importer_menu
from automatic_topic_mapping import automatic_topic_mapping_menu
from assessment_performance import performance_engine_menu
from intelligent_study_planner import intelligent_study_planner_menu
from academic_intelligence_dashboard import academic_intelligence_dashboard_menu
from semester_grade_intelligence import semester_grade_intelligence_menu
from academic_calendar_planner import academic_calendar_menu
from daily_academic_brief import daily_brief_menu
from personal_academic_agent import personal_academic_agent_menu


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

        if choice == "1":
            show_dashboard()

        elif choice == "2":
            view_notes()

        elif choice == "3":
            add_note()

        elif choice == "4":
            search_notes()

        elif choice == "5":
            count_notes()

        elif choice == "6":
            view_resources()

        elif choice == "7":
            add_resource()

        elif choice == "8":
            search_resources()

        elif choice == "9":
            count_resources()

        elif choice == "10":
            update_status()

        elif choice == "11":
            backup_database()

        elif choice == "12":
            restore_database()

        elif choice == "13":
            export_notes()

        elif choice == "14":
            export_resources()

        elif choice == "15":
            show_knowledge_library()

        elif choice == "16":
            search_hybrid_knowledge()

        elif choice == "17":
            preview_document()

        elif choice == "18":
            rag_chat_loop()

        elif choice == "19":
            memory_menu()

        elif choice == "20":
            obsidian_menu()

        elif choice == "21":
            youtube_menu()

        elif choice == "22":
            lecture_analysis_menu()

        elif choice == "23":
            course_manager_menu()

        elif choice == "24":
            course_rag_chat_loop()

        elif choice == "25":
            academic_progress_menu()

        elif choice == "26":
            weekly_planner_menu()

        elif choice == "27":
            multi_course_planner_menu()

        elif choice == "28":
            assignment_exam_menu()

        elif choice == "29":
            assessment_question_workspace_menu()

        elif choice == "30":
            assignment_file_importer_menu()

        elif choice == "31":
            automatic_topic_mapping_menu()

        elif choice == "32":
            performance_engine_menu()

        elif choice == "33":
            intelligent_study_planner_menu()

        elif choice == "34":
            academic_intelligence_dashboard_menu()

        elif choice == "35":
            semester_grade_intelligence_menu()

        elif choice == "36":
            academic_calendar_menu()

        elif choice == "37":
            daily_brief_menu()

        elif choice == "38":
            personal_academic_agent_menu()

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
