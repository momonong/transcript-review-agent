"""Create silent synthetic audio and fictional evidence, NOT a model/accuracy demo."""
import argparse
import json
from pathlib import Path
import wave

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
args=p.parse_args()
args.out.mkdir(parents=True,exist_ok=False)
with wave.open(str(args.out/'fictional.wav'),'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000*8)
templates=Path(__file__).resolve().parent
doc=json.loads((templates/'fictional-input.json').read_text(encoding='utf-8'))
evidence=json.loads((templates/'fictional-evidence.json').read_text(encoding='utf-8'))
for name,data in [('input.json',doc),('evidence.json',evidence)]:
    (args.out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Created fictional, silent harness fixture at {args.out}')
