"""B2 desired GET acceptance on disposable source; replaces defect C witness."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.repo.resolve()))
from scripts.architecture_validation import export_source
child=r'''
import json,hashlib,sys,socket
from pathlib import Path
sys.dont_write_bytecode=True
root=Path.cwd();sys.path.insert(0,str(root))
route=sys.argv[1];seeded=sys.argv[2]=='seeded'
if seeded:
 (root/'data').mkdir(exist_ok=True)
 (root/'data/courses.json').write_text(json.dumps({'version':1,'active_course_id':'ma103n','courses':[{'id':'ma103n','code':'MA103N','name':'Linear Algebra','status':'active','topics':[{'id':'rank','name':'Matrix Rank','status':'weak','confidence':1}]}],'document_links':{}}))
def hashes():return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
writes=[];network=[]
def audit(event,args):
 if event=='socket.connect':network.append(str(args));raise RuntimeError('Network forbidden in probe')
 if event=='open':
  path,mode,flags=args
  writing=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)))
  if writing and isinstance(path,(str,bytes)):
   actual=Path(path).resolve();writes.append(str(actual))
   if not actual.is_relative_to(root.resolve()):raise RuntimeError('Write outside disposable source')
import os
sys.addaudithook(audit)
before=hashes()
from personal_learning_assistant.ui.web import create_app
app=create_app({'TESTING':True})
with app.test_client() as client:r=client.get(route)
after=hashes();print(json.dumps({'route':route,'state':sys.argv[2],'status':r.status_code,'created':sorted(set(after)-set(before)),'changed':sorted(k for k in before if before[k]!=after.get(k)),'writes':writes,'network_attempts':network}))
'''
results=[]
for route in ['/planning','/analysis']:
 for state in ['empty','seeded']:
  with tempfile.TemporaryDirectory(prefix='anvaya-route-audit-') as tmp:
   root=Path(tmp)/'source'
   export_source(a.repo.resolve(),root)
   run=subprocess.run([sys.executable,'-c',child,route,state],cwd=root,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   if run.returncode:raise RuntimeError(run.stderr)
   results.append(json.loads(run.stdout))
assert all(r['status']==200 and not r['network_attempts'] for r in results)
assert all(not r['created'] and not r['changed'] and not r['writes'] for r in results)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
