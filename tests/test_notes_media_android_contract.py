"""Execute the pure-Java native navigation boundary without an Android SDK."""
from pathlib import Path
import subprocess
import shutil
import pytest

ROOT=Path(__file__).parents[1]

@pytest.mark.skipif(shutil.which("javac") is None,reason="Java compiler unavailable; JVM contract also runs in Android CI")
def test_only_exact_gestured_local_main_frame_media_links_enter_native(tmp_path):
    source=ROOT/'android/app/src/main/java/in/anvaya/privateapp'
    harness=tmp_path/'Boundary.java'
    harness.write_text('''
import in.anvaya.privateapp.*;
public class Boundary {
 public static void main(String[] args) {
  LocalOrigin origin=new LocalOrigin("http://127.0.0.1:3210");
  String good="http://127.0.0.1:3210/notes/media/note_1/file-2/open";
  MediaRequest r=MediaRequest.parse(origin,good,true,true);
  if(r==null || !r.noteId.equals("note_1") || !r.assetId.equals("file-2") || r.share) throw new AssertionError("valid open");
  if(!MediaRequest.parse(origin,good.replace("/open","/share"),true,true).share) throw new AssertionError("share");
  if(MediaRequest.parse(origin,good,false,true)!=null || MediaRequest.parse(origin,good,true,false)!=null) throw new AssertionError("gesture/frame");
  String[] bad={good.replace(":3210",":3211"), good.replace("127.0.0.1","evil.example"),good+"?x=1",good+"#x",good.replace("note_1",".."),good.replace("file-2","%2Fsecret"),good.replace("/open","/file"),good.replace("http:","file:"),good.replace("127.0.0.1","x@127.0.0.1")};
  for(String value:bad) if(MediaRequest.parse(origin,value,true,true)!=null) throw new AssertionError(value);
 }
}''')
    compile_result=subprocess.run(['javac','-d',str(tmp_path),str(source/'LocalOrigin.java'),str(source/'MediaRequest.java'),str(harness)],capture_output=True,text=True)
    assert compile_result.returncode==0,compile_result.stderr
    run=subprocess.run(['java','-cp',str(tmp_path),'Boundary'],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
