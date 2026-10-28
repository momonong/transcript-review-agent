"""Optional local Transformers Whisper CUDA tool. Never downloads or uses CPU."""
from __future__ import annotations

from array import array
import copy
import json
from pathlib import Path
import re
import sys
import time
import wave

from .tools import ToolError


def generation_termination(token_ids: list[int], eos_token_id: int | list[int], max_new_tokens: int) -> dict:
    """EOS checks decoding termination only. It never proves transcript accuracy."""
    eos_ids=eos_token_id if isinstance(eos_token_id,list) else [eos_token_id]
    if not eos_ids or any(not isinstance(v,int) for v in eos_ids):
        raise ToolError('cannot verify generation termination without an explicit EOS token')
    complete=bool(token_ids) and token_ids[-1] in eos_ids
    return {'complete':complete,'ended_with_eos':complete,'returned_token_count':len(token_ids),
            'max_new_tokens':max_new_tokens,
            'reason':'eos' if complete else 'missing_eos_possible_token_limit'}


def read_pcm16_clip(path: Path, start: float, end: float, *, declared_duration: float,
                    max_clip_seconds: float = 30) -> list[float]:
    """Read an explicitly bounded mono, 16 kHz, PCM16 WAV interval."""
    if not 0 <= start < end or end-start > max_clip_seconds:
        raise ToolError('invalid or oversized audio interval')
    try:
        with wave.open(str(path), 'rb') as stream:
            if (stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getcomptype()) != (1,2,16000,'NONE'):
                raise ToolError('Whisper adapter requires mono 16 kHz PCM16 WAV; explicit conversion is required')
            actual_duration=stream.getnframes()/16000
            if abs(actual_duration-declared_duration) > .1 or end > actual_duration+.001:
                raise ToolError('declared duration does not match WAV frames')
            first,last=int(start*16000),min(int(end*16000),stream.getnframes())
            stream.setpos(first)
            samples=array('h',stream.readframes(last-first))
            if sys.byteorder!='little': samples.byteswap()
    except (OSError,wave.Error) as exc:
        raise ToolError(f'cannot decode WAV: {exc}') from exc
    if not samples:
        raise ToolError('empty source clip')
    return [v/32768 for v in samples]


class TransformersWhisperTool:
    name='transformers_whisper_cuda'

    def __init__(self,model_path: Path | str,*,device: str='cuda:0',language: str='zh',
                 max_new_tokens: int=224,max_clip_seconds: float=30):
        self.model_path=Path(model_path).resolve()
        if not re.fullmatch(r'cuda(?::[0-9]+)?',device):
            raise ToolError('CUDA is required; CPU fallback is disabled')
        if not self.model_path.is_dir() or not (self.model_path/'config.json').is_file():
            raise ToolError('explicit existing local Whisper checkpoint directory is required; no downloads')
        if not any(self.model_path.glob('*.safetensors')) and not any(self.model_path.glob('pytorch_model*.bin')):
            raise ToolError('local model weights are missing; no download will be attempted')
        if not language or not 1 <= max_new_tokens <= 400 or not 0 < max_clip_seconds <= 30:
            raise ToolError('explicit language and bounded decoding limits are required')
        try:
            import torch
            from transformers import WhisperForConditionalGeneration,WhisperProcessor
        except ImportError as exc:
            raise ToolError('optional torch/transformers runtime is unavailable') from exc
        if not torch.cuda.is_available():
            raise ToolError('CUDA is unavailable; CPU fallback is disabled')
        try:
            config=json.loads((self.model_path/'config.json').read_text(encoding='utf-8'))
            if config.get('model_type')!='whisper':
                raise ToolError('local checkpoint is not a Whisper model')
            self.processor=WhisperProcessor.from_pretrained(str(self.model_path),local_files_only=True)
            self.model=WhisperForConditionalGeneration.from_pretrained(
                str(self.model_path),local_files_only=True,torch_dtype=torch.float16).to(device).eval()
            self.generation_config=copy.deepcopy(self.model.generation_config)
            self.modern_language_config=bool(getattr(self.generation_config,'lang_to_id',None))
            if not self.modern_language_config:
                self.generation_config.forced_decoder_ids=self.processor.get_decoder_prompt_ids(
                    language=language,task='transcribe',no_timestamps=True)
        except Exception as exc:
            raise ToolError(f'local Whisper CUDA initialization failed: {exc}') from exc
        self.torch=torch
        self.device=device
        self.language=language
        self.max_new_tokens=max_new_tokens
        self.max_clip_seconds=max_clip_seconds

    def _decode(self,samples: list[float]) -> dict:
        inputs=self.processor(samples,sampling_rate=16000,return_tensors='pt',return_attention_mask=True)
        kwargs={'input_features':inputs.input_features.to(self.device,dtype=self.torch.float16),
                'attention_mask':inputs.attention_mask.to(self.device),
                'max_new_tokens':self.max_new_tokens,'do_sample':False,'return_timestamps':False,
                'return_dict_in_generate':True}
        if self.modern_language_config:
            kwargs.update(language=self.language,task='transcribe')
        else:
            kwargs['generation_config']=self.generation_config
        with self.torch.inference_mode():
            output=self.model.generate(**kwargs)
        # Whisper's tensor-only return strips EOS. The explicit ModelOutput
        # contract preserves raw decoder sequences and their real EOS token.
        tokens=output.sequences
        ids=tokens[0].detach().cpu().tolist()
        eos=getattr(self.generation_config,'eos_token_id',None)
        if eos is None:eos=self.processor.tokenizer.eos_token_id
        return {'text':self.processor.batch_decode(tokens,skip_special_tokens=True)[0],
                'termination':generation_termination(ids,eos,self.max_new_tokens)}

    def retranscribe(self,source: Path,segment: dict,context: float,duration: float) -> dict:
        started=time.perf_counter()
        target=read_pcm16_clip(source,segment['start'],segment['end'],declared_duration=duration,
                               max_clip_seconds=self.max_clip_seconds)
        target_result=self._decode(target)
        context_start,context_end=max(0,segment['start']-context),min(duration,segment['end']+context)
        context_result=None
        generate_calls=1
        if target_result['termination']['complete'] and (context_start < segment['start'] or context_end > segment['end']):
            surrounding=read_pcm16_clip(source,context_start,context_end,declared_duration=duration,
                                        max_clip_seconds=self.max_clip_seconds)
            context_result=self._decode(surrounding)
            generate_calls+=1
        complete=target_result['termination']['complete'] and (context_result is None or context_result['termination']['complete'])
        return {'text':target_result['text'] if complete else None,'resolved':complete,'retryable':False,
                'reason':'local model hypothesis; human confirmation required' if complete else 'generation_missing_eos_requires_human',
                'target_text':target_result['text'],
                'target_termination':target_result['termination'],
                'context_termination':context_result['termination'] if context_result else None,
                'provenance':'real_local_model_inference','model':self.model_path.name,
                'device':self.device,'dtype':'float16','language':self.language,'task':'transcribe',
                'generation_branch':'modern_language_task' if self.modern_language_config else 'legacy_explicit_forced_decoder_ids',
                'generation_calls':generate_calls,'elapsed_seconds':round(time.perf_counter()-started,4),
                'candidate_scope':{'start':segment['start'],'end':segment['end']},
                'context_text':context_result['text'] if context_result else None,
                'context_scope':{'start':context_start,'end':context_end},
                'context_disclosure':'Context hypothesis covers a wider interval and never replaces the target segment automatically.'}
