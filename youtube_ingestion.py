import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from knowledge_paths import BASE_DIR


YOUTUBE_DIR = os.path.join(
    BASE_DIR,
    "knowledge",
    "documents",
    "youtube_transcripts"
)


def ensure_youtube_dir():
    """
    Create the transcript directory only when a transcript
    is actually going to be written.

    Importing this module and listing transcripts must remain
    side-effect free.
    """
    os.makedirs(
        YOUTUBE_DIR,
        exist_ok=True
    )

    return YOUTUBE_DIR


def extract_video_id(url):
    """
    Extract a YouTube video ID from common URL formats.
    """

    url = url.strip()

    if not url:
        return None

    parsed = urlparse(url)

    host = parsed.netloc.lower()

    if "youtu.be" in host:
        return parsed.path.strip("/").split("/")[0]

    if "youtube.com" in host:
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            values = query.get("v")

            if values:
                return values[0]

        if parsed.path.startswith("/shorts/"):
            parts = parsed.path.split("/")

            if len(parts) >= 3:
                return parts[2]

        if parsed.path.startswith("/embed/"):
            parts = parsed.path.split("/")

            if len(parts) >= 3:
                return parts[2]

    # Allow direct video ID
    if re.fullmatch(
        r"[A-Za-z0-9_-]{11}",
        url
    ):
        return url

    return None


def safe_filename(text):
    """
    Make a Windows-safe filename.
    """

    text = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text[:120]


def get_transcript(video_id, languages=None):
    """
    Download a YouTube transcript using youtube-transcript-api.
    """

    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi
        )

    except ImportError:
        raise RuntimeError(
            "YouTube transcript support is not installed. "
            "Run: python -m pip install youtube-transcript-api"
        )

    if languages is None:
        languages = [
            "en",
            "en-IN",
            "hi"
        ]

    try:
        transcript_api = YouTubeTranscriptApi()

        transcript = transcript_api.fetch(
            video_id,
            languages=languages
        )

        entries = []

        for item in transcript:
            text = item.text.strip()

            if not text:
                continue

            entries.append({
                "text": text,
                "start": float(item.start),
                "duration": float(
                    item.duration
                )
            })

        return entries

    except Exception as error:
        raise RuntimeError(
            f"Could not retrieve transcript: {error}"
        )


def format_timestamp(seconds):
    total_seconds = int(seconds)

    minutes, seconds = divmod(
        total_seconds,
        60
    )

    hours, minutes = divmod(
        minutes,
        60
    )

    if hours:
        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )

    return (
        f"{minutes:02d}:"
        f"{seconds:02d}"
    )


def save_transcript(
    video_id,
    transcript,
    title=None,
    source_url=None
):
    """
    Save transcript as Markdown so the existing knowledge
    and automatic semantic indexing pipeline can read it.
    """

    if not title:
        title = f"YouTube_{video_id}"

    filename = (
        safe_filename(title)
        + "_"
        + video_id
        + ".md"
    )

    ensure_youtube_dir()

    file_path = os.path.join(
        YOUTUBE_DIR,
        filename
    )

    lines = [
        f"# {title}",
        "",
        f"Video ID: {video_id}",
    ]

    if source_url:
        lines.append(
            f"Source URL: {source_url}"
        )

    lines.extend([
        "Imported into Personal AI Learning Chatbot",
        f"Imported at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Transcript",
        ""
    ])

    for item in transcript:
        timestamp = format_timestamp(
            item["start"]
        )

        lines.append(
            f"[{timestamp}] {item['text']}"
        )

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(
            "\n".join(lines)
        )

    return file_path


def import_youtube_video():
    print(
        "\n========== IMPORT YOUTUBE LECTURE =========="
    )

    url = input(
        "\nPaste YouTube URL: "
    ).strip()

    video_id = extract_video_id(
        url
    )

    if not video_id:
        print(
            "\nCould not understand that YouTube URL."
        )
        return

    title = input(
        "Lecture title "
        "(press Enter to use video ID): "
    ).strip()

    if not title:
        title = (
            f"YouTube Lecture {video_id}"
        )

    print(
        "\nRetrieving transcript..."
    )

    try:
        transcript = get_transcript(
            video_id
        )

    except RuntimeError as error:
        print(
            f"\n{error}"
        )
        return

    if not transcript:
        print(
            "\nNo transcript text was returned."
        )
        return

    file_path = save_transcript(
        video_id,
        transcript,
        title=title,
        source_url=url
    )

    print(
        "\nTranscript imported successfully."
    )

    print(
        f"Saved to: {file_path}"
    )

    print(
        "\nThe V5.1 automatic indexer will detect "
        "this new transcript the next time the "
        "knowledge index is loaded."
    )


def list_imported_transcripts():
    files = []

    if os.path.isdir(
        YOUTUBE_DIR
    ):
        for file_name in os.listdir(
            YOUTUBE_DIR
        ):
            if file_name.lower().endswith(
                ".md"
            ):
                files.append(
                    file_name
                )

    files.sort()

    print(
        "\n========== IMPORTED YOUTUBE TRANSCRIPTS =========="
    )

    if not files:
        print(
            "\nNo YouTube transcripts imported yet."
        )
        return

    for number, file_name in enumerate(
        files,
        start=1
    ):
        print(
            f"{number}. {file_name}"
        )


def youtube_menu():
    while True:
        print(
            "\n========== YOUTUBE LEARNING INTEGRATION =========="
        )

        print(
            "1. Import YouTube Lecture Transcript"
        )

        print(
            "2. List Imported Transcripts"
        )

        print(
            "3. Back"
        )

        choice = input(
            "\nEnter your choice (1-3): "
        ).strip()

        if choice == "1":
            import_youtube_video()

        elif choice == "2":
            list_imported_transcripts()

        elif choice == "3":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 3."
            )


if __name__ == "__main__":
    youtube_menu()
