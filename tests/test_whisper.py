import tempfile
from pathlib import Path
import unittest
import wave
from contextlib import nullcontext
from types import SimpleNamespace

from transcript_review_agent.whisper_cuda import read_pcm16_clip, TransformersWhisperTool, generation_termination
from transcript_review_agent.tools import ToolError


class WhisperBoundaryTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.local'/'test-temp'
        root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=root)
        self.path=Path(self.tmp.name)/'source.wav'
        with wave.open(str(self.path),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*32000)

    def tearDown(self): self.tmp.cleanup()

    def test_exact_clip_and_duration_contract(self):
        samples=read_pcm16_clip(self.path,.5,1.5,declared_duration=2,max_clip_seconds=2)
        self.assertEqual(len(samples),16000)
        self.assertEqual(max(samples),0)
        with self.assertRaises(ToolError): read_pcm16_clip(self.path,0,2,declared_duration=2,max_clip_seconds=1)
        with self.assertRaises(ToolError): read_pcm16_clip(self.path,0,1,declared_duration=3,max_clip_seconds=2)

    def test_missing_checkpoint_and_cpu_request_fail_before_import(self):
        with self.assertRaises(ToolError): TransformersWhisperTool(Path(self.tmp.name)/'missing')
        with self.assertRaises(ToolError): TransformersWhisperTool(Path(self.tmp.name),device='cpu')

    def test_generation_without_eos_is_not_complete(self):
        self.assertFalse(generation_termination([1,2,3],9,2)['complete'])
        self.assertTrue(generation_termination([1,2,9],9,2)['complete'])
        self.assertFalse(generation_termination([1,9,3],9,2)['complete'])

    def test_truncated_target_hypothesis_requires_human(self):
        tool=object.__new__(TransformersWhisperTool)
        tool.max_clip_seconds=30;tool.model_path=Path('local-whisper')
        tool.device='cuda:0';tool.language='en';tool.modern_language_config=False
        tool._decode=lambda samples:{'text':'unfinished','termination':generation_termination([1,2,3],9,2)}
        result=tool.retranscribe(self.path,{'start':0,'end':2},0,2)
        self.assertFalse(result['resolved'])
        self.assertFalse(result['retryable'])
        self.assertIsNone(result['text'])
        self.assertEqual(result['target_text'],'unfinished')

    def test_decode_requests_unstripped_sequences_with_eos(self):
        class Tensor:
            def to(self,*args,**kwargs):return self
            def __getitem__(self,index):return self
            def detach(self):return self
            def cpu(self):return self
            def tolist(self):return [1,2,9]
        tensor=Tensor()
        def generate(**kwargs):
            self.assertIs(kwargs.get('return_dict_in_generate'),True)
            return SimpleNamespace(sequences=tensor)
        class Processor:
            def __call__(self,*args,**kwargs):return SimpleNamespace(input_features=tensor,attention_mask=tensor)
            def batch_decode(self,ids,**kwargs):
                if ids is not tensor:raise AssertionError('decode must use raw output.sequences')
                return ['complete hypothesis']
        tool=object.__new__(TransformersWhisperTool)
        tool.processor=Processor();tool.model=SimpleNamespace(generate=generate)
        tool.torch=SimpleNamespace(float16='float16',inference_mode=nullcontext)
        tool.device='cuda:0';tool.max_new_tokens=2;tool.modern_language_config=False
        tool.generation_config=SimpleNamespace(eos_token_id=9)
        decoded=tool._decode([0.0])
        self.assertTrue(decoded['termination']['complete'])
        self.assertEqual(decoded['text'],'complete hypothesis')


if __name__=='__main__': unittest.main()
