import json
import os

from knowledge_paths import BASE_DIR


DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "obsidian_config.json")

DEFAULT_EXCLUDED_FOLDERS = {
    ".obsidian",
    ".trash",
    ".git",
    "node_modules"
}


def default_config():
    return {
        "vault_path": "",
        "enabled": False
    }


def save_config(config):
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(
            config,
            file,
            indent=2,
            ensure_ascii=False
        )


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return default_config()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            config = json.load(file)

        base = default_config()

        if isinstance(config, dict):
            base.update(config)

        return base

    except (json.JSONDecodeError, OSError):
        return default_config()


def normalize_vault_path(path):
    path = path.strip().strip('"').strip("'")
    return os.path.abspath(os.path.expanduser(path))


def validate_vault_path(path):
    if not path:
        return False, "Vault path is empty."

    if not os.path.isdir(path):
        return False, "That folder does not exist."

    obsidian_folder = os.path.join(path, ".obsidian")

    if not os.path.isdir(obsidian_folder):
        return (
            False,
            "This folder does not look like an Obsidian vault "
            "because .obsidian was not found."
        )

    return True, "Valid Obsidian vault."


def set_vault_path(path):
    normalized = normalize_vault_path(path)
    valid, message = validate_vault_path(normalized)

    if not valid:
        return False, message

    config = load_config()
    config["vault_path"] = normalized
    config["enabled"] = True
    save_config(config)

    return True, normalized


def disable_vault():
    config = load_config()
    config["enabled"] = False
    save_config(config)


def enable_vault():
    config = load_config()

    valid, message = validate_vault_path(
        config.get("vault_path", "")
    )

    if not valid:
        return False, message

    config["enabled"] = True
    save_config(config)

    return True, config["vault_path"]


def get_vault_path():
    config = load_config()

    if not config.get("enabled"):
        return None

    path = config.get("vault_path", "").strip()

    valid, _ = validate_vault_path(path)

    if not valid:
        return None

    return path


def get_obsidian_markdown_files():
    vault_path = get_vault_path()

    if not vault_path:
        return []

    markdown_files = []

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [
            folder
            for folder in dirs
            if folder not in DEFAULT_EXCLUDED_FOLDERS
        ]

        for file_name in files:
            if not file_name.lower().endswith(".md"):
                continue

            markdown_files.append(
                os.path.join(root, file_name)
            )

    return sorted(markdown_files)


def get_vault_stats():
    vault_path = get_vault_path()

    if not vault_path:
        return {
            "enabled": False,
            "vault_path": None,
            "markdown_files": 0
        }

    files = get_obsidian_markdown_files()

    return {
        "enabled": True,
        "vault_path": vault_path,
        "markdown_files": len(files)
    }


def obsidian_menu():
    while True:
        stats = get_vault_stats()

        print(
            "\n========== OBSIDIAN VAULT INTEGRATION =========="
        )

        if stats["enabled"]:
            print(
                f"Status : Connected"
            )
            print(
                f"Vault  : {stats['vault_path']}"
            )
            print(
                f"Notes  : {stats['markdown_files']} Markdown files"
            )
        else:
            print("Status : Not connected")

        print("\n1. Connect / Change Vault")
        print("2. Enable Vault")
        print("3. Disable Vault")
        print("4. Show Vault Status")
        print("5. Back")

        choice = input(
            "\nEnter your choice (1-5): "
        ).strip()

        if choice == "1":
            path = input(
                "\nPaste your Obsidian vault folder path: "
            ).strip()

            success, message = set_vault_path(path)

            if success:
                print(
                    "\nObsidian vault connected successfully."
                )
                print(
                    f"Vault: {message}"
                )
            else:
                print(
                    f"\nCould not connect vault: {message}"
                )

        elif choice == "2":
            success, message = enable_vault()

            if success:
                print(
                    "\nObsidian vault enabled."
                )
            else:
                print(
                    f"\nCould not enable vault: {message}"
                )

        elif choice == "3":
            disable_vault()
            print(
                "\nObsidian vault disabled."
            )

        elif choice == "4":
            stats = get_vault_stats()

            print(
                "\n========== VAULT STATUS =========="
            )
            print(
                f"Enabled : {stats['enabled']}"
            )
            print(
                f"Path    : {stats['vault_path']}"
            )
            print(
                f"Markdown files : {stats['markdown_files']}"
            )

        elif choice == "5":
            break

        else:
            print(
                "\nInvalid choice. Please enter 1 to 5."
            )


if __name__ == "__main__":
    obsidian_menu()
