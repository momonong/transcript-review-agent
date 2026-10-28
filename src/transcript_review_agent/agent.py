"""有界動作代理。模型只能選既有證據，不能改寫或代替人工接受。"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import time

from .core import ReviewInputError, coverage_cues, now, validate_review


class PolicyError(ValueError):
    """固定錯誤碼不回顯 prompt、模型路徑或底層例外內容。"""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError('duplicate_action_key')
        result[key] = value
    return result


def parse_action(raw: str, *, max_context_seconds: float = 6.0) -> dict:
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 16384:
        raise PolicyError('invalid_action_text')
    try:
        action = json.loads(raw, object_pairs_hook=_unique_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(PolicyError('nonfinite_action')))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise PolicyError('invalid_action_json') from exc
    if not isinstance(action, dict):
        raise PolicyError('action_must_be_object')
    schemas = {'retranscribe': {'action', 'context_seconds', 'reason'},
               'choose_evidence': {'action', 'index', 'reason'},
               'handoff': {'action', 'reason'}}
    name = action.get('action')
    if not isinstance(name, str) or name not in schemas or set(action) != schemas[name]:
        raise PolicyError('unsupported_action_or_fields')
    if not isinstance(action['reason'], str) or not action['reason'].strip() or len(action['reason']) > 512:
        raise PolicyError('invalid_action_reason')
    if name == 'retranscribe':
        context = action['context_seconds']
        if isinstance(context, bool) or not isinstance(context, (int, float)) or not math.isfinite(context):
            raise PolicyError('invalid_context')
        if not 0 <= context <= max_context_seconds:
            raise PolicyError('context_limit_exceeded')
    if name == 'choose_evidence' and (isinstance(action['index'], bool) or not isinstance(action['index'], int)
                                      or action['index'] < 0):
        raise PolicyError('invalid_evidence_index')
    return action


def _bounded_integer(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ReviewInputError(f'{name} must be an integer between 0 and {maximum}')


def _payload(segments, ordinal, item, max_context_seconds):
    segment = segments[ordinal]
    if len(segment['text']) > 6000:
        raise PolicyError('original_text_exceeds_policy_character_limit')
    neighbors = [{'id': s['id'], 'start': s['start'], 'end': s['end'], 'text': s['text'][:1000],
                  'text_truncated': len(s['text']) > 1000,
                  'role': 'neighbor_transcript_only_not_target_audio_evidence'}
                 for j, s in enumerate(segments[max(0, ordinal-1):ordinal+2], start=max(0, ordinal-1))
                 if j != ordinal]
    evidence = []
    for index, entry in enumerate(item['evidence']):
        text = entry.get('text')
        selectable = entry.get('resolved') is True and isinstance(text, str) and len(text) <= 6000
        evidence.append({'index': index, 'resolved': selectable, 'text': text[:6000] if isinstance(text, str) else None,
                         'text_truncated': isinstance(text, str) and len(text) > 6000,
                         'candidate_scope': entry['candidate_scope'],
                         'context_text': (entry.get('context_text') or '')[:1500],
                         'context_role': 'wider_audio_context_not_a_target_replacement',
                         'target_termination': entry.get('target_termination')})
    return {'data_role': 'untrusted_transcript_and_tool_evidence',
            'segment_id': segment['id'], 'start': segment['start'], 'end': segment['end'],
            'original_text': segment['text'], 'neighbors': neighbors, 'evidence': evidence,
            'allowed_context_seconds': [0, max_context_seconds],
            'decision_effect': 'candidate_for_human_review_only_never_acceptance'}


def run_agent_review(imported: dict, tool, policy, *, max_tool_calls: int = 8,
                     max_llm_calls: int = 12, max_actions_per_segment: int = 4,
                     max_context_seconds: float = 6.0, max_total_seconds: float = 120.0) -> dict:
    _bounded_integer(max_tool_calls, 'max_tool_calls', 256)
    _bounded_integer(max_llm_calls, 'max_llm_calls', 256)
    _bounded_integer(max_actions_per_segment, 'max_actions_per_segment', 4)
    for value, name, maximum in [(max_context_seconds, 'max_context_seconds', 30),
                                  (max_total_seconds, 'max_total_seconds', 3600)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
            raise ReviewInputError(f'invalid {name}')
    identity = {k: getattr(policy, k, None) for k in ('model_id', 'revision')}
    if any(not isinstance(v, str) or not v or len(v) > 256 for v in identity.values()):
        raise ReviewInputError('explicit policy model_id and revision are required')
    segments = imported['document']['segments']
    items = [{'segment_id': s['id'], 'start': s['start'], 'end': s['end'], 'original_text': s['text'],
              'candidate_text': None, 'status': 'pending', 'initial_status': 'pending',
              'reason': 'not_checked', 'evidence': []} for s in segments]
    review = {'schema_version': '0.1', 'created_at': now(), 'original': copy.deepcopy(imported['document']),
              'source_integrity': {k: imported[k] for k in ('source_sha256', 'import_sha256')},
              'source_locator': {'resolved_path': imported['source_path'], 'base_directory': imported['media_root'],
                                 'declared_path': imported['document']['source']['path'],
                                 'source_sha256': imported['source_sha256']},
              'policy': {'kind': 'llm_agent', 'llm_agent': True, **identity,
                         'identity_verification': getattr(policy, 'identity_verification', 'declared_by_policy'),
                         'weight_sha256': copy.deepcopy(getattr(policy, 'weight_sha256', {})),
                         'max_tool_calls': max_tool_calls, 'max_llm_calls': max_llm_calls,
                         'max_actions_per_segment': max_actions_per_segment,
                         'max_context_seconds': max_context_seconds, 'max_total_seconds': max_total_seconds,
                         'hard_timeout_preemption': False,
                         'timeout_disclosure': 'cooperative generation max_time plus elapsed checks; calls are not forcibly preempted'},
              'coverage': {'cues': coverage_cues(imported), 'complete_error_detection': False,
                           'unflagged_means_correct': False, 'duration_basis': 'declared_source_duration'},
              'items': items, 'trace': [], 'decisions': []}
    validate_review(review)
    started = time.perf_counter()
    llm_calls = tool_calls = 0
    duration = imported['document']['source']['duration']

    def handoff(item, reason):
        item.update(status='needs_human_review', reason=reason)
        review['trace'].append({'action': 'handoff', 'segment_id': item['segment_id'], 'reason': reason,
                                'elapsed_seconds': round(time.perf_counter()-started, 4)})

    for ordinal, (segment, item) in enumerate(zip(segments, items)):
        for step in range(max_actions_per_segment):
            if time.perf_counter()-started >= max_total_seconds:
                handoff(item, 'total_time_exhausted'); break
            if llm_calls >= max_llm_calls:
                handoff(item, 'llm_budget_exhausted'); break
            if not item['evidence'] and tool_calls >= max_tool_calls:
                handoff(item, 'tool_budget_exhausted'); break
            event = {'action': 'policy_decision', 'segment_id': segment['id'], 'step': step+1,
                     'call': None, **identity}
            review['trace'].append(event)
            call_started = time.perf_counter()
            try:
                payload = _payload(segments, ordinal, item, max_context_seconds)
                llm_calls += 1
                event['call'] = llm_calls
                result = policy.decide(payload)
                if not isinstance(result, dict) or not isinstance(result.get('text'), str) or len(result['text']) > 16384:
                    raise PolicyError('invalid_policy_result_contract')
                event['raw_action'] = result['text']
                for key, maximum in [('input_tokens', 2048), ('generated_tokens', 192)]:
                    if key in result:
                        _bounded_integer(result[key], key, maximum)
                        event[key] = result[key]
                termination = result.get('termination')
                event['termination'] = copy.deepcopy(termination)
                if not isinstance(termination, dict) or termination.get('complete') is not True or termination.get('ended_with_eos') is not True:
                    event['outcome'] = 'incomplete'
                    handoff(item, 'policy_incomplete'); break
                if time.perf_counter()-started >= max_total_seconds:
                    event['outcome'] = 'total_time_exhausted'
                    handoff(item, 'total_time_exhausted'); break
                action = parse_action(result['text'], max_context_seconds=max_context_seconds)
                event.update(parsed_action=action, outcome='valid_action')
            except Exception as exc:
                event.update(outcome='policy_failure', error_code=str(exc) if isinstance(exc, PolicyError) else 'policy_exception',
                             exception_type=type(exc).__name__)
                handoff(item, 'policy_failure'); break
            finally:
                event['elapsed_seconds'] = round(time.perf_counter()-call_started, 4)
            if action['action'] == 'handoff':
                item['policy_reason'] = action['reason']
                handoff(item, 'policy_handoff'); break
            if action['action'] == 'choose_evidence':
                index = action['index']
                if index >= len(item['evidence']):
                    handoff(item, 'invalid_evidence_index'); break
                chosen = item['evidence'][index]
                if chosen.get('resolved') is not True or not isinstance(chosen.get('text'), str) or len(chosen['text']) > 6000:
                    handoff(item, 'evidence_not_selectable'); break
                item.update(candidate_text=chosen['text'], selected_evidence_index=index,
                            reason='observed_candidate_selected', policy_reason=action['reason'])
                break
            if tool_calls >= max_tool_calls:
                handoff(item, 'tool_budget_exhausted'); break
            tool_calls += 1
            context = action['context_seconds']
            tool_event = {'action': 'retranscribe', 'call': tool_calls, 'segment_id': segment['id'],
                          'tool': tool.name, 'context_seconds': context,
                          'source_start': max(0, segment['start']-context),
                          'source_end': min(duration, segment['end']+context)}
            review['trace'].append(tool_event)
            tool_started = time.perf_counter()
            try:
                evidence = tool.retranscribe(Path(imported['source_path']), segment, context, duration)
                if not isinstance(evidence, dict) or not isinstance(evidence.get('resolved'), bool):
                    raise PolicyError('invalid_tool_result')
                text = evidence.get('text')
                if text is not None and (not isinstance(text, str) or len(text) > 100000):
                    raise PolicyError('invalid_tool_text')
                target = {'start': segment['start'], 'end': segment['end']}
                if evidence.get('candidate_scope', target) != target:
                    raise PolicyError('tool_candidate_is_not_target_scoped')
                if len(json.dumps(evidence, allow_nan=False)) > 150000:
                    raise PolicyError('tool_evidence_size_limit')
                evidence = copy.deepcopy(evidence)
                evidence.update(candidate_scope=target, tool=tool.name, call=tool_calls,
                                source_locator={'path': imported['document']['source']['path'],
                                                'start': tool_event['source_start'], 'end': tool_event['source_end']})
                item['evidence'].append(evidence)
                tool_event['outcome'] = 'hypothesis' if evidence['resolved'] else 'unresolved'
                if time.perf_counter()-started >= max_total_seconds:
                    handoff(item, 'total_time_exhausted'); break
                if not evidence['resolved'] and evidence.get('retryable') is False:
                    handoff(item, 'tool_reported_unresolved'); break
            except Exception as exc:
                tool_event.update(outcome='tool_failure', exception_type=type(exc).__name__)
                handoff(item, 'tool_failure'); break
            finally:
                tool_event['elapsed_seconds'] = round(time.perf_counter()-tool_started, 4)
        else:
            handoff(item, 'segment_action_budget_exhausted')
        item['initial_status'] = item['status']
    review['policy'].update(llm_calls_used=llm_calls, tool_calls_used=tool_calls,
                            elapsed_seconds=round(time.perf_counter()-started, 4))
    validate_review(review)
    return review
