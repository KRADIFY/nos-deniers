"""Recover only explicit programme-total zeroes omitted by synthesis exports."""
import json, sys
from pathlib import Path
from build_rap_actions_national_candidates import canonical_parents, numbers, table_sections, parse_measure
from rap_program_context import programme_context

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/recovery-20260920'

def main():
    sources=json.loads((REPORT/'actions/sources.json').read_text(encoding='utf8'))
    gaps=json.loads((REPORT/'actions/gaps.json').read_text(encoding='utf8'))
    targets={(g['year'],g['mission'],g['program'],g['measure'],g['stage']) for g in gaps
             if g['reason']=='canonical_program_group_missing'}
    previous=ROOT/'budget_service/data/rap-explicit-zeros.json'
    if previous.exists():
        targets|={tuple(p['key']) for p in json.loads(previous.read_text(encoding='utf8'))['proofs']}
    targets|={(year,'AV',program,'AE','OUVERT') for year in (2024,2025) for program in ('421','422')}
    parents=canonical_parents()
    missions={(r['year'],r['mission']):r['mission_label'] for r in parents}
    rows=[];proofs=[]
    for source in sources:
        relevant={k for k in targets if k[:2]==(source['year'],source['mission'])}
        if not relevant:continue
        text=Path(source['text_path']).read_text(encoding='utf8');context=programme_context(text)
        for section in table_sections(text,source['year']):
            program=section['programme']
            for measure,lines in section['measures'].items():
                parsed=parse_measure(lines,measure)
                for stage,word in [('LFI','LFI'),('EXEC','consomm'),('OUVERT','ouvert')]:
                    key=(source['year'],source['mission'],program,measure,stage)
                    if key not in relevant:continue
                    matches=[(page,line) for i,(page,_,line) in enumerate(lines)
                             if line.strip().startswith('Total des '+measure) and word in
                             (line+' '+(lines[i+1][2] if stage=='LFI' and i+1<len(lines) else ''))]
                    assert len(matches)==1,(key,matches)
                    page,raw=matches[0];values=numbers(raw)
                    value=values[-2] if stage=='LFI' else values[-1]
                    assert value==0,(key,raw)
                    if stage!='OUVERT':
                        field='lfi_euros' if stage=='LFI' else 'exec_euros'
                        assert not parsed['errors'] and parsed['actions']
                        assert all(a[field]==0 for a in parsed['actions']),(key,parsed)
                    row=dict(year=source['year'],stage=stage,measure=measure,budget='BG',mission=source['mission'],
                             mission_label=missions[key[:2]],program=program,program_label=context[page]['label'],
                             action='',action_label='',subaction='',subaction_label='',category='',title='',cents=0,
                             source=source['source'],line=page,field=f'RAP {source["year"]} · total {stage} {measure} · zéro explicitement publié, non ventilé par titre',approximate=0)
                    rows.append(row);proofs.append(dict(key=list(key),source=source['source'],sha256=source['sha256'],
                        page=page,programme_page=context[page]['opening_page'],raw_line=raw,published_total_euros=value))
    assert len(rows)==len(targets)==46,(len(rows),len(targets))
    assert len({tuple(p['key']) for p in proofs})==len(rows)
    output=ROOT/'budget_service/data/rap-explicit-zeros.json'
    output.write_text(json.dumps(dict(version='rap-explicit-zeros-1',rows=rows,proofs=proofs),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(explicit_zeroes=len(rows),sources=len({r['source'] for r in rows}))))

if __name__=='__main__':main()
