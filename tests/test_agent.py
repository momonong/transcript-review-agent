"""Agent guardrails use fictional evidence and a scripted policy, never a GPU."""
import contextlib
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from transcript_review_agent.core import load_import, decide, export_document
from transcript_review_agent.tools import FixtureTool

from transcript_review_agent.agent import run_agent_review, parse_action
from transcript_review_agent.phi_cuda import PhiActionPolicy, verify_checkpoint_weights


class ScriptedPolicy:
    model_id = 'fictional/scripted-policy'
    revision = 'test-only-not-model-inference'

    def __init__(self, actions, complete=True):
        self.actions = iter(actions)
        self.complete = complete
        self.requests = []

    def decide(self, payload):
        self.requests.append(copy.deepcopy(payload))
        action = next(self.actions)
        return {'text': action if isinstance(action, str) else json.dumps(action),
                'termination': {'complete': self.complete, 'ended_with_eos': self.complete,
                                'returned_token_count': 10, 'max_new_tokens': 192}}


class AgentTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / '.local' / 'test-temp'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.root = Path(self.tmp.name)
        (self.root / 'fictional.wav').write_bytes(b'fictional bytes; fixture does not decode')
        doc = {'source': {'path': 'fictional.wav', 'duration': 5}, 'segments': [
            {'id': 's1', 'start': 0, 'end': 2, 'text': '沒有拿十五個。'},
            {'id': 's2', 'start': 3, 'end': 5, 'text': '保留重複、改口。'}]}
        (self.root / 'input.json').write_text(json.dumps(doc), encoding='utf-8')
        self.imported = load_import(self.root / 'input.json')

    def tearDown(self):
        if hasattr(self, 'tmp'):
            self.tmp.cleanup()

    def test_selected_observed_candidate_remains_pending_and_reverts_losslessly(self):
        p = ScriptedPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'},
                            {'action': 'choose_evidence', 'index': 0, 'reason': 'use target ASR'},
                            {'action': 'handoff', 'reason': 'needs listening'}])
        r = run_agent_review(self.imported, FixtureTool({'s1': {'text': '我、我沒有拿十五個。'}}), p)
        self.assertEqual(r['items'][0]['candidate_text'], '我、我沒有拿十五個。')
        self.assertEqual(r['items'][0]['status'], 'pending')
        self.assertEqual(r['items'][1]['status'], 'needs_human_review')
        self.assertEqual(r['policy']['kind'], 'llm_agent')
        self.assertEqual(r['policy']['llm_calls_used'], 3)
        self.assertTrue(any(c['kind'] == 'gap' for c in r['coverage']['cues']))
        accepted = decide(r, 's1', 'accept', reviewer='fictional reviewer')
        self.assertEqual(export_document(accepted)['segments'][0]['text'], '我、我沒有拿十五個。')
        reverted = decide(accepted, 's1', 'revert', reviewer='fictional reviewer')
        self.assertEqual(export_document(reverted)['segments'][0]['text'], '沒有拿十五個。')
        self.assertEqual(reverted['original'], self.imported['document'])
        self.assertEqual(p.requests[0]['data_role'], 'untrusted_transcript_and_tool_evidence')
        self.assertNotIn(str(self.root), json.dumps(p.requests, ensure_ascii=False))

    def test_invalid_actions_indices_and_free_text_never_create_candidates(self):
        invalid = [{'action': 'accept', 'reason': 'not permitted'},
                   {'action': 'choose_evidence', 'index': 0, 'reason': 'no evidence'},
                   {'action': 'choose_evidence', 'index': True, 'reason': 'invalid index'},
                   {'action': 'handoff', 'reason': 'x', 'text': 'invented replacement'},
                   {'action': 'retranscribe', 'context_seconds': 31, 'reason': 'out of bounds'},
                   '{"action":"handoff","action":"accept","reason":"duplicate"}',
                   '```json\n{"action":"handoff","reason":"x"}\n```']
        for action in invalid:
            with self.subTest(action=action):
                p = ScriptedPolicy([action, {'action': 'handoff', 'reason': 'next'}])
                r = run_agent_review(self.imported, FixtureTool({}), p)
                self.assertTrue(all(i['candidate_text'] is None for i in r['items']))
                self.assertTrue(all(i['status'] == 'needs_human_review' for i in r['items']))

    def test_budget_leaves_every_unfinished_segment_explicitly_for_humans(self):
        p = ScriptedPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'}])
        r = run_agent_review(self.imported, FixtureTool({'s1': {'text': 'hypothesis'}}), p,
                             max_llm_calls=1)
        self.assertEqual(r['policy']['llm_calls_used'], 1)
        self.assertTrue(all(i['status'] == 'needs_human_review' for i in r['items']))
        self.assertTrue(all(i['candidate_text'] is None for i in r['items']))

    def test_tool_failure_never_becomes_selected_text(self):
        p = ScriptedPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'},
                            {'action': 'handoff', 'reason': 'second'}])
        r = run_agent_review(self.imported, FixtureTool({'s1': {'error': 'fictional failure'}}), p)
        self.assertEqual(r['items'][0]['reason'], 'tool_failure')
        self.assertIsNone(r['items'][0]['candidate_text'])

    def test_no_eos_action_is_not_executed(self):
        p = ScriptedPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'}] * 2,
                           complete=False)
        r = run_agent_review(self.imported, FixtureTool({}), p)
        self.assertEqual(r['policy']['tool_calls_used'], 0)
        self.assertTrue(all(i['reason'] == 'policy_incomplete' for i in r['items']))

    def test_total_deadline_stops_after_cooperative_policy_return(self):
        elapsed = [0.0]
        class SlowPolicy(ScriptedPolicy):
            def decide(self, payload):
                elapsed[0] = 11.0
                return super().decide(payload)
        p = SlowPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'}])
        with patch('transcript_review_agent.agent.time.perf_counter', side_effect=lambda: elapsed[0]):
            r = run_agent_review(self.imported, FixtureTool({}), p, max_total_seconds=10)
        self.assertEqual(r['policy']['tool_calls_used'], 0)
        self.assertTrue(all(i['reason'] == 'total_time_exhausted' for i in r['items']))
        self.assertFalse(r['policy']['hard_timeout_preemption'])

    def test_unresolved_or_context_scope_result_cannot_be_selected(self):
        for row in [{'text': 'not resolved', 'resolved': False, 'retryable': False},
                    {'text': 'wider context', 'candidate_scope': {'start': 0, 'end': 5}}]:
            class ScopeTool:
                name = 'fictional_scope_tool'
                def retranscribe(self, *args): return {'resolved': True, **row}
            p = ScriptedPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'},
                                {'action': 'handoff', 'reason': 'second'}])
            r = run_agent_review(self.imported, ScopeTool(), p)
            self.assertIsNone(r['items'][0]['candidate_text'])
            self.assertEqual(r['items'][0]['status'], 'needs_human_review')

    def test_zero_tool_budget_and_action_limit_leave_every_segment_for_humans(self):
        p = ScriptedPolicy([])
        r = run_agent_review(self.imported, FixtureTool({}), p, max_tool_calls=0)
        self.assertEqual(r['policy']['llm_calls_used'], 0)
        self.assertTrue(all(i['reason'] == 'tool_budget_exhausted' for i in r['items']))
        p = ScriptedPolicy([{'action': 'retranscribe', 'context_seconds': 0, 'reason': 'check'}] * 2)
        r = run_agent_review(self.imported, FixtureTool({'s1': {'text': 'first'}, 's2': {'text': 'second'}}), p,
                             max_actions_per_segment=1)
        self.assertEqual(r['policy']['tool_calls_used'], 2)
        self.assertTrue(all(i['reason'] == 'segment_action_budget_exhausted' for i in r['items']))

    def test_policy_resource_trace_retains_token_counts(self):
        class CountingPolicy(ScriptedPolicy):
            def decide(self, payload):
                return {**super().decide(payload), 'input_tokens': 321, 'generated_tokens': 17}
        p = CountingPolicy([{'action': 'handoff', 'reason': 'check'}] * 2)
        r = run_agent_review(self.imported, FixtureTool({}), p)
        rows = [e for e in r['trace'] if e['action'] == 'policy_decision']
        self.assertEqual([(e['input_tokens'], e['generated_tokens']) for e in rows], [(321, 17), (321, 17)])
        self.assertEqual(r['trace'][0]['action'], 'policy_decision')


class PhiPolicyTests(unittest.TestCase):
    def test_cuda_and_existing_checkpoint_are_required_before_model_import(self):
        with self.assertRaises(ValueError): PhiActionPolicy('missing-checkpoint', device='cpu')
        with self.assertRaises(ValueError): PhiActionPolicy('missing-checkpoint')

    def test_decoder_uses_model_eos_list_and_rejects_truncated_actions(self):
        class Tensor:
            shape = (1, 3)
            def to(self, *a, **kw): return self
        class Row:
            def __init__(self, ids): self.ids = ids
            def __getitem__(self, key): return Row(self.ids[key])
            def detach(self): return self
            def cpu(self): return self
            def tolist(self): return self.ids
        class Tokenizer:
            eos_token_id = 199999
            def apply_chat_template(self, *a, **kw): return {'input_ids': Tensor(), 'attention_mask': Tensor()}
            def decode(self, *a, **kw): return '{"action":"handoff","reason":"check"}'
        for ending, expected in [(200020, True), (42, False)]:
            p = PhiActionPolicy.__new__(PhiActionPolicy)
            p.tokenizer = Tokenizer()
            p.model = SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=[200020, 199999]),
                                      generate=lambda **kw: SimpleNamespace(sequences=[Row([1, 2, 3, ending])]))
            p.torch = SimpleNamespace(inference_mode=contextlib.nullcontext)
            p.device = 'cuda:0'; p.max_prompt_tokens = 2048; p.max_new_tokens = 192
            p.max_time_seconds = 20; p.model_id = 'fictional/policy'; p.revision = 'fictional'
            result = p.decide({'data_role': 'untrusted_transcript_and_tool_evidence'})
            self.assertEqual(result['termination']['complete'], expected)

    def test_wrong_checkpoint_hash_is_rejected_without_loading_gpu(self):
        root = Path(__file__).resolve().parents[1] / '.local' / 'test-temp'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as d:
            checkpoint = Path(d)
            shard = checkpoint / 'model.safetensors'
            shard.write_bytes(b'abc')
            expected = {'model.safetensors': (3, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')}
            with patch('transcript_review_agent.phi_cuda.PHI_SHARDS', expected):
                self.assertEqual(verify_checkpoint_weights(checkpoint), {'model.safetensors': expected['model.safetensors'][1]})
                shard.write_bytes(b'abd')
                with self.assertRaises(ValueError): verify_checkpoint_weights(checkpoint)
                shard.write_bytes(b'abcd')
                with self.assertRaises(ValueError): verify_checkpoint_weights(checkpoint)


if __name__ == '__main__': unittest.main()
