"""R040a entry that rejects an unbound file-only receipt before allocation."""
from __future__ import annotations
import argparse,getpass,hashlib,importlib.util,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;RID='E2-R040a';BASE=HERE/'r040a_d16_supplement_prepare.py';DRY=HERE/'r040a_d16_dryrun_v1.py';COLLECTOR=HERE/'r040a_d16_process_collection_v3.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _base():
 s=importlib.util.spec_from_file_location('r040a_prepare_v1_retained',BASE);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def require_dry_run_receipt(path):
 path=Path(path)
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R040a requires a sealed dry-run receipt')
 data=json.loads(path.read_text(encoding='utf-8'));sources={'r040a_d16_dryrun_v1.py':sha(DRY),'r040a_d16_process_collection_v3.py':sha(COLLECTOR),'r040a_d16_supplement_prepare_v2.py':sha(Path(__file__))}
 wanted={'rid':RID,'script':str(Path(__file__).resolve()),'formal_entry':str(Path(__file__).resolve()),'dry_runner':str(DRY.resolve()),'uid':getattr(os,'getuid',lambda:-1)(),'user':getpass.getuser(),'cwd':os.getcwd()}
 for key,value in wanted.items():
  if data.get(key)!=value:raise RuntimeError('R040a dry receipt binding differs: '+key)
 if not isinstance(data.get('sources'),dict) or any(data['sources'].get(key)!=value for key,value in sources.items()):raise RuntimeError('R040a dry receipt binding differs: sources')
 if data.get('receipt_path')!=str(path.resolve()) or not data.get('formal_round_path'):raise RuntimeError('R040a dry receipt path binding differs')
 if any(data.get(key) is not False for key in ('service_started','requests_sent','gpu_lock_taken','batch_allocated','formal_rid_directory_created')):raise RuntimeError('R040a dry receipt records a prohibited side effect')
 return {'path':str(path),'sha256':sha(path),'receipt':data}
def child_argv(base,batch,receipt,after,dry_receipt):
 return [str(base.ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--after-round',after,'--dry-receipt',str(dry_receipt)]
def _review(base,after,dry):
 document=base.require_review(after)
 sources=document.get('sources',{})
 expected={str(Path(__file__).resolve()):sha(Path(__file__)),str(COLLECTOR.resolve()):sha(COLLECTOR)}
 if any(sources.get(path)!=digest for path,digest in expected.items()):raise RuntimeError('R040a review omits v2 entry or collector v3')
 if document.get('dry_run_receipt')!=dry['path'] or document.get('dry_run_receipt_sha256')!=dry['sha256']:raise RuntimeError('R040a review binds a different dry-run receipt')
 return document
def execute(*,dry_receipt,owned_child=False,batch=None,receipt=None,after='E2-R048'):
 dry=require_dry_run_receipt(dry_receipt);base=_base();_review(base,after,dry)
 original_review=base.require_review
 # Both parent and owned child now produce/verify argv whose executable is this
 # final entry; v1 cannot reserve a child that bypasses receipt admission.
 base.child_argv=lambda number,launch,round_after:child_argv(base,number,launch,round_after,dry_receipt)
 base.require_review=lambda round_after:_review_from_original(original_review,round_after,dry)
 collector=_load_collector();old_body=base.run_supplement_body
 base.run_supplement_body=lambda owner,inputs,wrapper,review,review_sha256,**kw:old_body(owner,inputs,wrapper,review,review_sha256,native_module=collector,**kw)
 return base.execute(owned_child=owned_child,batch=batch,receipt=receipt,after=after)
def _review_from_original(original,after,dry):
 document=original(after);sources=document.get('sources',{})
 expected={str(Path(__file__).resolve()):sha(Path(__file__)),str(COLLECTOR.resolve()):sha(COLLECTOR)}
 if any(sources.get(path)!=digest for path,digest in expected.items()):raise RuntimeError('R040a review omits v2 entry or collector v3')
 if document.get('dry_run_receipt')!=dry['path'] or document.get('dry_run_receipt_sha256')!=dry['sha256']:raise RuntimeError('R040a review binds a different dry-run receipt')
 return document
def _load_collector():
 s=importlib.util.spec_from_file_location('r040a_collector_v3',COLLECTOR);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS);parser.add_argument('--batch',type=int,help=argparse.SUPPRESS);parser.add_argument('--launch-receipt',type=Path,help=argparse.SUPPRESS);parser.add_argument('--after-round',default='E2-R048');parser.add_argument('--dry-receipt',type=Path);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--dry-run-dir',type=Path)
 args=parser.parse_args(argv)
 if args.dry_run:
  if args.dry_run_dir is None:parser.error('--dry-run-dir is required')
  dry=importlib.util.spec_from_file_location('r040a_dry',DRY);module=importlib.util.module_from_spec(dry);dry.loader.exec_module(module);return module.dry_run(args.dry_run_dir,final_entry=Path(__file__).resolve())
 if args.run:
  if args.dry_receipt is None:parser.error('--dry-receipt is required')
  return execute(dry_receipt=args.dry_receipt,owned_child=args.owned_child,batch=args.batch,receipt=args.launch_receipt,after=args.after_round)
 parser.error('choose --dry-run or --run')
if __name__=='__main__':main()
