"""Host-runnable Java policy and native backup contracts; not device certification."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import pytest
from test_native_document_library import pdf_bytes


def test_native_intent_parser_rejects_other_hosts_paths_and_ambiguous_fields(tmp_path):
    if not shutil.which('javac'): pytest.skip('JDK unavailable')
    source=Path(__file__).parents[1]/'android/app/src/main/java/in/anvaya/privateapp'
    harness=tmp_path/'NativeContract.java'
    harness.write_text('''import in.anvaya.privateapp.*;
public class NativeContract {
 public static void main(String[] args) {
  String origin="http://127.0.0.1:12345";
  String base=origin+"/library/files/"+"a".repeat(32)+"/original";
  assert NativeDocumentRequest.parse(origin,base+"?native_action=open&position=18&download=1").position==18;
  assert NativeDocumentRequest.parse(origin,base+"?native_action=share").share;
  for(String url:new String[]{base,base+"?native_action=open&position=0",base+"?native_action=open&position=2501",base+"?native_action=open&native_action=share",base+"?native_action=open&next=evil",base+"?native_action=open#page=2",base.replace(":12345",":12346")+"?native_action=open",base.replace("127.0.0.1","example.com")+"?native_action=open",origin+"/mobile/backup?native_action=open"}) {
   assert NativeDocumentRequest.parse(origin,url)==null:url;
  }
 }
}''')
    subprocess.run(['javac','-d',str(tmp_path),str(source/'LocalOrigin.java'),str(source/'NativeDocumentRequest.java'),str(harness)],check=True,capture_output=True)
    subprocess.run(['java','-ea','-cp',str(tmp_path),'NativeContract'],check=True,capture_output=True)


def test_backup_restore_preserves_native_original_and_search(tmp_path):
    from personal_learning_assistant.android_backup import export_backup,stage_restore,apply_pending_restore
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    root=tmp_path/'source';lib=NativeDocumentLibrary(root/'data/native_library',autostart=False)
    raw=pdf_bytes();d=lib.upload(BytesIO(raw),'Original.pdf');lib.run_pending()
    backup=export_backup(root)
    target=tmp_path/'restore';stage_restore(target,backup);apply_pending_restore(target)
    restored=NativeDocumentLibrary(target/'data/native_library',autostart=False)
    assert restored.original(d['id']).read_bytes()==raw
    assert len(restored.search('Eigenvalues'))==2


def test_restore_rejects_missing_native_original(tmp_path):
    from personal_learning_assistant.android_backup import export_backup,stage_restore
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    root=tmp_path/'source';lib=NativeDocumentLibrary(root/'data/native_library',autostart=False)
    d=lib.upload(BytesIO(pdf_bytes()),'Original.pdf')
    lib.original(d['id']).unlink()
    backup=export_backup(root)
    with pytest.raises(ValueError):stage_restore(tmp_path/'target',backup)
