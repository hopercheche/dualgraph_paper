"""Count original CUHK documents locally. No source writes or model calls."""
from __future__ import annotations

import collections
import hashlib
import json
import platform
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import fitz
import docx
import tokenizers
from tokenizers import Tokenizer

ROOT = Path(r'E:\che\apricot\hoper\CUHK项目')
OUT = Path(__file__).resolve().parent
SELECTED = ROOT / 'OneDrive_2026-09-09' / 'Sample cases Apricot'
STATIONS = {
    'case1_fungal_toe': ('Drug Info Case 1 Fungal Toe', 'Drug Info Case 1 Fungal Toe-20260901T121859Z-1-001', 'cuhk_di_01_fungal_toe'),
    'case2_migraine': ('Drug Info Case 2 Migrane', 'Drug Info Case 2 Migrane-20260901T122239Z-1-001', 'cuhk_di_02_migraine'),
    'case3_diuretics': ('Patient Drug Counselling Case 1 Diruetics', 'Patient Drug Counselling Case 1 Diruetics-20260901T122422Z-1-001', 'cuhk_di_03_diuretics_counseling'),
    'case4_mtx': ('Patient Drug Counselling Case 2 MTX', 'Patient Drug Counselling Case 2 MTX-20260901T122454Z-1-001', 'cuhk_di_04_mtx_counseling'),
}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
EP = 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
TOKENIZER = Tokenizer.from_file(str(OUT / 'tokenizer.json'))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def count(text):
    return len(TOKENIZER.encode(text, add_special_tokens=False).ids)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def normalize_text(text):
    # Preserve all lexical content and paragraph/line ordering. Normalize whitespace only.
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


def xml_text(data):
    tree = ET.fromstring(data)
    pieces = []
    paragraphs = 0
    def visit(node):
        nonlocal paragraphs
        if node.tag == f'{{{MC}}}AlternateContent':
            # A Word-compatible modern choice and its fallback describe the
            # same object. Count a single representation, never both.
            choice = node.find(f'{{{MC}}}Choice')
            selected = choice if choice is not None else node.find(f'{{{MC}}}Fallback')
            if selected is not None:
                visit(selected)
            return
        if node.tag == f'{{{W}}}del':
            return
        if node.tag in (f'{{{W}}}t', f'{{{M}}}t'):
            pieces.append(node.text or '')
            return
        if node.tag == f'{{{W}}}tab':
            pieces.append('\t')
            return
        if node.tag in (f'{{{W}}}br', f'{{{W}}}cr'):
            pieces.append('\n')
            return
        start = len(pieces)
        for child in node:
            visit(child)
        if node.tag == f'{{{W}}}p' and any(p.strip() for p in pieces[start:]):
            paragraphs += 1
            pieces.append('\n')
    visit(tree)
    # Normalize empty paragraph lines only; each textual run is visited once,
    # including nested text boxes, and source words/numbers remain unchanged.
    text = '\n'.join(line for line in ''.join(pieces).splitlines() if line.strip())
    return normalize_text(text), paragraphs


def extract_docx(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        primary_parts = [p for p in names if p == 'word/document.xml' or re.fullmatch(r'word/(header\d*|footer\d*|footnotes|endnotes)\.xml', p)]
        primary_parts.sort(key=lambda p: (p != 'word/document.xml', p))
        part_rows, texts = [], []
        for part in primary_parts:
            text, paragraphs = xml_text(z.read(part))
            part_rows.append({'part':part,'characters':len(text),'reference_tokens':count(text),'nonempty_paragraphs':paragraphs})
            if text:
                texts.append(text)
        text = '\n\n'.join(texts)
        declared_pages = None
        if 'docProps/app.xml' in names:
            meta = ET.fromstring(z.read('docProps/app.xml'))
            node = meta.find(f'{{{EP}}}Pages')
            if node is not None and node.text and node.text.isdigit():
                declared_pages = int(node.text)
        comments_text = xml_text(z.read('word/comments.xml'))[0] if 'word/comments.xml' in names else ''
        body = ET.fromstring(z.read('word/document.xml'))
        return text, {'extraction_method':'OOXML textual runs w:t and m:t traversed once in body paragraphs/tables/textboxes, headers/footers and notes; modern AlternateContent Choice selected once, fallback duplicate excluded; whitespace-only lines removed; no OCR','included_parts':part_rows,'word_declared_pages':declared_pages,'word_page_count_status':'last-saved metadata only; not rendered or verified pagination','body_tables':len(list(body.iter(f'{{{W}}}tbl'))),'embedded_media_files':len([p for p in names if p.startswith('word/media/')]),'comments_chars_not_in_primary_count':len(comments_text),'comments_reference_tokens_not_in_primary_count':count(comments_text),'limitations':['Embedded images are not OCRed.','Headers/footers are counted once per OOXML part, not multiplied by rendered pages.','Comments, deleted-text runs and field instruction strings are excluded from primary text.','Modern OOXML compatibility Choice is used without layout rendering; extraction does not validate appearance.']}


def extract_pdf(path):
    page_rows, texts = [], []
    with fitz.open(path) as pdf:
        for i, page in enumerate(pdf):
            text = normalize_text(page.get_text('text', sort=True))
            texts.append(text)
            page_rows.append({'page':i+1,'characters':len(text),'reference_tokens':count(text),'images':len(page.get_images())})
        page_count = len(pdf)
    return '\n\n'.join(texts), {'extraction_method':'PyMuPDF native PDF text page.get_text(text, sort=True); page text joined by two newlines; no OCR','pdf_pages':page_count,'pdf_pages_with_zero_native_text':[p['page'] for p in page_rows if p['characters']==0],'pdf_pages_below_50_characters':[p['page'] for p in page_rows if p['characters']<50],'pdf_pages_with_image_assets_not_OCRed':[p['page'] for p in page_rows if p['images']],'pdf_image_assets_note':'May include repeated logos; asset presence is not evidence of unrecognized clinical text. Figure meaning is not measured as tokens.','per_page':page_rows,'limitations':['Native extraction includes repeated headers/footers, bibliographies and broad monograph content.','Figures and raster-only text are not OCRed; extraction is not a visual completeness audit.','Line wrapping and PDF reading order affect reference token counts.']}


def category(path):
    if path.suffix.lower()=='.pdf':
        return 'professional_reference'
    if 'assessment' in path.name.lower():
        return 'teacher_assessment'
    if 'scenario' in path.name.lower():
        return 'scenario'
    if 'exhibit' in path.name.lower():
        return 'exhibit'
    return 'other'


def main():
    allowed = {'.docx','.pdf'}
    file_rows, docs, text_by_sha = [], [], {}
    for case,(folder,old_folder,app_id) in STATIONS.items():
        selected_files = sorted(p for p in (SELECTED/folder).rglob('*') if p.is_file() and p.suffix.lower() in allowed)
        old_files = sorted(p for p in (ROOT/old_folder).rglob('*') if p.is_file() and p.suffix.lower() in allowed)
        for group,paths in [('selected',selected_files),('older_copy',old_files)]:
            for path in paths:
                digest=sha_bytes(path.read_bytes())
                file_rows.append({'case':case,'group':group,'path':str(path),'size_bytes':path.stat().st_size,'sha256':digest})
                if group != 'selected':
                    continue
                if path.suffix.lower()=='.docx':
                    text,details=extract_docx(path)
                else:
                    text,details=extract_pdf(path)
                text_by_sha[digest]=text
                docs.append({'case':case,'app_case_id':app_id,'category':category(path),'file':path.name,'path':str(path),'source_sha256':digest,'size_bytes':path.stat().st_size,'extracted_text_chars':len(text),'extracted_text_chars_without_whitespace':sum(not c.isspace() for c in text),'extracted_text_sha256':sha_bytes(text.encode('utf8')),'reference_tokens':count(text),**details})
    sha_paths=collections.defaultdict(list)
    for row in file_rows:
        sha_paths[row['sha256']].append(row)
    duplicates=[{'sha256':s,'files':paths} for s,paths in sha_paths.items() if len(paths)>1]
    selected_sha={d['source_sha256'] for d in docs}
    older_variants=[]
    for row in file_rows:
        if row['group']!='older_copy' or row['sha256'] in selected_sha:
            continue
        path=Path(row['path'])
        text,details=extract_docx(path) if path.suffix.lower()=='.docx' else extract_pdf(path)
        text_sha=sha_bytes(text.encode('utf8'))
        match=next((d for d in docs if d['case']==row['case'] and d['file']==path.name),None)
        older_variants.append({'case':row['case'],'category':category(path),'file':path.name,'path':str(path),'source_sha256':row['sha256'],'extracted_text_chars':len(text),'reference_tokens':count(text),'extracted_text_sha256':text_sha,'matching_selected_file':match['path'] if match else None,'extracted_text_identical_to_selected':bool(match and match['extracted_text_sha256']==text_sha),'included_in_selected_station_pack':False,**details})
    material=load(OUT/'material_token_audit.json')
    cases_by_id={c['case_id']:c for c in material['case_materials']}
    baseline=load(OUT/'empty_history_baseline_request_audit.json')
    baseline_by_id={c['case_id']:c for c in baseline['cases']}
    transcripts=load(ROOT/'.codex_tmp'/'case_audit'/'videos'/'transcripts.json')
    station_rows=[]
    for case,(folder,old_folder,app_id) in STATIONS.items():
        case_docs=[d for d in docs if d['case']==case]
        # De-duplicate identical files only within this station; preserve cross-station ownership.
        unique=list({d['source_sha256']:d for d in case_docs}.values())
        packs={}
        for cat in ['teacher_assessment','professional_reference','scenario','exhibit','other']:
            subset=[d for d in unique if d['category']==cat]
            joined='\n\n'.join(text_by_sha[d['source_sha256']] for d in subset)
            packs[cat]={'documents':len(subset),'file_paths':[d['path'] for d in subset],'standalone_reference_tokens_sum':sum(d['reference_tokens'] for d in subset),'concatenated_reference_tokens':count(joined),'text_chars':len(joined),'pdf_pages':sum(d.get('pdf_pages',0) for d in subset),'word_declared_pages_sum':sum(d.get('word_declared_pages') or 0 for d in subset),'word_declared_pages_status':'metadata only; not verified rendered pagination'}
        full='\n\n'.join(text_by_sha[d['source_sha256']] for d in unique)
        combinations=[]
        for t in transcripts:
            if t['case']!=case:
                continue
            speech='\n'.join(c['transcript'].strip() for c in t['chunks'] if not c.get('no_speech') and c.get('transcript') and c['transcript']!='[无可辨识语音]')
            combinations.append({'video':t['video'],'speech_reference_tokens':count(speech),'hypothetical_source_pack_plus_recognized_speech_reference_tokens':count(full+'\n\n'+speech)})
        app=cases_by_id[app_id]
        actual=baseline_by_id[app_id]['requests']['judge_initial_require_report']
        station_rows.append({'case':case,'folder':str(SELECTED/folder),'source_document_count':len(case_docs),'unique_assets_within_station':len(unique),'docfiles':[{k:d.get(k) for k in ['file','category','path','source_sha256','extracted_text_chars','reference_tokens','pdf_pages','word_declared_pages']} for d in unique],'category_packs':packs,'hypothetical_all_source_documents_concatenated_reference_tokens':count(full),'hypothetical_all_source_documents_plus_recognized_speech_min_reference_tokens':min(c['hypothetical_source_pack_plus_recognized_speech_reference_tokens'] for c in combinations),'hypothetical_all_source_documents_plus_recognized_speech_max_reference_tokens':max(c['hypothetical_source_pack_plus_recognized_speech_reference_tokens'] for c in combinations),'hypothetical_pack_plus_speech_by_video':combinations,'comparison_to_current_application':{'app_case_file':app['file'],'application_rubric_items':app['rubric_items'],'serialized_rubric_field_reference_tokens_in_report_request':actual['payload_components_reference_tokens']['rubric'],'serialized_teaching_key_field_reference_tokens_in_report_request':actual['payload_components_reference_tokens']['teaching_key'],'not_original_teacher_form_fulltext':True,'not_entire_professional_reference_pack':True}})
    output={'scope':'Only the four CUHK OneDrive station folders and their mapped four older copies; original DOCX assessment/scenario/exhibit and PDF reference assets. Sources read only.','tokenizer':load(OUT/'tokenizer_manifest.json'),'extraction_runtime':{'python':platform.python_version(),'pymupdf':fitz.__version__,'python_docx_available':docx.__version__,'tokenizers':tokenizers.__version__},'counting_contract':{'unit':'Qwen3-8B reference text tokens','add_special_tokens':False,'chat_template_or_system_instructions_included':False,'provider_usage':False,'full_pack':'Concatenate each unique extracted source document within a station in sorted file-path order, separated by two newlines; no relevance filtering.','not_current_request':True,'not_KG_serialization':True,'not_claimed_required_knowledge_for_each_turn':True,'professional_reference_pack':'Broad monographs and patient education PDFs, including repeated page furniture and bibliography; naive all-document text-loading scenario only.','speech':'Existing raw ASR recognized chunks stripped of outer whitespace, joined with newline; timestamps and no-words placeholders excluded; unverified transcript.'},'summary':{'selected_document_files':len(docs),'selected_docx_files':sum(d['path'].lower().endswith('.docx') for d in docs),'selected_pdf_files':sum(d['path'].lower().endswith('.pdf') for d in docs),'globally_unique_selected_assets':len({d['source_sha256'] for d in docs}),'global_pdf_page_count_unique_assets':sum(d.get('pdf_pages',0) for d in {d['source_sha256']:d for d in docs}.values()),'all_scoped_file_copies':len(file_rows),'globally_unique_assets_including_older_variants':len({r['sha256'] for r in file_rows}),'older_nonidentical_binary_variants':len(older_variants),'duplicate_byte_sha_groups':len(duplicates)},'limitations':['These hypothetical all-document packs were not sent to a model and are not a measured context overflow.','A reference tokenizer cannot establish the configured provider context limit or billing usage.','All-document packs contain material irrelevant to some station decisions, repeated content, broader doses/indications and bibliography; their entire content is not required at every turn.','Source PDFs are reference documents, not an implemented pharmacy knowledge graph or serialized retrieved subgraph.','Native text extraction does not count meaning in figures or raster-only text; Word page metadata is not an actual rendered page count.','Current application rubric items consolidate teacher instructions, and teaching_key is a short curated answer; small application fields do not measure the full original source package.'],'per_station':station_rows,'documents':docs,'older_nonidentical_binary_variant_documents':older_variants,'duplicate_byte_sha_groups':duplicates,'scoped_file_inventory':file_rows}
    destination=OUT/'source_document_token_audit.json'
    destination.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'summary':output['summary'],'per_station':[{k:r[k] for k in ['case','source_document_count','hypothetical_all_source_documents_concatenated_reference_tokens','hypothetical_all_source_documents_plus_recognized_speech_min_reference_tokens','hypothetical_all_source_documents_plus_recognized_speech_max_reference_tokens']} | {'categories':{k:{'n':v['documents'],'tokens':v['concatenated_reference_tokens'],'pdf_pages':v['pdf_pages'],'word_declared_pages_sum':v['word_declared_pages_sum']} for k,v in r['category_packs'].items()},'current_application':r['comparison_to_current_application']} for r in station_rows],'output':str(destination)},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
