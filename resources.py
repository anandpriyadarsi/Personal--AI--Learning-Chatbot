"""
==========================================
Personal AI Learning Chatbot v1.0
Developer : Anand Priyadarsi
Language  : Python
Project   : AI Learning Boot Camp

Description:
A personal learning assistant to organize
notes, learning resources, dashboards,
and backups.

==========================================
"""
import json
import os

FILE_PATH = "data/resources.json"


# -------------------------
# Load Resources
# -------------------------
def load_resources():
    if not os.path.exists(FILE_PATH):
        return []

    try:
        with open(FILE_PATH, "r") as file:
            return json.load(file)

    except json.JSONDecodeError:
        return []


# -------------------------
# Save Resources
# -------------------------
def save_resources(resources):
    with open(FILE_PATH, "w") as file:
        json.dump(resources, file, indent=4)


# -------------------------
# Add Resource
# -------------------------
def add_resource():

    print("\n========== ADD NEW RESOURCE ==========\n")

    title = input("Title : ")
    resource_type = input("Type (YouTube/Book/Website/GitHub/Course): ")
    link = input("Link : ")

    resource = {
        "title": title,
        "type": resource_type,
        "link": link,
        "status": "Not Started"
    }

    resources = load_resources()
    resources.append(resource)
    save_resources(resources)

    print("\n✅ Resource added successfully!")


# -------------------------
# View Resources
# -------------------------
def view_resources():

    resources = load_resources()

    if len(resources) == 0:
        print("\nNo resources found.")
        return

    print("\n========== MY LEARNING RESOURCES ==========")

    for i, resource in enumerate(resources, start=1):

        print("\n----------------------------")
        print(f"Resource {i}")
        print("----------------------------")
        print("Title  :", resource["title"])
        print("Type   :", resource["type"])
        print("Link   :", resource["link"])
        print("Status :", resource["status"])


# -------------------------
# Search Resources
# -------------------------
def search_resources():

    keyword = input("\nEnter keyword : ").lower()

    resources = load_resources()

    found = False

    for resource in resources:

        if (keyword in resource["title"].lower() or
                keyword in resource["type"].lower()):

            found = True

            print("\n----------------------------")
            print("Title  :", resource["title"])
            print("Type   :", resource["type"])
            print("Link   :", resource["link"])
            print("Status :", resource["status"])

    if not found:
        print("\n❌ No matching resource found.")


# -------------------------
# Count Resources
# -------------------------
def count_resources():

    resources = load_resources()

    print("\n========== RESOURCE SUMMARY ==========")
    print(f"\n📚 Total Resources : {len(resources)}")


# -------------------------
# Update Resource Status
# -------------------------
def update_status():

    resources = load_resources()

    if len(resources) == 0:
        print("\nNo resources found.")
        return

    print("\n========== UPDATE STATUS ==========\n")

    for i, resource in enumerate(resources, start=1):
        print(f"{i}. {resource['title']} ({resource['status']})")

    try:
        choice = int(input("\nEnter resource number: "))

        if choice < 1 or choice > len(resources):
            print("Invalid choice.")
            return

        print("\nChoose Status")
        print("1. Not Started")
        print("2. In Progress")
        print("3. Completed")

        status_choice = input("Enter choice: ")

        if status_choice == "1":
            resources[choice-1]["status"] = "Not Started"

        elif status_choice == "2":
            resources[choice-1]["status"] = "In Progress"

        elif status_choice == "3":
            resources[choice-1]["status"] = "Completed"

        else:
            print("Invalid status.")
            return

        save_resources(resources)

        print("\n✅ Status updated successfully!")

    except ValueError:
        print("\nPlease enter a valid number.")
