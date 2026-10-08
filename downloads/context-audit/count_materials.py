from pathlib import Path
import json, hashlib, statistics, csv
from tokenizers import Tokenizer

D=Path(__file__).resolve().parent
T=Tokenizer.from_file(str(D/'tokenizer.json'))
def nt(s): return len(T.encode(s,add_special_tokens=False).ids)
def ser(v): return json.dumps(v,ensure_ascii=False,separators=(',',':'))
a=json.loads((D/'video_materials_audit.json').read_text(encoding='utf8'))
tr=json.loads(Path(a['source_manifest']).read_text(encoding='utf8'))
raw={(x['case'],x['video']):x for x in tr}
rows=[]
for v in a['videos']:
    x=raw[(v['case'],v['video'])]
    speech='\n'.join(c['transcript'].strip() for c in x['chunks'] if c.get('transcript','').strip() and not c.get('no_speech') and c['transcript'].strip()!='[无可辨识语音]')
    timed='\n'.join(f"[{c['start_seconds']:.1f}-{c['end_seconds']:.1f}] {c['transcript']}" for c in x['chunks'])
    r={k:v[k] for k in ['case','video','file','wav_duration_seconds','placeholder_chunk_count','placeholder_seconds','selected_source','source_sha256','transcript_file','human_verified']}
    r.update({'speech_tokens':nt(speech),'speech_chars':len(speech),'timed_transcript_tokens':nt(timed),'speech_text_sha256':hashlib.sha256(speech.encode()).hexdigest()})
    rows.append(r)
station=[]
for k in sorted({v['case'] for v in rows}):
    vv=[r for r in rows if r['case']==k]
    station.append({'case':k,'n':len(vv),'min':min(r['speech_tokens'] for r in vv),'median':statistics.median(r['speech_tokens'] for r in vv),'max':max(r['speech_tokens'] for r in vv),'duration_median_minutes':statistics.median(r['wav_duration_seconds'] for r in vv)/60})
case_rows=[]
root=Path(r'E:\che\apricot\tw_teaching_system_new_bak2\data\cuhk_drug_information_cases')
for p in sorted(root.glob('case_*.json')):
    c=json.loads(p.read_text(encoding='utf8'))
    fields={k:nt(ser(v)) for k,v in c.items()}
    case_rows.append({'case_id':c['case_id'],'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'complete_case_json_tokens':nt(ser(c)),'field_tokens':fields,'rubric_items':len(c['rubric'])})
out={'tokenizer':json.loads((D/'tokenizer_manifest.json').read_text(encoding='utf8')),'counting_contract':{'unit':'Qwen3-8B reference text tokens','special_tokens':False,'not_provider_usage':True,'speech':'Raw ASR recognized text joined with newline; no timestamps, no ASR no-words markers','prompt':'Offline source-assembled first call; count message contents, not cumulative calls or output reservation','limits':'Machine transcripts are not human-corrected; reference tokenizer is not the configured provider tokenizer'},'summary':{'videos':len(rows),'speech_tokens_min':min(r['speech_tokens'] for r in rows),'speech_tokens_median':statistics.median(r['speech_tokens'] for r in rows),'speech_tokens_max':max(r['speech_tokens'] for r in rows)},'per_station':station,'videos':rows,'case_materials':case_rows}
(D/'material_token_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
with (D/'video_tokens.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print(json.dumps({'summary':out['summary'],'per_station':station,'case_materials':case_rows},ensure_ascii=False,indent=2))
