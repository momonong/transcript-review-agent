"""Standard-library review contracts. Coverage cues are never correctness verdicts."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
from typing import Any


class ReviewInputError(ValueError):
    pass


ImportError = ReviewInputError
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_MEDIA_BYTES = 512 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewInputError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path: Path | str, limit: int = MAX_JSON_BYTES) -> dict:
    path = Path(path)
    if limit <= 0 or path.stat().st_size > limit:
        raise ReviewInputError('JSON file exceeds size limit')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ReviewInputError('JSON file exceeds size limit')
    try:
        value = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_object,
                           parse_constant=lambda v: (_ for _ in ()).throw(ReviewInputError(f'non-finite JSON value: {v}')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewInputError(f'invalid UTF-8 JSON: {exc}') from exc
    if not isinstance(value, dict):
        raise ReviewInputError('JSON root must be an object')
    return value


def write_json_new(path: Path | str, value: Any) -> None:
    """Exclusive create prevents accidental overwrites of inputs or prior reviews."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded)


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReviewInputError(f'{name} must be a finite number')
    return float(value)


def _hash_file(path: Path, limit: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            total += len(chunk)
            if total > limit:
                raise ReviewInputError('source media exceeds size limit during read')
            digest.update(chunk)
    return digest.hexdigest()


def _validate_document(doc: dict) -> None:
    if not isinstance(doc,dict):
        raise ReviewInputError('original document must be an object')
    source = doc.get('source')
    if not isinstance(source, dict):
        raise ReviewInputError('source must be an object')
    raw = source.get('path')
    if not isinstance(raw, str) or not raw or '\x00' in raw:
        raise ReviewInputError('source.path must be a relative file path')
    if Path(raw).is_absolute() or PureWindowsPath(raw).drive or ':' in raw or '..' in raw.replace('\\', '/').split('/'):
        raise ReviewInputError('absolute paths and path traversal are not allowed in source.path')
    duration = _number(source.get('duration'), 'source.duration')
    if not 0 < duration <= 86400:
        raise ReviewInputError('source.duration must be > 0 and <= 86400 seconds')
    segments = doc.get('segments')
    if not isinstance(segments, list) or not segments or len(segments) > 10000:
        raise ReviewInputError('segments must be a nonempty list with <= 10000 entries')
    ids = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ReviewInputError('each segment must be an object')
        sid = segment.get('id')
        if not isinstance(sid, str) or not sid or len(sid) > 256 or sid in ids:
            raise ReviewInputError('segment IDs must be unique nonempty strings of <= 256 characters')
        ids.add(sid)
        start, end = _number(segment.get('start'), 'start'), _number(segment.get('end'), 'end')
        if not 0 <= start < end <= duration:
            raise ReviewInputError(f'invalid source interval for {sid}')
        if not isinstance(segment.get('text'), str) or len(segment['text']) > 100000:
            raise ReviewInputError(f'text for {sid} must be a string of <= 100000 characters')


def load_import(path: Path | str, *, media_root: Path | str | None = None,
                max_json_bytes: int = MAX_JSON_BYTES,
                max_media_bytes: int = MAX_MEDIA_BYTES) -> dict:
    path = Path(path).resolve()
    doc = read_json(path, max_json_bytes)
    _validate_document(doc)
    root = Path(media_root).resolve() if media_root else path.parent
    media = (root / doc['source']['path']).resolve()
    if not media.is_relative_to(root) or not media.is_file():
        raise ReviewInputError('source must resolve to a file inside media-root')
    if max_media_bytes <= 0 or media.stat().st_size > max_media_bytes:
        raise ReviewInputError('source media exceeds size limit')
    encoded = json.dumps(doc, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
    return {'document': copy.deepcopy(doc), 'source_path': str(media),
            'media_root': str(root), 'input_path': str(path),
            'source_sha256': _hash_file(media, max_media_bytes), 'import_sha256': hashlib.sha256(encoded).hexdigest()}


def coverage_cues(imported: dict) -> list[dict]:
    doc = imported['document']
    ordered = sorted(doc['segments'], key=lambda s: (s['start'], s['end']))
    cues = []
    cursor = 0.0
    previous = None
    for s in ordered:
        if s['start'] > cursor + .01:
            cues.append({'kind': 'gap', 'start': cursor, 'end': s['start'],
                         'reason': 'uncovered timestamp interval, not proof of omitted speech',
                         'status': 'needs_human_review'})
        elif s['start'] < cursor - .01:
            cues.append({'kind': 'overlap', 'start': s['start'], 'end': min(cursor, s['end']),
                         'segments': [previous, s['id']],
                         'reason': 'overlap can be legitimate simultaneous speech, not an error verdict',
                         'status': 'needs_human_review'})
        if s['end'] > cursor:
            cursor, previous = s['end'], s['id']
    if cursor < doc['source']['duration'] - .01:
        cues.append({'kind': 'gap', 'start': cursor, 'end': doc['source']['duration'],
                     'reason': 'uncovered timestamp interval, not proof of omitted speech',
                     'status': 'needs_human_review'})
    return cues


def run_review(imported: dict, tool, *, max_tool_calls: int = 8,
               context_seconds: float = 1.5, max_context_seconds: float = 6.0) -> dict:
    if isinstance(max_tool_calls, bool) or not isinstance(max_tool_calls, int) or max_tool_calls < 0:
        raise ReviewInputError('max_tool_calls must be a nonnegative integer')
    context_seconds = _number(context_seconds, 'context_seconds')
    max_context_seconds = _number(max_context_seconds, 'max_context_seconds')
    if not 0 <= context_seconds <= max_context_seconds <= 30:
        raise ReviewInputError('context must satisfy 0 <= initial <= maximum <= 30 seconds')
    trace, items, calls = [], [], 0
    duration = imported['document']['source']['duration']
    for segment in imported['document']['segments']:
        item = {'segment_id': segment['id'], 'start': segment['start'], 'end': segment['end'],
                'original_text': segment['text'], 'candidate_text': None,
                'status': 'pending', 'reason': 'not_checked', 'evidence': []}
        context = context_seconds
        while True:
            if calls >= max_tool_calls:
                item.update(status='needs_human_review', reason='tool_budget_exhausted')
                trace.append({'action': 'handoff', 'segment_id': segment['id'], 'reason': item['reason']})
                break
            calls += 1
            event = {'action': 'retranscribe', 'call': calls, 'segment_id': segment['id'],
                     'tool': tool.name, 'context_seconds': context,
                     'source_start': max(0, segment['start'] - context),
                     'source_end': min(duration, segment['end'] + context)}
            try:
                result = tool.retranscribe(Path(imported['source_path']), segment, context, duration)
                if not isinstance(result, dict) or not isinstance(result.get('resolved'), bool):
                    raise ValueError('tool returned an invalid result contract')
                text = result.get('text')
                if text is not None and (not isinstance(text, str) or len(text) > 100000):
                    raise ValueError('tool hypothesis must be bounded text')
                event.update(outcome='hypothesis' if result['resolved'] else 'unresolved')
                item['evidence'].append({**copy.deepcopy(result), 'source_locator': {
                    'path': imported['document']['source']['path'], 'start': event['source_start'],
                    'end': event['source_end']}, 'tool': tool.name, 'call': calls})
                trace.append(event)
                if result['resolved'] and text is not None:
                    item.update(candidate_text=text, reason='candidate_differs' if text != segment['text'] else 'no_difference_detected')
                    break
                if result.get('retryable') is False:
                    item.update(status='needs_human_review',reason='tool_reported_unresolved')
                    trace.append({'action':'handoff','segment_id':segment['id'],'reason':item['reason']})
                    break
                if context >= max_context_seconds:
                    item.update(status='needs_human_review', reason='unresolved_at_context_limit')
                    break
                context = min(max_context_seconds, max(context * 2, context + 1))
                trace.append({'action': 'expand_context', 'segment_id': segment['id'], 'context_seconds': context})
            except Exception as exc:
                event.update(outcome='tool_failure', error=str(exc))
                trace.append(event)
                item.update(status='needs_human_review', reason='tool_failure')
                break
        item['initial_status']=item['status']
        items.append(item)
    return {'schema_version': '0.1', 'created_at': now(), 'original': copy.deepcopy(imported['document']),
            'source_integrity': {k: imported[k] for k in ('source_sha256', 'import_sha256')},
            'source_locator': {'resolved_path': imported['source_path'], 'base_directory': imported['media_root'],
                               'declared_path': imported['document']['source']['path'],
                               'source_sha256': imported['source_sha256']},
            'policy': {'kind': 'fixed_baseline', 'name': 'bounded_context_baseline',
                       'llm_agent': False, 'max_tool_calls': max_tool_calls, 'tool_calls_used': calls,
                       'context_seconds': context_seconds, 'max_context_seconds': max_context_seconds},
            'coverage': {'cues': coverage_cues(imported), 'complete_error_detection': False,
                         'unflagged_means_correct': False, 'duration_basis': 'declared_source_duration'},
            'items': items, 'trace': trace, 'decisions': []}


def validate_review(review: dict) -> None:
    if not isinstance(review,dict):
        raise ReviewInputError('review must be an object')
    if review.get('schema_version') != '0.1' or not isinstance(review.get('original'), dict):
        raise ReviewInputError('unsupported review document')
    _validate_document(review['original'])
    integrity=review.get('source_integrity')
    if not isinstance(integrity,dict) or any(not isinstance(integrity.get(k),str) or len(integrity[k])!=64
                                             or any(c not in '0123456789abcdef' for c in integrity[k])
                                             for k in ['import_sha256','source_sha256']):
        raise ReviewInputError('invalid source integrity record')
    try:
        original_bytes=json.dumps(review['original'],ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')
    except (TypeError,ValueError) as exc:
        raise ReviewInputError('invalid preserved original') from exc
    if hashlib.sha256(original_bytes).hexdigest()!=review.get('source_integrity',{}).get('import_sha256'):
        raise ReviewInputError('preserved original integrity check failed')
    locator=review.get('source_locator')
    if not isinstance(locator,dict) or not isinstance(locator.get('resolved_path'),str) or not isinstance(locator.get('base_directory'),str):
        raise ReviewInputError('explicit local source locator is missing')
    resolved,base=Path(locator['resolved_path']),Path(locator['base_directory'])
    if (not resolved.is_absolute() or not base.is_absolute() or '..' in resolved.parts
            or not resolved.is_relative_to(base) or locator.get('declared_path')!=review['original']['source']['path']
            or (base/review['original']['source']['path']).resolve()!=resolved
            or locator.get('source_sha256')!=integrity['source_sha256']):
        raise ReviewInputError('invalid local source locator')
    segments = review['original'].get('segments', [])
    if not isinstance(segments,list) or not isinstance(review.get('items'),list) or not isinstance(review.get('decisions'),list):
        raise ReviewInputError('invalid review arrays')
    if not isinstance(review.get('trace'),list) or any(not isinstance(event,dict) for event in review['trace']):
        raise ReviewInputError('invalid action trace entries')
    if len(review.get('items', [])) != len(segments):
        raise ReviewInputError('review/original segment count mismatch')
    states={}
    by_id={}
    for s, item in zip(segments, review['items']):
        if not isinstance(s,dict) or not isinstance(item,dict):
            raise ReviewInputError('invalid review item')
        if s.get('id') != item.get('segment_id') or s.get('text') != item.get('original_text'):
            raise ReviewInputError('review item does not match preserved original')
        if s['start']!=item.get('start') or s['end']!=item.get('end'):
            raise ReviewInputError('review item source interval mismatch')
        if item.get('status') not in {'pending','needs_human_review','accepted','rejected','reverted'}:
            raise ReviewInputError('invalid review status')
        if item.get('candidate_text') is not None and not isinstance(item['candidate_text'], str):
            raise ReviewInputError('invalid candidate text')
        if item.get('status')=='accepted' and item.get('candidate_text') is None:
            raise ReviewInputError('accepted item has no candidate')
        if item.get('initial_status') not in {'pending','needs_human_review'}:
            raise ReviewInputError('invalid initial review status')
        if (not isinstance(item.get('evidence'),list) or any(not isinstance(row,dict) for row in item['evidence'])
                or not isinstance(item.get('reason'),str)):
            raise ReviewInputError('invalid evidence or reason')
        states[s['id']]=item['initial_status']
        by_id[s['id']]=item
    action_states={'accept':'accepted','reject':'rejected','revert':'reverted'}
    for decision in review['decisions']:
        if not isinstance(decision,dict):
            raise ReviewInputError('invalid human decision record')
        sid=decision.get('segment_id')
        if (not isinstance(sid,str) or sid not in by_id or not isinstance(decision.get('action'),str)
                or decision['action'] not in action_states):
            raise ReviewInputError('unknown decision segment or action')
        item=by_id[sid]
        target=action_states[decision['action']]
        if (decision.get('previous_status')!=states[sid] or decision.get('status')!=target
                or decision.get('original_text')!=item['original_text']
                or decision.get('candidate_text')!=item['candidate_text']
                or not isinstance(decision.get('reviewer'),str) or not decision['reviewer'].strip()
                or not isinstance(decision.get('at'),str) or not decision['at']
                or not isinstance(decision.get('note'),str)):
            raise ReviewInputError('human decision history is inconsistent')
        if decision['action']=='accept' and item['candidate_text'] is None:
            raise ReviewInputError('accept decision has no candidate')
        states[sid]=target
    if any(states[sid]!=item['status'] for sid,item in by_id.items()):
        raise ReviewInputError('review status lacks a matching human decision history')


def decide(review: dict, segment_id: str, action: str, *, reviewer: str, note: str = '') -> dict:
    validate_review(review)
    if action not in {'accept', 'reject', 'revert'} or not reviewer.strip():
        raise ReviewInputError('valid action and nonempty reviewer are required')
    result = copy.deepcopy(review)
    item = next((i for i in result['items'] if i['segment_id'] == segment_id), None)
    if item is None:
        raise ReviewInputError(f'unknown segment ID: {segment_id}')
    if action == 'accept' and item['candidate_text'] is None:
        raise ReviewInputError('cannot accept without a candidate hypothesis')
    previous = item['status']
    item['status'] = {'accept':'accepted', 'reject':'rejected', 'revert':'reverted'}[action]
    result['decisions'].append({'at': now(), 'segment_id': segment_id, 'action': action,
                                'reviewer': reviewer, 'note': note, 'previous_status': previous,
                                'status': item['status'], 'original_text': item['original_text'],
                                'candidate_text': item['candidate_text']})
    return result


def export_document(review: dict) -> dict:
    validate_review(review)
    doc = copy.deepcopy(review['original'])
    for s, item in zip(doc['segments'], review['items']):
        s['text'] = item['candidate_text'] if item['status'] == 'accepted' else item['original_text']
        s['review_status'] = item['status']
    doc['review_disclosure'] = 'Pending, rejected and reverted items retain original text. Unflagged text is not verified correct.'
    doc['review_source_locator']=copy.deepcopy(review['source_locator'])
    return doc
