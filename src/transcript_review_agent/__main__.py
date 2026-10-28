"""Run with python -m transcript_review_agent. Core uses only the standard library."""
import argparse
import json
from pathlib import Path
import sys

from .core import load_import, read_json, write_json_new, run_review, decide, export_document, ReviewInputError
from .tools import FixtureTool, ToolError


def parser():
    p=argparse.ArgumentParser(description='Local transcript review baseline harness. No correctness guarantee.')
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('review',help='Run explicit fixed baseline with a selected evidence tool')
    r.add_argument('input',type=Path);r.add_argument('--out',type=Path,required=True)
    r.add_argument('--media-root',type=Path)
    tools=r.add_mutually_exclusive_group(required=True)
    tools.add_argument('--fixture',type=Path)
    tools.add_argument('--whisper-model',type=Path,help='Existing local Transformers Whisper checkpoint, CUDA required')
    r.add_argument('--device',default='cuda:0');r.add_argument('--language',default='zh')
    r.add_argument('--budget',type=int,default=8)
    r.add_argument('--context',type=float,default=1.5);r.add_argument('--max-context',type=float,default=6)
    d=sub.add_parser('decide',help='Create a new review revision with a human decision')
    d.add_argument('review',type=Path);d.add_argument('segment_id');d.add_argument('action',choices=['accept','reject','revert'])
    d.add_argument('--reviewer',required=True);d.add_argument('--note',default='');d.add_argument('--out',type=Path,required=True)
    e=sub.add_parser('export',help='Export retained/accepted transcript plus complete review audit')
    e.add_argument('review',type=Path);e.add_argument('--out-dir',type=Path,required=True)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='review':
            if args.out.exists(): raise FileExistsError(f'output already exists: {args.out}')
            imported=load_import(args.input,media_root=args.media_root)
            if args.fixture:
                tool=FixtureTool.from_file(args.fixture)
            else:
                from .whisper_cuda import TransformersWhisperTool
                tool=TransformersWhisperTool(args.whisper_model,device=args.device,language=args.language)
            result=run_review(imported,tool,max_tool_calls=args.budget,
                              context_seconds=args.context,max_context_seconds=args.max_context)
            write_json_new(args.out,result)
            print(json.dumps({'review':str(args.out),'policy':result['policy']['kind'],
                              'tool_calls':result['policy']['tool_calls_used'],'pending_human_items':len(result['items'])}))
        elif args.command=='decide':
            result=decide(read_json(args.review),args.segment_id,args.action,reviewer=args.reviewer,note=args.note)
            write_json_new(args.out,result);print(json.dumps({'review':str(args.out),'decision':args.action}))
        else:
            review=read_json(args.review);doc=export_document(review)
            args.out_dir.mkdir(parents=True,exist_ok=False)
            write_json_new(args.out_dir/'transcript.json',doc)
            write_json_new(args.out_dir/'audit.json',review)
            with (args.out_dir/'transcript.txt').open('x',encoding='utf-8') as stream:
                for s in doc['segments']:
                    stream.write(f"[{s['start']:.3f}–{s['end']:.3f}] ({s['id']}, {s['review_status']}) {s['text']}\n")
            print(json.dumps({'export_dir':str(args.out_dir),'segments':len(doc['segments'])}))
        return 0
    except (OSError,ValueError,ToolError) as exc:
        print(f'error: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())
