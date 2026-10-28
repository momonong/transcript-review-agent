import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from transcript_review_agent.core import ImportError as ReviewImportError
from transcript_review_agent.core import load_import, coverage_cues, run_review, decide, export_document
from transcript_review_agent.tools import FixtureTool


class CoreTests(unittest.TestCase):
    def setUp(self):
        temp_root=Path(__file__).resolve().parents[1]/'.local'/'test-temp'
        temp_root.mkdir(parents=True,exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.root = Path(self.tmp.name)
        with wave.open(str(self.root / 'audio.wav'), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b'\0\0' * 16000 * 3)
        self.doc = {'source': {'path': 'audio.wav', 'duration': 3}, 'segments': [
            {'id': 's1', 'start': 0, 'end': 2, 'text': '我拿了十五個。'},
            {'id': 's2', 'start': 1.5, 'end': 3, 'text': '原文不變。'}]}

    def tearDown(self):
        self.tmp.cleanup()

    def imported(self, doc=None, **kw):
        p=self.root/'input.json'; p.write_text(json.dumps(doc or self.doc, ensure_ascii=False), encoding='utf-8')
        return load_import(p, **kw)

    def test_reject_invalid_time(self):
        for start,end in [(-1,1),(2,1),(0,4),(0,float('nan')),(True,1)]:
            d=copy.deepcopy(self.doc);d['segments'][0].update(start=start,end=end)
            with self.assertRaises(ReviewImportError): self.imported(d)

    def test_overlap_is_cue_and_never_error_verdict(self):
        cues=coverage_cues(self.imported())
        self.assertTrue(any(c['kind']=='overlap' for c in cues))
        self.assertTrue(all(c['status']=='needs_human_review' for c in cues))
        self.assertFalse(any('correct' in c for c in cues))

    def test_budget_failure_and_unflagged_remain_pending(self):
        imp=self.imported(); tool=FixtureTool({'s1': {'text':'我、我沒有拿十五個。我拿了五十個。'}})
        r=run_review(imp,tool,max_tool_calls=1)
        self.assertEqual(r['items'][0]['status'],'pending')
        self.assertEqual(r['items'][1]['status'],'needs_human_review')
        self.assertEqual(r['items'][1]['reason'],'tool_budget_exhausted')
        self.assertEqual(export_document(r)['segments'][0]['text'],'我拿了十五個。')
        r2=run_review(imp,FixtureTool({'s1': {'error':'fixture failure'},'s2':{'text':'原文不變。'}}))
        self.assertEqual(r2['items'][0]['status'],'needs_human_review')
        self.assertEqual(r2['items'][1]['status'],'pending')
        self.assertNotIn('correct',r2['items'][1])

    def test_accept_and_revert_preserve_original_and_audit(self):
        imp=self.imported(); r=run_review(imp,FixtureTool({'s1':{'text':'我、我沒有拿十五個。我拿了五十個。'}}))
        accepted=decide(r,'s1','accept',reviewer='tester')
        self.assertEqual(export_document(accepted)['segments'][0]['text'],'我、我沒有拿十五個。我拿了五十個。')
        reverted=decide(accepted,'s1','revert',reviewer='tester')
        self.assertEqual(export_document(reverted)['segments'][0]['text'],'我拿了十五個。')
        self.assertEqual(reverted['original'],imp['document'])
        self.assertEqual([d['action'] for d in reverted['decisions']],['accept','revert'])
        self.assertEqual(r['decisions'],[])

    def test_source_path_traversal_and_size_limit(self):
        d=copy.deepcopy(self.doc);d['source']['path']='../audio.wav'
        with self.assertRaises(ReviewImportError): self.imported(d)
        with self.assertRaises(ReviewImportError): self.imported(max_media_bytes=10)
        with self.assertRaises(ReviewImportError): self.imported(max_json_bytes=10)

    def test_gap_is_only_cue(self):
        d=copy.deepcopy(self.doc);d['segments'][1]['start']=2.5
        cues=coverage_cues(self.imported(d))
        gap=next(c for c in cues if c['kind']=='gap')
        self.assertIn('not proof',gap['reason'])

    def test_unresolved_tool_expands_context_within_budget(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'resolved':False}}),max_tool_calls=2,
                     context_seconds=1,max_context_seconds=2)
        self.assertEqual(r['policy']['tool_calls_used'],2)
        self.assertTrue(any(t['action']=='expand_context' for t in r['trace']))
        self.assertEqual(r['items'][0]['status'],'needs_human_review')

    def test_nonretryable_incomplete_tool_hands_off_without_retry(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'resolved':False,'retryable':False}}),max_tool_calls=8)
        self.assertEqual(r['items'][0]['reason'],'tool_reported_unresolved')
        self.assertEqual(len(r['items'][0]['evidence']),1)

    def test_reject_has_original_export_and_no_output_overwrite(self):
        from transcript_review_agent.core import write_json_new
        r=run_review(self.imported(),FixtureTool({'s1':{'text':'不同候選'}}))
        rejected=decide(r,'s1','reject',reviewer='human')
        self.assertEqual(export_document(rejected)['segments'][0]['text'],'我拿了十五個。')
        out=self.root/'review.json';write_json_new(out,r)
        with self.assertRaises(FileExistsError):write_json_new(out,rejected)

    def test_modified_preserved_original_is_rejected(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'text':'候選'}}))
        r['original']['segments'][0]['text']='tampered'
        r['items'][0]['original_text']='tampered'
        with self.assertRaises(ReviewImportError):export_document(r)

    def test_accepted_state_requires_matching_human_decision(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'text':'候選'}}))
        r['items'][0]['status']='accepted'
        with self.assertRaises(ReviewImportError):export_document(r)
        r['items'][0]['status']='pending'
        accepted=decide(r,'s1','accept',reviewer='human')
        accepted['items'][0]['candidate_text']='different candidate'
        with self.assertRaises(ReviewImportError):export_document(accepted)

    def test_original_schema_is_checked_even_if_hash_matches(self):
        import hashlib
        for change in ['path','time']:
            r=run_review(self.imported(),FixtureTool({'s1':{'text':'候選'}}))
            if change=='path':r['original']['source']['path']='../another.wav'
            else:r['original']['segments'][0]['end']=99
            payload=json.dumps(r['original'],ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')
            r['source_integrity']['import_sha256']=hashlib.sha256(payload).hexdigest()
            with self.assertRaises(ReviewImportError):export_document(r)

    def test_cross_directory_export_retains_explicit_source_locator(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'text':'候選'}}))
        exported=export_document(r)
        self.assertEqual(Path(exported['review_source_locator']['resolved_path']),self.root/'audio.wav')
        self.assertEqual(exported['source']['path'],'audio.wav')

    def test_locator_must_match_declared_file_and_base(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'text':'候選'}}))
        r['source_locator']['resolved_path']=str(self.root/'other.wav')
        with self.assertRaises(ReviewImportError):export_document(r)

    def test_malformed_decision_identity_is_rejected_cleanly(self):
        r=run_review(self.imported(),FixtureTool({'s1':{'text':'候選'}}))
        r=decide(r,'s1','accept',reviewer='tester')
        r['decisions'][0]['segment_id']=[]
        with self.assertRaises(ReviewImportError):export_document(r)


if __name__=='__main__': unittest.main()
