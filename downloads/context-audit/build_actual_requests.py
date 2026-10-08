"""Offline CUHK prompt audit. Never loads config/.env or contacts a provider.

Runs real prompt assemblers up to their first completion using a capture-only
transport. Actor post-scope envelopes require a named PRIVATE decision choice;
the synthetic neutral choice here is a boundary illustration, not a model result.
"""
from __future__ import annotations
import argparse, asyncio, ast, copy, hashlib, json, sys, types
from pathlib import Path

BACKEND = Path(r'E:\che\apricot\tw_teaching_system_new_bak2')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
# Do not import operator configuration or read secrets. Safe source defaults.
safe_config = types.ModuleType('config')
safe_config.CUHK_DI_DOCTOR_SCOPE_REASONING = 'low'
safe_config.CUHK_DI_DOCTOR_REVIEW_REASONING = 'low'
safe_config.CUHK_DI_LIVE_DOCTOR_SCOPE = True
sys.modules['config'] = safe_config

from schemas.cuhk_drug_information import DrugInformationDialogueTurn
from services.cuhk_station_policy import apply_mode, actor_policy, guidance_for, role_reminder
from services import cuhk_model_transport as transport
from services.cuhk_drug_information_judge import judge_rubric
from services.cuhk_drug_information_agent import ACTOR, Draft, source_facts, doctor_reply
from services.cuhk_doctor_role import prepare_payload, IDENTITY, VERSION as DOCTOR_VERSION, RULES, VERIFY
from services.cuhk_patient_role import actor_prompt
from services.cuhk_drug_information_fidelity import source_obligations

TOKENIZER_PATH=OUT/'tokenizer.json'
TOKENIZER=None
if TOKENIZER_PATH.exists():
    from tokenizers import Tokenizer
    TOKENIZER=Tokenizer.from_file(str(TOKENIZER_PATH))

def token_count(text):
    return len(TOKENIZER.encode(text,add_special_tokens=False).ids) if TOKENIZER else None

class Captured(BaseException):
    def __init__(self, kwargs): self.kwargs = kwargs

async def capture(_client, **kwargs): raise Captured(kwargs)

transport.complete = capture
# Agent binds transport at import; replace that imported name too.
import services.cuhk_drug_information_agent as agent
agent.complete = capture

async def get_first(awaitable):
    try: await awaitable
    except Captured as captured: return captured.kwargs
    raise RuntimeError('Expected a first model request')

def live_constants():
    # Evaluate exact constants without importing live module/provider dependencies.
    tree = ast.parse((BACKEND/'services/cuhk_drug_information_live_reply.py').read_text(encoding='utf-8'))
    env = {'ACTOR':ACTOR, 'Draft':Draft, 'json':json}
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'LIVE_ACTOR','_OUTPUT_CONTRACT'} for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]),'live_constants','exec'), env)
    return env['LIVE_ACTOR'],env['_OUTPUT_CONTRACT']

LIVE_ACTOR, OUTPUT_CONTRACT = live_constants()

def summarize(request):
    messages=request['messages']
    payload=json.loads(messages[1]['content'])
    compact=json.dumps(payload,ensure_ascii=False)!=messages[1]['content']
    def value_json(value):
        return json.dumps(value,ensure_ascii=False,separators=(',',':')) if compact else json.dumps(value,ensure_ascii=False)
    return {'system_chars':len(messages[0]['content']), 'user_chars':len(messages[1]['content']),
            'messages_content_chars':sum(len(m['content']) for m in messages),
            'system_reference_tokens':token_count(messages[0]['content']),
            'user_reference_tokens':token_count(messages[1]['content']),
            'messages_content_reference_tokens_sum':sum(token_count(m['content']) for m in messages) if TOKENIZER else None,
            'messages_content_reference_tokens_concatenated_newline':token_count('\n'.join(m['content'] for m in messages)),
            'max_output_tokens':request.get('max_tokens'),
            'payload_components_chars':{k:len(value_json(v)) for k,v in payload.items()},
            'payload_components_reference_tokens':{k:token_count(value_json(v)) for k,v in payload.items()},
            'tokenizer':'Qwen/Qwen3-8B b968826d9c46dd6066d109eabc6255188de91218; no chat template/special tokens; not Gemini billing counts'}

async def build(case,history,current_text):
    judge=await get_first(judge_rubric(case,history,None,'OFFLINE_AUDIT_ONLY',require_report=True))
    base={'case_id':case['case_id'],'opening':False,'source_facts':source_facts(case),
          'dialogue_policy':case['dialogue_policy'],'guidance_permissions':guidance_for(case,history,current_text),
          **actor_policy(case),'conversation_memory':[
              {'turn_index':i,'role':t.role,'text':t.text,'prompt_codes':list(t.prompt_codes)} for i,t in enumerate(history)]}
    base['conversation_memory'].append({'turn_index':len(history),'role':'student','text':current_text,'prompt_codes':[]})
    role=case.get('counterpart_role','doctor')
    private=None
    if role=='doctor':
        private=await get_first(prepare_payload(case,copy.deepcopy(base),None,'OFFLINE_AUDIT_ONLY'))
        facts={k:v for k,v in base['source_facts'].items() if k.startswith(('doctor.','interaction.')) or k in IDENTITY}
        # These are exact outputs for a hypothetical valid Plan with no challenge.
        base.update({'source_facts':facts,'source_obligations':[], 'doctor_disclosure_contract':DOCTOR_VERSION,
          'retrieval_scope':{'mode':'dialogue','selected':list(facts),'unknown_questions':[]},
          'guidance_permissions':{},'dialogue_policy':{'challenge_rules':[],
              'information_access':'Pharmacist reads hospital record independently; doctor does not recite or verify entries.'},
          'disclosure_instruction':RULES})
    actor={'model':'OFFLINE_AUDIT_ONLY','temperature':.3,'max_tokens':4500,'stream':True,
           'messages':[{'role':'system','content':actor_prompt(case,LIVE_ACTOR)+role_reminder(case)+OUTPUT_CONTRACT},
                       {'role':'user','content':json.dumps(base,ensure_ascii=False,separators=(',',':'))}]}
    # Capture the real reviewed-path actor request. For doctors alone, provide a
    # static no-challenge Plan solely to pass the private decision boundary;
    # every subsequent call is capture-only. Patient joint scope remains exact.
    async def conditional_transport(_client, **kwargs):
        if kwargs.get('messages',[{}])[0].get('content') == VERIFY:
            plan={'mode':'dialogue','prompt_code':'','rule_index':None,'trigger_quote':''}
            return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='stop',
                    message=types.SimpleNamespace(content=json.dumps(plan)))])
        return await capture(_client,**kwargs)
    transport.complete=conditional_transport
    try:
        reviewed_actor=await get_first(doctor_reply(case,history,current_text,None,
                'OFFLINE_AUDIT_ONLY',combine_scope=True))
    finally:
        transport.complete=capture
    requests={'judge_initial_require_report':judge,'live_actor_after_neutral_scope':actor,
              'reviewed_actor_after_neutral_scope':reviewed_actor}
    if private: requests['private_doctor_verify_initial']=private
    return requests

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--history-json',type=Path,help='JSON map case ID -> list of role/text/prompt_codes turns')
    parser.add_argument('--current-text',default='')
    parser.add_argument('--label',default='empty_history_baseline')
    args=parser.parse_args()
    history_map=json.loads(args.history_json.read_text(encoding='utf-8')) if args.history_json else {}
    inventory=[]
    for path in sorted((BACKEND/'data/cuhk_drug_information_cases').glob('case_*.json')):
        raw=json.loads(path.read_text(encoding='utf-8'))
        case=apply_mode(raw,raw['case_id'],'assessment')
        history=[DrugInformationDialogueTurn.model_validate(t) for t in history_map.get(case['case_id'],[])]
        requests=await build(case,history,args.current_text)
        stem=f'{args.label}_{case["case_id"]}'
        target=OUT/(stem+'_messages.json')
        target.write_text(json.dumps(requests,ensure_ascii=False,indent=2),encoding='utf-8')
        inventory.append({'case_id':case['case_id'],'version':case['version'], 'counterpart_role':case.get('counterpart_role','doctor'),
          'history_turns':len(history),'history_raw_text_chars':sum(len(t.text) for t in history),
          'rubric_items':len(case['rubric']),'case_json_chars':len(json.dumps(raw,ensure_ascii=False,separators=(',',':'))),
          'case_components_chars':{k:len(json.dumps(v,ensure_ascii=False,separators=(',',':'))) for k,v in raw.items()},
          'requests_file':str(target),'requests':{k:summarize(v) for k,v in requests.items()}})
    summary={'measurement':'Exact prompt strings before any provider call; characters not tokens.',
      'neutral_scope_warning':'Private doctor decision is not executed; actor neutral-scope envelopes illustrate no-challenge Plan only.',
      'configuration':'Config module stub prevents .env/operator-secret reads; no actual model identity or context window asserted.',
      'label':args.label,'cases':inventory}
    output=OUT/(args.label+'_request_audit.json')
    output.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(output),'cases':[{'id':c['case_id'],'requests':{k:v['messages_content_chars'] for k,v in c['requests'].items()}} for c in inventory]},ensure_ascii=False))

if __name__=='__main__': asyncio.run(main())
