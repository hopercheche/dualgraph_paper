"""Recount the frozen first-call message snapshots; no model calls required."""
from pathlib import Path
from tokenizers import Tokenizer
import json
D=Path(__file__).resolve().parent
T=Tokenizer.from_file(str(D/'tokenizer.json'))
audit=json.loads((D/'inferred_video_request_audit.json').read_text(encoding='utf8'))
checked=[]
for row in audit['videos']:
 p=D/Path(row['request_file']).name
 q=json.loads(p.read_text(encoding='utf8'))
 if 'judge_initial_require_report' in q:q=q['judge_initial_require_report']
 text='\n'.join(m['content'] for m in q['messages'])
 n=len(T.encode(text,add_special_tokens=False).ids)
 expect=row['request_summary']['messages_content_reference_tokens_concatenated_newline']
 assert n==expect,(row['video_id'],n,expect)
 checked.append({'video_id':row['video_id'],'reference_tokens':n})
print(json.dumps({'checked':len(checked),'provider_calls':0,'results':checked},ensure_ascii=False,indent=2))
