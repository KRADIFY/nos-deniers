"""Integrate verified staged PDF pages into an explicitly supplied catalogue COPY.

No preparation copy, export, GPU job or production database is created here.
Page commits are resumable; a missing review after a crash is repaired from the
idempotent page ledger before the final, separate release gate can succeed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import unicodedata

try:
    from .vectorisation_page_replacement import ReplacementConflict, fingerprint_page, replace_page
    from .vectorisation_release_contract import canonical, closed_snapshot, digest, _replace_file_safely
except ImportError:
    from vectorisation_page_replacement import ReplacementConflict, fingerprint_page, replace_page
    from vectorisation_release_contract import canonical, closed_snapshot, digest, _replace_file_safely


class IntegrationError(ValueError):
    pass


REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS integration_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS page_inventory(source_sha256 TEXT,page INTEGER,grid_alert INTEGER,has_table INTEGER,PRIMARY KEY(source_sha256,page));
CREATE TABLE IF NOT EXISTS page_reviews(source_sha256 TEXT,page INTEGER,status TEXT,raw_words_preserved INTEGER,raw_numbers_preserved INTEGER,header_context_preserved INTEGER,numeric_fact_certified INTEGER,provenance_json TEXT,PRIMARY KEY(source_sha256,page));
CREATE TABLE IF NOT EXISTS page_review_evidence(source_sha256 TEXT,page INTEGER,shard_sha256 TEXT,raw_record_sha256 TEXT,retained_record_json TEXT,retained_document_path TEXT,retained_record_no INTEGER,PRIMARY KEY(source_sha256,page));
CREATE TABLE IF NOT EXISTS integration_documents(source_sha256 TEXT PRIMARY KEY,stage_sha256 TEXT,contract TEXT,source_shard_sha256 TEXT,pages INTEGER,catalogue_fingerprint TEXT,receipt_json TEXT);
"""


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


@contextmanager
def generation_lock(path):
    with Path(path).open("a+b") as stream:
        if stream.tell()==0:
            stream.write(b"0");stream.flush()
        stream.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise IntegrationError("Another writer holds the generation lock") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name=="nt":
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def _lexical(text):
    return Counter(re.findall(r"\w+",unicodedata.normalize("NFC",str(text)).casefold()))


def _source_blocks(record):
    blocks=[str(block.get("text","")) for block in record.get("blocks",[])]
    words=record.get("words",[])
    if sum((_lexical(word[4]) for word in words),Counter())-sum((_lexical(block) for block in blocks),Counter()):
        blocks.append(" ".join(str(word[4]) for word in words))
    return blocks


def verify_payload(payload,record,source_sha,tokenizer,maximum):
    """Reconstruct raw block characters and bind every table reference/chunk."""
    raw_hash=digest(canonical(record))
    if payload.get("page")!=record["page"] or payload.get("raw_record_sha256")!=raw_hash:
        raise IntegrationError("Staged page differs from the original extraction record")
    required=bool(record.get("tables")) or "grid_candidate_not_resolved" in record.get("issues",[])
    if bool(payload.get("review_required"))!=required or payload.get("grid_alert")!=int("grid_candidate_not_resolved" in record.get("issues",[])) or payload.get("has_table")!=int(bool(record.get("tables"))):
        raise IntegrationError("Staging changed source inventory flags")
    if not required:
        return False
    if digest(canonical(payload.get("record")))!=raw_hash:
        raise IntegrationError("Full original page representation was not retained")
    if payload.get("numeric_fact_certified") is not False or payload.get("allow_automatic_numeric_fact") is not False:
        raise IntegrationError("Raw table data cannot become an automatically certified fact")
    if payload.get("status")!="positioned_source_retained_review_required":
        raise IntegrationError("Unexpected staging review status")
    blocks=_source_blocks(record)
    recovered=["" for _ in blocks]
    raw_bodies=[]
    references={}
    for table in payload.get("tables",[]):
        ref=digest(canonical({"table":table["table"],"context":table["context"]}))
        if ref!=table.get("table_ref") or ref in references:
            raise IntegrationError("Conflicting or invalid raw table reference")
        if table["context"].get("source_sha256")!=source_sha or table["context"].get("page")!=record["page"]:
            raise IntegrationError("Table context belongs to another source/page")
        references[ref]=table
    referenced=set()
    locator=f"page:{record['page']}"
    for chunk in payload.get("chunks",[]):
        text,body=chunk["text"],chunk["body"]
        if not isinstance(text,str) or not isinstance(body,str) or not text.endswith(body):
            raise IntegrationError("Chunk body is not present verbatim in its encoded text")
        count=len(tokenizer.encode(text,add_special_tokens=True).ids)
        if type(chunk.get("tokens")) is not int or chunk["tokens"]!=count or not 0<count<=maximum:
            raise IntegrationError("Staged token count or maximum differs")
        if not chunk["locator"].startswith(locator+"/"):
            raise IntegrationError("Chunk locator escapes the physical page")
        if chunk["kind"]=="page_source_text":
            segments=chunk.get("segments",[])
            if body!="\n\n".join(segment["text"] for segment in segments):
                raise IntegrationError("Raw chunk body differs from its exact source segments")
            for segment in segments:
                index=segment["block"]
                if type(index) is not int or not 0<=index<len(blocks):
                    raise IntegrationError("Unknown raw block reference")
                start,end=segment["char_start"],segment["char_end"]
                if start!=len(recovered[index]) or end!=start+len(segment["text"]) or blocks[index][start:end]!=segment["text"]:
                    raise IntegrationError("Gap, overlap or altered characters in raw chunk segments")
                recovered[index]+=segment["text"]
            raw_bodies.append(body)
        elif chunk["kind"]=="table_candidate":
            if chunk.get("table_ref") not in references:
                raise IntegrationError("Table chunk has no retrievable raw table")
            referenced.add(chunk["table_ref"])
        else:
            raise IntegrationError("Unknown staged chunk kind")
    if recovered!=blocks or raw_bodies!=payload.get("raw_segments"):
        raise IntegrationError("Raw source characters were omitted")
    if sum((_lexical(word[4]) for word in record.get("words",[])),Counter())-sum((_lexical(block) for block in recovered),Counter()):
        raise IntegrationError("Raw source words are not represented in chunks")
    if referenced!=set(references):
        raise IntegrationError("A raw table lacks searchable chunks")
    return True


def _routes(con,sha,page):
    locator=f"page:{page}"
    rows=con.execute("SELECT DISTINCT p.partition,p.embedding_route FROM occurrences o JOIN passages p ON p.id=o.passage_id WHERE o.asset_sha256=? AND (o.locator=? OR o.locator LIKE ?)",(sha,locator,locator+"/%")).fetchall()
    if rows:
        return sorted({tuple(row) for row in rows})
    rows=con.execute("SELECT DISTINCT p.partition,p.embedding_route FROM occurrences o JOIN passages p ON p.id=o.passage_id WHERE o.asset_sha256=?",(sha,)).fetchall()
    if rows:
        return sorted({tuple(row) for row in rows})
    refs={}
    for row in con.execute("SELECT partition,metadata_json FROM refs WHERE asset_sha256=?",(sha,)):
        refs.setdefault(row["partition"],[]).append(json.loads(row["metadata_json"]))
    result=[]
    for partition,items in refs.items():
        external=any((item.get("source_metadata") or {}).get("already_vectorized_in_cour") for item in items)
        route="existing_cour_pending_connection" if external else ("internal_hold" if partition=="internal" else "new_bge")
        result.append((partition,route))
    if not result:
        raise IntegrationError("Source has no registered partition")
    return sorted(result)


def _manual_ocr_overlay(con,sha,page):
    locator=f"page:{page}"
    evidence=[dict(row) for row in con.execute("SELECT * FROM evidence WHERE asset_sha256=? AND (locator=? OR locator LIKE ?) AND kind='manual_ocr_recovery' ORDER BY id",(sha,locator,locator+"/%"))]
    if not evidence:
        return None
    occurrences=[dict(row) for row in con.execute("SELECT * FROM occurrences WHERE asset_sha256=? AND (locator=? OR locator LIKE ?) AND kind='page_text_ocr_recovered' ORDER BY id",(sha,locator,locator+"/%"))]
    if not occurrences:
        raise IntegrationError("Manual OCR evidence has no preserved OCR passage")
    passages={row["passage_id"]:dict(con.execute("SELECT * FROM passages WHERE id=?",(row["passage_id"],)).fetchone()) for row in occurrences}
    for proof in evidence:
        if json.loads(proof["summary_json"]).get("source_pdf_sha256")!=sha:
            raise IntegrationError("Manual OCR evidence refers to another PDF")
    manifest={"passages":[{"passage_id":row["passage_id"],"occurrence_id":row["id"],"text_sha256":digest(passages[row["passage_id"]]["text"]),"locator":row["locator"],"kind":row["kind"]} for row in occurrences],
              "evidence":[{"id":proof["id"],"sha256":digest(canonical(proof))} for proof in evidence],
              "coordinates_policy":"Native coordinates belong only to the native source record; no coordinates are inferred for recovered OCR text."}
    return {"manifest":manifest,"passages":passages,"occurrences":occurrences,"evidence":evidence}


def _native_chunks(record,sha,tokenizer):
    # Reuse the frozen, already tested source-character chunker. Do not run OCR.
    tools_path=str(Path(__file__).resolve().parent)
    inserted=tools_path not in sys.path
    if inserted:
        sys.path.insert(0,tools_path)
    try:
        from prepare_vectorisation_tables import raw_chunks
        return raw_chunks(record,sha,tokenizer)
    finally:
        if inserted:
            sys.path.remove(tools_path)


def _document_fingerprint(con,sha):
    hash_=hashlib.sha256()
    queries=("SELECT o.*,p.partition,p.embedding_route,p.text,p.tokens FROM occurrences o JOIN passages p ON p.id=o.passage_id WHERE o.asset_sha256=? ORDER BY o.id",
             "SELECT * FROM evidence WHERE asset_sha256=? ORDER BY id")
    for query in queries:
        for row in con.execute(query,(sha,)):
            hash_.update((canonical(dict(row))+"\n").encode("utf-8"))
    return hash_.hexdigest()


def _insert_review(con,table,columns,values):
    existing=con.execute(f"SELECT {','.join(columns)} FROM {table} WHERE source_sha256=? AND page=?",values[:2]).fetchone()
    if existing is not None:
        if tuple(existing)!=tuple(values):
            raise IntegrationError("Existing page review differs; preserve the previous revision")
        return
    con.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",values)


def _review_page(reviews,sha,page,payload,record,shard,shard_sha,source_line,staged,stage_sha,stage_line,required,manual_overlay=None):
    provenance={"source_sha256":sha,"page":page,"source_locator":f"page:{page}",
                "source_shard":str(shard),"source_shard_sha256":shard_sha,
                "raw_record_sha256":digest(canonical(record)),"stage_document_sha256":stage_sha,
                "numeric_fact_certified":False}
    if manual_overlay:
        provenance["manual_ocr_overlay"]=manual_overlay["manifest"]
    with reviews:
        _insert_review(reviews,"page_inventory",("source_sha256","page","grid_alert","has_table"),
                       (sha,page,payload["grid_alert"],payload["has_table"]))
        _insert_review(reviews,"page_reviews",("source_sha256","page","status","raw_words_preserved","raw_numbers_preserved","header_context_preserved","numeric_fact_certified","provenance_json"),
                       (sha,page,payload["status"] if required else "source_text_verified",1,1,1,0,canonical(provenance)))
        _insert_review(reviews,"page_review_evidence",("source_sha256","page","shard_sha256","raw_record_sha256","retained_record_json","retained_document_path","retained_record_no"),
                       (sha,page,shard_sha,provenance["raw_record_sha256"],None,str(staged if required else shard),stage_line if required else source_line))


def integrate_document(con,baseline,reviews,receipt,*,stage_contract,extracted_root,tokenizer,baseline_archive,progress_callback=None):
    """Caller owns generation lock. Both SQLite outputs are private generation files."""
    sha=receipt["source_sha256"]
    row=con.execute("SELECT a.path,e.shard_sha256,e.receipt_json FROM assets a JOIN extraction e ON e.asset_sha256=a.sha256 WHERE a.sha256=? AND e.status='complete'",(sha,)).fetchone()
    if row is None or row["shard_sha256"]!=receipt["source_shard_sha256"]:
        raise IntegrationError("Current catalogue extraction differs from the staging baseline")
    source=Path(row["path"])
    if file_hash(source)!=sha or (source.resolve()!=Path(receipt["source_pdf"]).resolve() and file_hash(receipt["source_pdf"])!=sha):
        raise IntegrationError("Physical source PDF fingerprint changed")
    staged=Path(receipt["file"]).resolve(strict=True)
    if receipt["contract"]!=stage_contract["contract"] or file_hash(staged)!=receipt["sha256"] or staged.stat().st_size!=receipt["bytes"]:
        raise IntegrationError("Staged document receipt/code contract changed")
    shard=Path(extracted_root)/sha[:2]/(sha+".jsonl.gz")
    if file_hash(shard)!=receipt["source_shard_sha256"]:
        raise IntegrationError("Physical source extraction shard changed")
    prior=reviews.execute("SELECT * FROM integration_documents WHERE source_sha256=?",(sha,)).fetchone()
    if prior:
        if prior["stage_sha256"]!=receipt["sha256"] or prior["contract"]!=receipt["contract"] or prior["source_shard_sha256"]!=receipt["source_shard_sha256"]:
            raise IntegrationError("Document already integrated from another revision")
        if prior["catalogue_fingerprint"]!=_document_fingerprint(con,sha):
            raise IntegrationError("An integrated document was subsequently changed")
        for table in ("page_inventory","page_reviews","page_review_evidence"):
            if reviews.execute(f"SELECT count(*) FROM {table} WHERE source_sha256=?",(sha,)).fetchone()[0]!=prior["pages"]:
                raise IntegrationError("Completed document lost its page review evidence")
        return json.loads(prior["receipt_json"])|{"already_integrated":True}
    pages=changed=0
    with gzip.open(shard,"rt",encoding="utf-8") as raw, gzip.open(staged,"rt",encoding="utf-8") as inp:
        for source_line,line in enumerate(raw,1):
            record=json.loads(line)
            if record.get("kind")!="page":
                continue
            pages+=1
            if record["page"]!=pages:
                raise IntegrationError("Source pages are missing or out of order")
            stage_line=inp.readline()
            if not stage_line:
                raise IntegrationError("Staged document omits a source page")
            payload=json.loads(stage_line)
            required=verify_payload(payload,record,sha,tokenizer,stage_contract["config"]["max_tokens_including_context"])
            manual_overlay=_manual_ocr_overlay(baseline,sha,pages)
            chunks=payload.get("chunks",[])
            tables=payload.get("tables",[])
            if manual_overlay and not required:
                chunks=_native_chunks(record,sha,tokenizer)
            if (required or manual_overlay) and chunks:
                revision=digest(stage_contract["contract"]+receipt["sha256"]+sha+str(pages)+(":manual-ocr-preserved" if manual_overlay else ""))
                passage_rows={};occurrence_rows=[];chunk_refs=[]
                for partition,route in _routes(baseline,sha,pages):
                    for index,chunk in enumerate(chunks):
                        pid=digest(partition+"\n"+route+"\n"+chunk["text"])
                        passage_rows[pid]={"id":pid,"partition":partition,"body_sha256":digest(" ".join(chunk["body"].split())),"text":chunk["text"],"tokens":chunk["tokens"],"embedding_route":route}
                        oid=digest(sha+partition+chunk["locator"]+chunk["kind"]+str(index)+pid)
                        occurrence_rows.append({"id":oid,"passage_id":pid,"asset_sha256":sha,"locator":chunk["locator"],"section":"","kind":chunk["kind"]})
                        chunk_refs.append({"passage_id":pid,"occurrence_id":oid,"staged_chunk_index":index,"table_ref":chunk.get("table_ref"),"segments_in_staged_chunk":True})
                if manual_overlay:
                    passage_rows.update(manual_overlay["passages"])
                    occurrence_rows.extend(manual_overlay["occurrences"])
                    if not required:
                        # An unmodified text page keeps every prior citation as well
                        # as the OCR, while the native remainder is added separately.
                        for old in baseline.execute("SELECT * FROM occurrences WHERE asset_sha256=? AND (locator=? OR locator LIKE ?)",(sha,f"page:{pages}",f"page:{pages}/%")):
                            old=dict(old)
                            if old["id"] not in {item["id"] for item in occurrence_rows}:
                                occurrence_rows.append(old)
                            passage_rows[old["passage_id"]]=dict(baseline.execute("SELECT * FROM passages WHERE id=?",(old["passage_id"],)).fetchone())
                status=payload["status"] if required else "source_text_verified_with_manual_ocr_overlay"
                summary={"status":status,"numeric_fact_certified":False,"allow_automatic_numeric_fact":False,
                         "staged_document":str(staged),"staged_document_sha256":receipt["sha256"],"staged_record_no":pages,
                         "source_shard":str(shard),"source_shard_sha256":receipt["source_shard_sha256"],
                         "raw_record_sha256":payload["raw_record_sha256"],"chunk_references":chunk_refs}
                if manual_overlay:
                    summary["manual_ocr_overlay"]=manual_overlay["manifest"]
                    if not required:
                        summary["native_raw_chunks"]=chunks
                evidence=[{"id":digest(revision+":page"),"asset_sha256":sha,"record_no":source_line,"locator":f"page:{pages}","kind":"page_source_and_tables","table_no":None,"summary_json":canonical(summary)}]
                if manual_overlay:
                    if required:
                        evidence.extend(manual_overlay["evidence"])
                    else:
                        evidence.extend(dict(old) for old in baseline.execute("SELECT * FROM evidence WHERE asset_sha256=? AND (locator=? OR locator LIKE ?)",(sha,f"page:{pages}",f"page:{pages}/%")))
                for number,table in enumerate(tables):
                    evidence.append({"id":digest(revision+":table:"+table["table_ref"]),"asset_sha256":sha,"record_no":source_line,
                                     "locator":f"page:{pages}/table:{table['context']['table_id']}","kind":"table_candidate","table_no":number,
                                     "summary_json":canonical({"table_ref":table["table_ref"],"status":status,"numeric_fact_certified":False,
                                         "staged_document":str(staged),"staged_document_sha256":receipt["sha256"],"staged_record_no":pages,"staged_table_index":number})})
                replace_page(con,replacement_id=revision,asset_sha256=sha,page=pages,verified_source_sha256=sha,
                             expected_page_fingerprint=fingerprint_page(baseline,sha,pages),passages=list(passage_rows.values()),
                             occurrences=occurrence_rows,evidence=evidence,provenance=summary,
                             max_tokens=stage_contract["config"]["max_tokens_including_context"],update_fts=False,compact_ledger=True,
                             archive_references=baseline_archive|{"staged_document":str(staged),"staged_sha256":receipt["sha256"]})
                changed+=1
            _review_page(reviews,sha,pages,payload,record,shard,receipt["source_shard_sha256"],source_line,staged,receipt["sha256"],pages,required,manual_overlay)
            if progress_callback and pages%20==0:
                progress_callback(pages,changed)
        if inp.readline():
            raise IntegrationError("Staged document contains extra pages")
    if pages!=receipt["pages"] or pages!=json.loads(row["receipt_json"])["counts"]["pages"]:
        raise IntegrationError("Document page count differs from source/staging receipts")
    if file_hash(staged)!=receipt["sha256"] or file_hash(shard)!=receipt["source_shard_sha256"]:
        raise IntegrationError("An input changed during integration")
    result={"source_sha256":sha,"pages":pages,"replaced_pages":changed,"already_integrated":False,
            "numeric_fact_certified":False,"gpu_launched":False}
    with reviews:
        reviews.execute("INSERT INTO integration_documents VALUES(?,?,?,?,?,?,?)",(sha,receipt["sha256"],receipt["contract"],receipt["source_shard_sha256"],pages,_document_fingerprint(con,sha),canonical(result)))
    if progress_callback:
        progress_callback(pages,changed)
    return result


def rebuild_search_index(con):
    exists=con.execute("SELECT 1 FROM sqlite_master WHERE name='vectorisation_index_state'").fetchone()
    if not exists or not con.execute("SELECT 1 FROM vectorisation_index_state WHERE name='passages_fts' AND dirty<>0").fetchone():
        return False
    if con.in_transaction:
        raise IntegrationError("Finish page transactions before rebuilding the search index")
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("DROP TABLE IF EXISTS passages_fts")
        con.execute("CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,text,tokenize='unicode61 remove_diacritics 2')")
        con.execute("INSERT INTO passages_fts SELECT id,text FROM passages")
        if con.execute("SELECT count(*) FROM passages_fts").fetchone()[0]!=con.execute("SELECT count(*) FROM passages").fetchone()[0]:
            raise IntegrationError("Rebuilt search index count differs")
        con.execute("UPDATE vectorisation_index_state SET dirty=0 WHERE name='passages_fts'")
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return True


def integrate_stage(*,generation_root,catalogue,stage_root,source_extracted_root,tokenizer=None,only_sha=None):
    root=Path(generation_root).resolve(strict=True)
    catalogue=Path(catalogue).resolve(strict=True)
    stage_root=Path(stage_root).resolve(strict=True)
    contract=json.loads((stage_root/"staging_contract.json").read_text(encoding="utf-8"))
    source_config=contract["config"]
    original=(Path(source_config["output_root"])/"nos_deniers.sqlite").resolve()
    snapshot=Path(contract["snapshot"]).resolve(strict=True)
    if not catalogue.is_relative_to(root) or catalogue in {original,snapshot} or root==Path(source_config["output_root"]).resolve():
        raise IntegrationError("Target must be an existing catalogue copy inside a separate generation root")
    if catalogue.stat().st_nlink>1 or any(protected.exists() and os.path.samefile(protected,catalogue) for protected in (original,snapshot)):
        raise IntegrationError("Catalogue copy must not be a hard link to any protected database")
    code=contract["code"]
    expected_names={"prepare_vectorisation_tables.py","vectorisation_table_geometry.py","vectorisation_table_text.py"}
    if set(code)!=expected_names or any(file_hash(Path(__file__).parent/name)!=sha for name,sha in code.items()):
        raise IntegrationError("Staging code differs from the frozen contract")
    if digest(canonical({"version":contract["version"],"code":code,"tokenizer":source_config["tokenizer_sha256"]}))!=contract["contract"]:
        raise IntegrationError("Invalid staging contract fingerprint")
    if file_hash(source_config["tokenizer"])!=source_config["tokenizer_sha256"]:
        raise IntegrationError("Tokenizer changed")
    if source_config["max_tokens_including_context"]!=800:
        raise IntegrationError("Existing 800-token chunking contract changed")
    if tokenizer is None:
        from tokenizers import Tokenizer
        tokenizer=Tokenizer.from_file(source_config["tokenizer"])
        tokenizer.no_truncation();tokenizer.no_padding()
    if getattr(tokenizer,"truncation",None):
        raise IntegrationError("Tokenizer truncation is forbidden")
    receipts=json.loads((stage_root/"receipts.json").read_text(encoding="utf-8"))
    if len({row["source_sha256"] for row in receipts})!=len(receipts):
        raise IntegrationError("Duplicate staged source receipts")
    results=[]
    selected=[receipt for receipt in receipts if not only_sha or receipt["source_sha256"] in only_sha]
    started=time.monotonic()
    state={"documents_expected":len(selected),"pages_expected":sum(row["pages"] for row in selected),
           "documents_completed":0,"pages_reviewed":0,"pages_replaced":0,"current_sha":None,
           "current_document_pages":0,"current_document_pages_expected":0,"gpu_launched":False,
           "active_preparation_modified":False}
    def progress(phase,**details):
        state.update(details)
        state.update(phase=phase,at=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),elapsed_seconds=round(time.monotonic()-started,1))
        path=root/"integration_progress.json"
        temporary=path.with_suffix(".json.partial")
        with temporary.open("w",encoding="utf-8",newline="\n") as stream:
            stream.write(canonical(state)+"\n");stream.flush();os.fsync(stream.fileno())
        _replace_file_safely(temporary,path)
    with generation_lock(root/"integration.lock"):
        progress("hashing_baseline_snapshot")
        closed_snapshot(catalogue).close()
        baseline=closed_snapshot(snapshot)
        baseline_archive={"baseline_snapshot":str(snapshot),"baseline_sha256":file_hash(snapshot)}
        con=sqlite3.connect(catalogue,timeout=5)
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=DELETE")
        reviews=sqlite3.connect(root/"page_reviews.sqlite")
        reviews.row_factory=sqlite3.Row
        try:
            reviews.executescript(REVIEW_SCHEMA)
            identity=canonical({"stage_contract":contract["contract"],"snapshot":str(snapshot),"catalogue":str(catalogue)})
            previous=reviews.execute("SELECT value FROM integration_metadata WHERE key='generation_contract'").fetchone()
            if previous and previous[0]!=identity:
                raise IntegrationError("Generation belongs to a different staging contract")
            with reviews:
                reviews.execute("INSERT OR IGNORE INTO integration_metadata VALUES('generation_contract',?)",(identity,))
            for receipt in selected:
                if not Path(receipt["file"]).resolve().is_relative_to(stage_root):
                    raise IntegrationError("Staged document is outside its declared staging folder")
                completed_pages=sum(result["pages"] for result in results)
                completed_replaced=sum(result["replaced_pages"] for result in results)
                progress("integrating_pages",current_sha=receipt["source_sha256"],current_document_pages=0,
                         current_document_pages_expected=receipt["pages"])
                def page_progress(pages,replaced):
                    progress("integrating_pages",current_document_pages=pages,
                             pages_reviewed=completed_pages+pages,pages_replaced=completed_replaced+replaced)
                results.append(integrate_document(con,baseline,reviews,receipt,stage_contract=contract,
                    extracted_root=source_extracted_root,tokenizer=tokenizer,baseline_archive=baseline_archive,
                    progress_callback=page_progress))
                progress("document_complete",documents_completed=len(results),
                         pages_reviewed=sum(result["pages"] for result in results),
                         pages_replaced=sum(result["replaced_pages"] for result in results),
                         current_document_pages=receipt["pages"])
            progress("rebuilding_search_index",current_sha=None)
            rebuild_search_index(con)
            progress("checking_catalogue")
            if con.execute("PRAGMA quick_check").fetchone()[0]!="ok" or con.execute("PRAGMA foreign_key_check").fetchone():
                raise IntegrationError("Generation catalogue integrity check failed")
            progress("integration_complete_gate_pending")
        except BaseException as exc:
            progress("interrupted_requires_review",error=type(exc).__name__+": "+str(exc))
            raise
        finally:
            reviews.close();con.close();baseline.close()
    return {"catalogue":str(catalogue),"page_review_db":str(root/"page_reviews.sqlite"),"documents":results,
            "integration_complete_for_supplied_receipts":True,"release_gate_required":True,
            "numeric_fact_certified":False,"gpu_launched":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-root",required=True,type=Path)
    parser.add_argument("--catalogue",required=True,type=Path)
    parser.add_argument("--stage-root",required=True,type=Path)
    parser.add_argument("--source-extracted-root",required=True,type=Path)
    parser.add_argument("--sha",action="append")
    args=parser.parse_args()
    print(canonical(integrate_stage(generation_root=args.generation_root,catalogue=args.catalogue,
                    stage_root=args.stage_root,source_extracted_root=args.source_extracted_root,only_sha=args.sha)),flush=True)


if __name__=="__main__":
    main()
