"""Real JVM byte/lifetime contracts for Android picker snapshots."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_native_activity_result_handlers_have_distinct_request_codes():
    import re
    activity = (Path(__file__).parents[1] / 'android/app/src/main/java/in/anvaya/privateapp/MainActivity.java').read_text()
    values = {name: int(value) for name, value in re.findall(
        r'private static final int (PICK_FILES|SAVE_FILE|VIEW_PDF|EXTERNAL_MEDIA)\s*=\s*(\d+)', activity)}
    assert len(values) == 4
    assert len(set(values.values())) == 4, 'External-player results must never enter the PDF result handler'


def test_picker_snapshot_keeps_original_bytes_and_rejects_partial_uploads(tmp_path):
    if not shutil.which('javac'):
        pytest.skip('JDK compiler unavailable; required in Android CI')
    source = Path(__file__).parents[1] / 'android/app/src/main/java/in/anvaya/privateapp'
    harness = tmp_path / 'UploadContract.java'
    harness.write_text('''package in.anvaya.privateapp;
import java.io.*;
import java.nio.file.*;
import java.util.*;
public class UploadContract {
 public static void main(String[] args) throws Exception {
  File root = new File(args[0]); root.mkdirs();
  byte[] original = "%PDF-1.4\\nOriginal lecture".getBytes("UTF-8");
  File selected = UploadSnapshot.copy(new ByteArrayInputStream(original), root, "कक्षा.pdf", 1024);
  long modified = selected.lastModified();
  original[0] = 0;
  if (Files.readAllBytes(selected.toPath())[0] != '%' || selected.lastModified() != modified)
   throw new AssertionError("Picker source must not change selected upload");
  if (!selected.getName().equals("कक्षा.pdf")) throw new AssertionError("Human filename lost");
  File second = UploadSnapshot.copy(new ByteArrayInputStream(new byte[]{42}), root, "कक्षा.pdf", 1024);
  if (second.equals(selected) || Files.readAllBytes(selected.toPath()).length < 2)
   throw new AssertionError("A later selection replaced the pending upload");
  int count = root.list().length;
  try { UploadSnapshot.copy(new ByteArrayInputStream(new byte[8]), root, "large.pdf", 7);
   throw new AssertionError("Oversized selection accepted"); } catch(IOException expected) {}
  InputStream broken = new InputStream() { public int read() throws IOException { throw new IOException("source revoked"); } };
  try { UploadSnapshot.copy(broken, root, "broken.pdf", 1024);
   throw new AssertionError("Interrupted source accepted"); } catch(IOException expected) {}
  if (root.list().length != count) throw new AssertionError("Partial selections leaked");
  boolean[] closed = {false};
  InputStream limited = new ByteArrayInputStream(new byte[]{1}) {
   public void close() { closed[0] = true; }
  };
  try { UploadSnapshot.copy(limited, root, "over-cap.pdf", 0);
   throw new AssertionError("Zero remaining quota accepted"); } catch(IOException expected) {}
  if (!closed[0]) throw new AssertionError("Quota rejection leaked provider stream");
  closed[0] = false;
  File blocked = new File(root,"not-a-directory");Files.write(blocked.toPath(),new byte[]{0});
  InputStream unavailable = new ByteArrayInputStream(new byte[]{1}) {
   public void close() { closed[0] = true; }
  };
  try { UploadSnapshot.copy(unavailable, blocked, "unavailable.pdf", 1024);
   throw new AssertionError("Invalid storage accepted"); } catch(IOException expected) {}
  if (!closed[0]) throw new AssertionError("Storage rejection leaked provider stream");
  File escaped = UploadSnapshot.copy(new ByteArrayInputStream(new byte[]{1}), root, "../../escape.pdf", 1024);
  if (!escaped.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator))
   throw new AssertionError("Filename escaped private upload root");
 }
}''', encoding='utf-8')
    compiled = subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
        str(source / 'DownloadSpec.java'), str(source / 'UploadSnapshot.java'), str(harness)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'in.anvaya.privateapp.UploadContract', str(tmp_path / 'selected')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
