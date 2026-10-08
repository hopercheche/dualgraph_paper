from __future__ import annotations

import collections
import hashlib
import json
import statistics
import struct
import wave
from pathlib import Path

ROOT = Path(r'E:\che\apricot\hoper\CUHK项目')
OUT = Path(r'E:\che\apricot\hoper\tmp\egj_context_20261003')
VIDEO_ROOT = ROOT / '.codex_tmp' / 'case_audit' / 'videos'
SOURCE_ROOT = ROOT / 'OneDrive_2026-09-09' / 'Sample cases Apricot'
ROLE_ROOT = ROOT / 'outputs' / 'CUHK_原表与示范视频评分复核_20260922'


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def mp4_duration(path: Path):
    # Parse only ISO BMFF container metadata, never decode or send audio.
    with path.open('rb') as f:
        def boxes(start, end):
            pos = start
            while pos + 8 <= end:
                f.seek(pos)
                head = f.read(8)
                size, typ = struct.unpack('>I4s', head)
                header_len = 8
                if size == 1:
                    size = struct.unpack('>Q', f.read(8))[0]
                    header_len = 16
                elif size == 0:
                    size = end - pos
                if size < header_len or pos + size > end:
                    raise ValueError(f'Invalid MP4 box at {pos}')
                yield typ, pos + header_len, pos + size
                pos += size
        for typ, start, end in boxes(0, path.stat().st_size):
            if typ != b'moov':
                continue
            for child, cstart, cend in boxes(start, end):
                if child != b'mvhd':
                    continue
                f.seek(cstart)
                data = f.read(min(40, cend - cstart))
                if data[0] == 0:
                    timescale, duration = struct.unpack('>II', data[12:20])
                elif data[0] == 1:
                    timescale = struct.unpack('>I', data[20:24])[0]
                    duration = struct.unpack('>Q', data[24:32])[0]
                else:
                    raise ValueError('Unknown mvhd version')
                return duration / timescale
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    transcripts = load(VIDEO_ROOT / 'transcripts.json')
    video_map = {(x['Case'], f"v{x['Index']:02d}"): x for x in load(VIDEO_ROOT / 'video_map.json')}
    paths = sorted(SOURCE_ROOT.rglob('*.mp4'))
    original_paths = sorted(p for d in ROOT.iterdir() if d.is_dir() and '-20260901' in d.name for p in d.rglob('*.mp4'))
    extra_paths = sorted((ROOT / 'drugs_info_case1').glob('*.mp4'))
    all_paths = paths + original_paths + extra_paths
    sizes = collections.Counter(p.stat().st_size for p in all_paths)
    file_rows = []
    for p in all_paths:
        size = p.stat().st_size
        file_rows.append({'path': str(p), 'size_bytes': size, 'movie_duration_seconds': mp4_duration(p), 'sha256': sha(p) if sizes[size] > 1 else None, 'group': 'onedrive_selected' if p in paths else 'original' if p in original_paths else 'extra'})
    bypath = {x['path']: x for x in file_rows}
    rows = []
    for t in transcripts:
        case, vid = t['case'], t['video']
        meta = video_map[case, vid]
        with wave.open(meta['Audio'], 'rb') as w:
            wav_duration = w.getnframes() / w.getframerate()
        chunks = sorted(t['chunks'], key=lambda x:x['start_seconds'])
        spoken = [c['transcript'] for c in chunks if not c.get('no_speech') and c.get('transcript') != '[无可辨识语音]']
        raw = '\n'.join(spoken)
        placeholders = [c for c in chunks if c.get('no_speech') or c.get('transcript') == '[无可辨识语音]']
        gaps = [{'after_chunk': a['chunk'], 'before_chunk': b['chunk'], 'seconds': b['start_seconds']-a['end_seconds']} for a,b in zip(chunks, chunks[1:]) if abs(b['start_seconds']-a['end_seconds']) > 0.001]
        row = {'case':case,'video':vid,'file':t['file'],'old_source':t['source'],'transcript_file':t['transcript_file'],'audio_file':meta['Audio'],'wav_duration_seconds':round(wav_duration,6),'movie_duration_seconds':bypath[t['source']]['movie_duration_seconds'],'chunk_count':len(chunks),'machine_complete_flag':t['complete'],'time_coverage_start_seconds':chunks[0]['start_seconds'],'time_coverage_end_seconds':chunks[-1]['end_seconds'],'gaps':gaps,'empty_chunk_count':sum(not bool(c['transcript']) for c in chunks),'placeholder_chunk_count':len(placeholders),'placeholder_seconds':sum(c['end_seconds']-c['start_seconds'] for c in placeholders),'spoken_chars_with_newlines':len(raw),'spoken_chars_without_whitespace':sum(not ch.isspace() for ch in raw),'spoken_text_sha256':hashlib.sha256(raw.encode('utf-8')).hexdigest(),'human_verified':False,'speaker_turns_status':'not_diarized'}
        role_path = ROLE_ROOT / f'{case}_{vid}_原文.json'
        if role_path.exists():
            role = load(role_path)
            units = role['labeled_units']
            role_counts = collections.Counter(u['inferred_role'] for u in units)
            runs = []
            for u in units:
                if not runs or runs[-1] != u['inferred_role']:
                    runs.append(u['inferred_role'])
            row.update({'role_labels_file':str(role_path),'role_label_method':'LLM inference from ASR text; no audio sent','human_verified':role['human_verified'],'text_unit_count':len(units),'text_unit_roles':dict(role_counts),'inferred_contiguous_runs_all_roles':len(runs),'inferred_contiguous_runs_student_or_doctor':sum(r in ['student','doctor'] for r in runs),'speaker_turns_status':'unverified LLM role runs; not ground-truth turns'})
        rows.append(row)
    duplicate_groups = collections.defaultdict(list)
    for x in file_rows:
        if x['sha256']:
            duplicate_groups[x['sha256']].append(x['path'])
    byte_duplicates = [dict(sha256=k,paths=v) for k,v in duplicate_groups.items() if len(v)>1]
    for row in rows:
        group = next((d for d in byte_duplicates if row['old_source'] in d['paths']), None)
        selected = next((p for p in group['paths'] if p.startswith(str(SOURCE_ROOT))), None) if group else None
        row.update({'selected_source':selected,'source_sha256':group['sha256'] if group else None,'byte_identical_original_and_onedrive':bool(selected)})
    summary=[]
    for case in sorted({r['case'] for r in rows}):
        subset=[r for r in rows if r['case']==case]
        summary.append({'case':case,'videos':len(subset),'duration_min_seconds':min(r['wav_duration_seconds'] for r in subset),'duration_median_seconds':statistics.median(r['wav_duration_seconds'] for r in subset),'duration_max_seconds':max(r['wav_duration_seconds'] for r in subset),'spoken_chars_min':min(r['spoken_chars_with_newlines'] for r in subset),'spoken_chars_median':statistics.median(r['spoken_chars_with_newlines'] for r in subset),'spoken_chars_max':max(r['spoken_chars_with_newlines'] for r in subset),'placeholder_chunks_total':sum(r['placeholder_chunk_count'] for r in subset),'placeholder_seconds_total':sum(r['placeholder_seconds'] for r in subset),'all_time_intervals_contiguous':all(not r['gaps'] and r['time_coverage_start_seconds']==0 and abs(r['time_coverage_end_seconds']-r['wav_duration_seconds'])<0.001 for r in subset)})
    audit = {'scope':'18 existing machine transcripts; source MP4 container and extracted WAV durations; no new ASR/LLM invocation','token_counts_status':'Not computed by this script; character counts are not token counts','limitations':['Machine chunk intervals cover extracted WAV; this does not establish every utterance was recognized.','ASR no-words errors were converted to nonempty placeholders; complete:true therefore means no empty chunk strings, not verified verbatim completeness.','No human-verified transcript or speaker-turn annotation found in these artifacts.','Video duration includes silent search time, preparation, and any outside-station speech; it is not verified station interaction time.'],'source_manifest':str(VIDEO_ROOT/'transcripts.json'),'corpus_summary':{'videos':len(rows),'chunks':sum(r['chunk_count'] for r in rows),'placeholder_chunks':sum(r['placeholder_chunk_count'] for r in rows),'placeholder_seconds':sum(r['placeholder_seconds'] for r in rows),'duration_seconds':sum(r['wav_duration_seconds'] for r in rows),'duration_median_seconds':statistics.median(r['wav_duration_seconds'] for r in rows),'all_selected_sources_byte_match_original':all(r['byte_identical_original_and_onedrive'] for r in rows)},'per_station':summary,'videos':rows,'file_inventory':file_rows,'byte_identical_duplicate_groups':byte_duplicates}
    (OUT/'video_materials_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'per_station':summary,'videos':[{k:r.get(k) for k in ['case','video','wav_duration_seconds','movie_duration_seconds','chunk_count','placeholder_chunk_count','spoken_chars_with_newlines','inferred_contiguous_runs_student_or_doctor']} for r in rows],'byte_duplicate_groups':len(byte_duplicates),'output':str(OUT/'video_materials_audit.json')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
