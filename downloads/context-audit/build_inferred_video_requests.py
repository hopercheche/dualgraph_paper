"""Reconstruct ten CURRENT judge prompts from PRIOR inferred role spans.

This is a conditional offline prompt-envelope measurement, not recorded live
requests, new model output, human verified speaker attribution or a complete
verbatim conversation. Unsupported role spans remain audited as excluded text.
"""
import asyncio, json, hashlib
from pathlib import Path
import build_actual_requests as builder

VIDEO_AUDIT=builder.OUT/'video_materials_audit.json'
CASE_MAPPING={'case1_fungal_toe':'case_1_fungal_toe.json',
              'case2_migraine':'case_2_migraine.json'}

def inferred_history(data):
    turns=[];excluded=[];merge_allowed=False
    for unit in data['labeled_units']:
        role=unit['inferred_role'];text=unit['text']
        if role not in {'student','doctor'}:
            excluded.append({'unit_id':unit['id'],'role':role,'chars':len(text),
                    'reference_tokens':builder.token_count(text)})
            merge_allowed=False
            continue
        if merge_allowed and turns and turns[-1]['role']==role:
            turns[-1]['text']+=text
        else: turns.append({'role':role,'text':text,'prompt_codes':[]})
        merge_allowed=True
    return turns,excluded

async def main():
    videos=json.loads(VIDEO_AUDIT.read_text(encoding='utf-8'))['videos']
    results=[]
    for v in videos:
        if v['case'] not in CASE_MAPPING:continue
        source=Path(v['role_labels_file'])
        data=json.loads(source.read_text(encoding='utf-8'))
        turns,excluded=inferred_history(data)
        history=[builder.DrugInformationDialogueTurn.model_validate(t) for t in turns]
        raw=json.loads((builder.BACKEND/'data/cuhk_drug_information_cases'/CASE_MAPPING[v['case']]).read_text(encoding='utf-8'))
        case=builder.apply_mode(raw,raw['case_id'],'assessment')
        req=await builder.get_first(builder.judge_rubric(case,history,None,'OFFLINE_AUDIT_ONLY',require_report=True))
        # Build each first PRIVATE doctor-decision prompt without generating a
        # Plan. Its full patient facts/history precede all model scope filtering.
        private_turns=[];peak_request=None;peak_tokens=-1
        for turn_index,turn in enumerate(history):
            if turn.role!='student':continue
            prefix=history[:turn_index]
            payload={'case_id':case['case_id'],'opening':False,
              'source_facts':builder.source_facts(case),'dialogue_policy':case['dialogue_policy'],
              'guidance_permissions':builder.guidance_for(case,prefix,turn.text),**builder.actor_policy(case),
              'conversation_memory':[{'turn_index':i,'role':t.role,'text':t.text,
                  'prompt_codes':list(t.prompt_codes)} for i,t in enumerate(prefix)]}
            payload['conversation_memory'].append({'turn_index':turn_index,'role':'student',
                                                  'text':turn.text,'prompt_codes':[]})
            private=await builder.get_first(builder.prepare_payload(case,payload,None,'OFFLINE_AUDIT_ONLY'))
            summary=builder.summarize(private)
            private_turns.append({'current_student_turn_index':turn_index,'prefix_history_turns':len(prefix),
                                 'request_summary':summary})
            tokens=summary['messages_content_reference_tokens_concatenated_newline']
            if tokens>peak_tokens:peak_tokens=tokens;peak_request=private
        stem=v['case']+'_'+v['video']
        target=builder.OUT/(stem+'_inferred_roles_judge_messages.json')
        target.write_text(json.dumps(req,ensure_ascii=False,indent=2),encoding='utf-8')
        peak_target=builder.OUT/(stem+'_inferred_roles_private_verify_peak_messages.json')
        peak_target.write_text(json.dumps(peak_request,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append({'video_id':stem,'case_id':case['case_id'],'source_role_labels_file':str(source),
            'source_role_labels_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'human_verified':data.get('human_verified',False),'source_role_method':'Prior LLM inference from ASR text; no audio sent',
            'history_turns_after_contiguous_merge':len(history),
            'history_included_text_chars':sum(len(t.text) for t in history),
            'history_excluded_units':excluded,'history_excluded_text_chars':sum(r['chars'] for r in excluded),
            'prompt_code_status':'Not inferred; [] placeholders. Judge conversation envelope itself excludes prompt_codes.',
            'request_file':str(target),'request_summary':builder.summarize(req),
            'private_verify_per_student_turn':private_turns,
            'private_verify_peak_reference_tokens':peak_tokens,
            'private_verify_peak_request_file':str(peak_target)})
    result={'scope':'Ten current first judge request envelopes reconstructed OFFLINE with prior inferred student/doctor spans.',
      'not_actual_recorded_provider_requests':True,'no_model_calls':True,'no_config_or_secret_reads':True,
      'limitations':['ASR not human verified. Unsupported mixed/uncertain/outside/unintelligible roles excluded and counted separately.',
       'No claim of complete dialogue or gold speaker annotation. Last two stations have no role labels and no full judge reconstruction.',
       'Qwen fixed tokenizer is reference counts; actual model-token usage and chat wrapper not measured.'],
      'videos':results}
    target=builder.OUT/'inferred_video_request_audit.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(target),'videos':[{ 'id':v['video_id'],'turns':v['history_turns_after_contiguous_merge'],
       'chars':v['request_summary']['messages_content_chars'],'reference_tokens':v['request_summary']['messages_content_reference_tokens_concatenated_newline'],
       'private_verify_peak_reference_tokens':v['private_verify_peak_reference_tokens']} for v in results]},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
