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


def about():
    print("\n" + "=" * 55)
    print("      PERSONAL AI LEARNING CHATBOT")
    print("               Version 1.0")
    print("=" * 55)

    print("\n👨‍💻 Developer : Anand Priyadarsi")

    print("\n🎯 Purpose")
    print("This chatbot helps me organize my learning")
    print("journey by managing notes, learning")
    print("resources, and study progress.")

    print("\n✨ Features")
    print("✔ Notes Manager")
    print("✔ Learning Resources Manager")
    print("✔ Learning Dashboard")
    print("✔ JSON Storage")
    print("✔ Backup & Restore")
    print("✔ Export System")

    print("\n🚀 Future Version")
    print("• AI Integration")
    print("• Quiz Generator")
    print("• YouTube Summaries")
    print("• Second Brain Integration")

    print("\nRelease Version : v1.0")
    print("Release Date    : July 2026")

    print("\nThank you for using my project!")
    print("=" * 55)


def show_menu():
    print("\n" + "=" * 55)
    print("🤖      PERSONAL AI LEARNING CHATBOT v1.0")
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

    print("\n🤖 AI")
    print("15. Ask AI (Coming Soon)")

    print("\nℹ️ Information")
    print("16. About")
    print("17. Exit")

    print("=" * 55)


def run_chatbot():

    print("=" * 55)
    print("🤖 Welcome to Personal AI Learning Chatbot")
    print("Version : 1.0")
    print("Developer : Anand Priyadarsi")
    print("=" * 55)

    while True:

        show_menu()

        choice = input("\nEnter your choice (1-17): ")

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
            print("\n🤖 AI Integration Coming Soon!")

        elif choice == "16":
            about()

        elif choice == "17":
            print("\n👋 Thank you for using Personal AI Learning Chatbot!")
            print("Goodbye, Anand!")
            break

        else:
            print("\n❌ Invalid choice. Please try again.")


run_chatbot()
