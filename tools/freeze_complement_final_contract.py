"""Freeze the verified complement only. No keys, network, GPU or active-site writes."""
from pathlib import Path
import json,hashlib,datetime,shutil
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'consolidation-vectorisation-20260924';O=B/'preparation-conforme'
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
 Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n','utf-8')
verify=load(O/'VERIFICATION.json');status=load(O/'export_status.json');desc=status['partitions']['public'];compat=load(O/'EXISTING_PROCESS_COMPATIBILITY.json');preparation=load(O/'preparation_contract.json')
assert verify['state']=='passed' and compat['passed'] and verify['input_sha256']==desc['sha256']==compat['input_sha256']
assert sha(O/'catalogue.sqlite')==verify['catalogue_sha256'] and sha(O/desc['input'])==desc['sha256']
identity=desc['sha256'];now=datetime.datetime.now().astimezone().isoformat();runner=Path(r'C:\Users\Jean-Christophe\Documents\ChatGPT\Mises à jour auto\nos_deniers_runpod_20260912')
contract=dict(mode='incremental_only',model='BAAI/bge-m3',revision='5617a9f61b028005a4858fdac845db406aefb181',dimension=1024,dense_dimensions=1024,dense_dtype='float16',dense_normalized=True,sparse_dtype='float32',colbert=False,max_tokens=800,truncate=False,artificial_overlap=0,word_boundaries=True,natural_blocks=True,context_included_in_token_limit=True,input='public.bge-m3.jsonl',input_count=desc['count'],tokens=desc['tokens'],input_tokens=desc['tokens'],input_sha256=identity,input_bytes=desc['bytes'],catalogue='../catalogue.sqlite',catalogue_sha256=verify['catalogue_sha256'],part_size=8192,paid_compute_authorized=False,encoder_launched=False,base_input_sha256=verify['source_base_input_sha256'],existing_passages_to_reencode=0,previous_supplement_manifest_sha256='205fc398e9a343eb29adee7c9bbfd738403a52ed0e42e5ebf5dd5fe51857f60a',internal_corpus='Separate held input; excluded from public retrieval',quality_propagation=dict(page_physical=True,paragraph_number_scope='extractor_order_or_document_xml_order_not_official_number',raw_positioned_text=True,table_rows_columns_cells_coordinates=True,headers='candidates_not_certified',null_is_not_zero=True,automatic_numeric_fact=False,ocr_provenance=True,source_kind_per_occurrence=True),validated_at=now)
save(O/'gpu_input/contract.json',contract)
newroot='/mnt/d/ChatGPT/docker/budget/consolidation-vectorisation-20260924/preparation-conforme'
job=dict(existing_runner=str(runner),source_root_windows=str(O),source_root_wsl=newroot,input_relative='gpu_input/public.bge-m3.jsonl',input_count=desc['count'],input_bytes=desc['bytes'],input_sha256=identity,job_name='lexmachine-nos-deniers-complement-'+identity[:12],remote_root='/workspace/nos_deniers_jobs/complement-'+identity[:12],runtime_relative='runpod_incremental',part_size=8192,expected_parts=len(compat['lots']),dense_dimensions=1024,model=contract['model'],revision=contract['revision'],reuse_existing_vectors=True,launch_authorized=False,budget_cap_usd=None,notes=['Use a new job identity and runtime; never reuse the full-corpus launcher unchanged.','Use the existing checkpoint/lease controller, local SHA validation before acknowledgement, and preserved volume.','No old job historical spend or budget exemption transfers to this job.','Import verified returned parts into a COPY of retrieval-supplement-20260923-expanded; compare_previous must prove its 2,779 passages/vectors/citations unchanged.','Retain this rich catalogue and page register alongside search.sqlite; runtime citations alone do not carry all geometry.','Validate bibliography/source download routes and example queries before activation.'])
save(O/'RUNPOD_JOB.json',job)
# Preserve a self-contained copy of the exact preparation code used for this complement.
for filename in ['prepare_complement_final_contract.py','export_complement_final_contract.py','verify_complement_final_contract.py','freeze_complement_final_contract.py']:
 target=O/'code'/filename
 if not target.exists():shutil.copyfile(ROOT/'tools'/filename,target)
 else:assert sha(target)==sha(ROOT/'tools'/filename)
for srcpath,expected in preparation['code'].items():
 src=Path(srcpath);assert sha(src)==expected
 target=O/'code'/'original'/src.name;target.parent.mkdir(exist_ok=True)
 if not target.exists():shutil.copyfile(src,target)
 else:assert sha(target)==expected
handoff=dict(state='VERIFIED_INCREMENTAL_INPUT_READY',generation_root=str(O),input=str(O/desc['input']),input_count=desc['count'],input_sha256=identity,input_bytes=desc['bytes'],input_tokens=desc['tokens'],contract=str(O/'gpu_input/contract.json'),catalogue=str(O/'catalogue.sqlite'),page_reviews='catalogue.sqlite:page_reviews',manifest=str(O/'frozen/manifest.json'),verification=str(O/'VERIFICATION.json'),structured_reference=str(O/'structured'),source_files_root=str(B),source_inventory=str(B/'_controle/sources.json'),runpod_job=str(O/'RUNPOD_JOB.json'),runpod_input_ready=True,launch_authorized=False,encoder_launched=False,active_site_modified=False,existing_vector_base_modified=False,internal_passages_held=667,external_cour_documents_reused=7,notes=['Only this complement is new. Do not re-encode the main corpus or previous supplement.','The 124,146-passage draft input at the parent directory is superseded; it is not this generation.','Raw table candidates are evidence, never automatically certified numeric facts.','The separate internal input is not authorized for the public search index.'])
save(O/'HANDOFF.json',handoff)
files=[]
for p in sorted(O.rglob('*')):
 if not p.is_file() or 'frozen' in p.relative_to(O).parts or p.name in ('progress.json','status.json','export_status.json') or p.name.endswith('.partial'):continue
 files.append(dict(path=str(p.relative_to(B)),bytes=p.stat().st_size,sha256=sha(p)))
for source in load(B/'_controle/sources.json'):
 p=B/source['path'];assert sha(p)==source['sha256'];files.append(dict(path=source['path'],bytes=p.stat().st_size,sha256=source['sha256']))
for name in ['sources.json','indexes-avant.json','sources-site-avant.json','decisions-doublons.json','PROCESSUS_EXISTANT.json']:
 p=B/'_controle'/name;files.append(dict(path=str(p.relative_to(B)),bytes=p.stat().st_size,sha256=sha(p)))
manifest=dict(schema='nos-deniers-incremental-frozen-v1',created_at=now,path_base=str(B),state='verified_input_ready',input_sha256=identity,input_count=desc['count'],input_tokens=desc['tokens'],source_generation_reference='F:/LexMachine/NosDeniers/generation_tables_20260911',source_base_input_sha256=contract['base_input_sha256'],file_count=len(files),files=files,active_site_modified=False,gpu_launched=False)
save(O/'frozen/manifest.json',manifest)
save(B/'HANDOFF.json',dict(state='SUPERSEDED_BY_VERIFIED_INCREMENTAL_GENERATION',runpod_input_ready=False,launch_authorized=False,authoritative_handoff=str(O/'HANDOFF.json'),authoritative_input_sha256=identity,note='Do not launch the draft gpu_input in this parent directory. Follow the authoritative handoff.'))
save(B/'RUNPOD_INPUT_SUPERSEDED.json',dict(old_input_sha256='ef5dfba53d5333408c8eb36ecce6380a8ebeee6bd66a5f69c41c3ebfd6d7fd54',old_count=124146,new_handoff=str(O/'HANDOFF.json'),new_count=desc['count'],new_input_sha256=identity))
print(json.dumps(dict(state=handoff['state'],public_passages=desc['count'],tokens=desc['tokens'],immutable_parts=len(compat['lots']),files=len(files),input_sha256=identity,gpu_launched=False),ensure_ascii=False))
