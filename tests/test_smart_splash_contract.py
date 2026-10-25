"""Executable JVM attachment boundary and Android launch resource contracts.

Device rendering/lifecycle checks live in StartupSplashTest; these checks can
still run when the Android SDK or emulator is unavailable.
"""
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).parents[1]
ANDROID = ROOT / "android/app/src/main"
JAVA = ANDROID / "java/in/anvaya/privateapp"


@pytest.mark.skipif(shutil.which("javac") is None, reason="Java compiler unavailable")
def test_provider_attachment_mimes_are_exact_and_reject_path_payloads(tmp_path):
    expected = {
        "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
        "mp4": "video/mp4", "mkv": "video/x-matroska", "mov": "video/quicktime", "webm": "video/webm",
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "pdf": "application/pdf",
        "txt": "text/plain", "md": "text/markdown", "csv": "text/csv",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    checks = "\n".join(
        f'if (!"{mime}".equals(NoteAttachmentType.mimeForFilename("asset_1-2.{suffix}"))) throw new AssertionError("{suffix}");'
        for suffix, mime in expected.items()
    )
    harness = tmp_path / "AttachmentBoundary.java"
    harness.write_text('''package in.anvaya.privateapp;
public class AttachmentBoundary {
 public static void main(String[] args) {
''' + checks + '''
  String[] bad = {null, "", "../secret.pdf", "foo/bar.pdf", "%2e%2e.pdf", "a.pdf.exe", "a.PDF", ".pdf", "a.html", "a.svg", "a.zip", "a\\\\b.pdf", "a.pdf?x=1"};
  for (String name : bad) if (NoteAttachmentType.mimeForFilename(name) != null) throw new AssertionError(name);
 }
}''')
    compile_result = subprocess.run(
        ["javac", "-d", str(tmp_path), str(JAVA / "NoteAttachmentType.java"), str(harness)],
        capture_output=True, text=True,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run(["java", "-cp", str(tmp_path), "in.anvaya.privateapp.AttachmentBoundary"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "NoteAttachmentType.mimeForFilename(parts.get(3)) == null" in (JAVA / "MediaFileProvider.java").read_text()


def test_launch_uses_light_system_and_native_surfaces_and_original_mark():
    attrs = "{http://schemas.android.com/apk/res/android}"
    manifest = ET.parse(ANDROID / "AndroidManifest.xml").getroot()
    activity = manifest.find("application/activity")
    assert activity.attrib[attrs + "theme"] == "@style/LaunchTheme"
    styles = ET.parse(ANDROID / "res/values/styles.xml").getroot()
    app = styles.find("style[@name='AppTheme']")
    items = {item.attrib["name"]: item.text for item in app}
    assert items["android:windowBackground"] == "#F8FAFB"
    assert items["android:statusBarColor"] == "#F8FAFB"
    modern = ET.parse(ANDROID / "res/values-v31/styles.xml").getroot().find("style")
    values = {item.attrib["name"]: item.text for item in modern}
    assert values["android:windowSplashScreenBackground"] == "#F8FAFB"
    assert values["android:windowSplashScreenAnimatedIcon"] == "@drawable/anvaya_splash_icon"
    assert (ANDROID / "res/drawable/anvaya_mark.png").read_bytes() == (ROOT / "personal_learning_assistant/ui/web/static/brand/anvaya-mark.png").read_bytes()


def test_startup_reveal_requires_first_paint_and_never_animation_completion():
    activity = (JAVA / "MainActivity.java").read_text()
    splash = (JAVA / "StartupSplashView.java").read_text()
    commit = activity.split("@Override public void onPageCommitVisible", 1)[1].split("@Override public void onReceivedError", 1)[0]
    assert "postVisualStateCallback" in commit
    assert "postOnAnimation(() -> revealWorkspace(view))" in commit
    assert activity.count("revealWorkspace(view)") == 1
    assert "workspaceRoot.addView(web, 0," in activity
    assert "workspaceRoot.removeView(splash)" in activity
    assert "ValueAnimator.areAnimatorsEnabled()" in splash
    assert "withEndAction" not in splash
    assert "Thread.sleep" not in activity
    assert "WeakReference<MainActivity>" in activity
    assert "startupAttempt != attempt" in activity
    assert "startupHandler.removeCallbacksAndMessages(null)" in activity
    assert "setOnExitAnimationListener" in activity and "platformSplash.remove()" in activity


@pytest.mark.skipif(shutil.which("javac") is None, reason="Java compiler unavailable")
def test_only_gestured_obsidian_open_vault_note_links_leave_webview(tmp_path):
    harness = tmp_path / "ObsidianBoundary.java"
    harness.write_text('''package in.anvaya.privateapp;
public class ObsidianBoundary {
 public static void main(String[] args) {
  String good = "obsidian://open?vault=My%20Vault&file=Notes%2FMy%20note.md";
  if (!ObsidianOpenRequest.permits(good,true,true)) throw new AssertionError("Valid open");
  if (ObsidianOpenRequest.permits(good,false,true) || ObsidianOpenRequest.permits(good,true,false)) throw new AssertionError("gesture/frame");
  String[] bad = {null, "https://open?vault=x&file=y", "obsidian://new?vault=x&file=y", "obsidian://user@open?vault=x&file=y", "obsidian://open:80?vault=x&file=y", "obsidian://open/path?vault=x&file=y", "obsidian://open?vault=x", "obsidian://open?vault=x&file=", "obsidian://open?vault=x&file=y&file=z", "obsidian://open?vault=x&file=y&command=delete", "obsidian://open?vault=x&file=y#fragment", "obsidian://open?vault=x&file=%00", "obsidian://open?vault=x&file=%", "obsidian://open?vault=x&file=y&"};
  for(String value:bad) if(ObsidianOpenRequest.permits(value,true,true)) throw new AssertionError(value);
 }
}''')
    compiled = subprocess.run(["javac", "-d", str(tmp_path), str(JAVA / "ObsidianOpenRequest.java"), str(harness)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    run = subprocess.run(["java", "-cp", str(tmp_path), "in.anvaya.privateapp.ObsidianBoundary"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
