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
    knowledge_search_menu,
    preview_document
)


def about():
    print("\n" + "=" * 55)
    print("      PERSONAL AI LEARNING CHATBOT")
    print("               Version 1.1")
    print("=" * 55)

    print("\n👨‍💻 Developer : Anand Priyadarsi")

    print("\n🎯 Purpose")
    print("This chatbot helps me organize my learning")
    print("journey by managing notes, learning")
    print("resources, academic documents, and study progress.")

    print("\n✨ Features")
    print("✔ Notes Manager")
    print("✔ Learning Resources Manager")
    print("✔ Learning Dashboard")
    print("✔ Knowledge Library")
    print("✔ Markdown / Text / PDF Support")
    print("✔ Knowledge Search")
    print("✔ JSON Storage")
    print("✔ Backup & Restore")
    print("✔ Export System")

    print("\n🚀 Future Version")
    print("• AI Integration")
    print("• Semantic Search / RAG")
    print("• Quiz Generator")
    print("• YouTube Transcript Analysis")
    print("• Deeper Obsidian Integration")

    print("\nRelease Version : v1.1")

    print("\nThank you for using my project!")
    print("=" * 55)


def show_menu():
    print("\n" + "=" * 55)
    print("🤖      PERSONAL AI LEARNING CHATBOT v1.1")
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
    print("16. Search Knowledge")
    print("17. Preview Document")

    print("\n🤖 AI")
    print("18. Ask AI (Coming Soon)")

    print("\nℹ️ Information")
    print("19. About")
    print("20. Exit")

    print("=" * 55)


def run_chatbot():
    print("=" * 55)
    print("🤖 Welcome to Personal AI Learning Chatbot")
    print("Version : 1.1")
    print("Developer : Anand Priyadarsi")
    print("=" * 55)

    while True:
        show_menu()

        choice = input("\nEnter your choice (1-20): ").strip()

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
            knowledge_search_menu()

        elif choice == "17":
            preview_document()

        elif choice == "18":
            print("\n🤖 AI Integration Coming Soon!")

        elif choice == "19":
            about()

        elif choice == "20":
            print("\n👋 Thank you for using Personal AI Learning Chatbot!")
            print("Goodbye, Anand!")
            break

        else:
            print("\n❌ Invalid choice. Please enter a number from 1 to 20.")


if __name__ == "__main__":
    run_chatbot()
