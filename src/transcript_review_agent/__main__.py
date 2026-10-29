"""Run with python -m transcript_review_agent. Core uses only the standard library."""
import argparse
import json
from pathlib import Path
import sys

from .core import load_import, read_json, write_json_new, run_review, decide, export_document, ReviewInputError
from .tools import FixtureTool, ToolError


def add_backend_options(p,*,required):
    tools=p.add_mutually_exclusive_group(required=required)
    tools.add_argument('--fixture',type=Path)
    tools.add_argument('--whisper-model',type=Path,help='Existing local Transformers Whisper checkpoint, CUDA required')
    p.add_argument('--device',default='cuda:0');p.add_argument('--language',default='zh')
    p.add_argument('--budget',type=int,default=8)
    p.add_argument('--context',type=float,default=1.5);p.add_argument('--max-context',type=float,default=6)
    p.add_argument('--policy',choices=['fixed','agent'])
    p.add_argument('--agent-model',type=Path,help='Existing pinned local Phi-4-mini-instruct weights')
    p.add_argument('--max-llm-calls',type=int,default=12)
    p.add_argument('--max-actions-per-segment',type=int,default=4)
    p.add_argument('--max-total-seconds',type=float,default=120)


def make_runner(args,*,optional=False):
    """Return a lazy runner. Merely opening serve never imports or loads torch."""
    configured=bool(args.fixture or args.whisper_model)
    mode=args.policy or ('agent' if args.agent_model else 'fixed')
    if mode=='agent' and not args.agent_model:
        raise ReviewInputError('agent policy requires --agent-model with existing local weights')
    if mode=='fixed' and args.agent_model:
        raise ReviewInputError('--agent-model cannot be combined with --policy fixed')
    if not configured:
        if args.agent_model or args.policy:
            raise ReviewInputError('configure --whisper-model or --fixture before selecting a policy')
        if optional:return None,'fixed_baseline'
        raise ReviewInputError('an explicit evidence tool is required')

    def execute(imported):
        if args.fixture:tool=FixtureTool.from_file(args.fixture)
        else:
            from .whisper_cuda import TransformersWhisperTool
            tool=TransformersWhisperTool(args.whisper_model,device=args.device,language=args.language)
        if mode=='agent':
            from .agent import run_agent_review
            from .phi_cuda import PhiActionPolicy
            policy=PhiActionPolicy(args.agent_model,device=args.device)
            return run_agent_review(imported,tool,policy,max_tool_calls=args.budget,
                                    max_llm_calls=args.max_llm_calls,max_actions_per_segment=args.max_actions_per_segment,
                                    max_context_seconds=args.max_context,max_total_seconds=args.max_total_seconds)
        return run_review(imported,tool,max_tool_calls=args.budget,
                          context_seconds=args.context,max_context_seconds=args.max_context)
    return execute,'llm_agent' if mode=='agent' else 'fixed_baseline'


def parser():
    p=argparse.ArgumentParser(description='Local transcript review baseline harness. No correctness guarantee.')
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('review',help='Run explicit fixed baseline with a selected evidence tool')
    r.add_argument('input',type=Path);r.add_argument('--out',type=Path,required=True)
    r.add_argument('--media-root',type=Path)
    add_backend_options(r,required=True)
    d=sub.add_parser('decide',help='Create a new review revision with a human decision')
    d.add_argument('review',type=Path);d.add_argument('segment_id');d.add_argument('action',choices=['accept','reject','revert'])
    d.add_argument('--reviewer',required=True);d.add_argument('--note',default='');d.add_argument('--out',type=Path,required=True)
    e=sub.add_parser('export',help='Export retained/accepted transcript plus complete review audit')
    e.add_argument('review',type=Path);e.add_argument('--out-dir',type=Path,required=True)
    s=sub.add_parser('serve',help='Open a loopback-only Chinese review workbench; bundled synthetic demo by default')
    content=s.add_mutually_exclusive_group()
    content.add_argument('--review',type=Path);content.add_argument('--input',type=Path)
    s.add_argument('--port',type=int,default=8765)
    s.add_argument('--save-dir',type=Path,default=Path('.local/workbench/revisions'))
    add_backend_options(s,required=False)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='review':
            if args.out.exists(): raise FileExistsError(f'output already exists: {args.out}')
            imported=load_import(args.input,media_root=args.media_root)
            runner,_=make_runner(args)
            result=runner(imported)
            write_json_new(args.out,result)
            print(json.dumps({'review':str(args.out),'policy':result['policy']['kind'],
                              'tool_calls':result['policy']['tool_calls_used'],'pending_human_items':len(result['items'])}))
        elif args.command=='decide':
            result=decide(read_json(args.review),args.segment_id,args.action,reviewer=args.reviewer,note=args.note)
            write_json_new(args.out,result);print(json.dumps({'review':str(args.out),'decision':args.action}))
        elif args.command=='export':
            review=read_json(args.review);doc=export_document(review)
            args.out_dir.mkdir(parents=True,exist_ok=False)
            write_json_new(args.out_dir/'transcript.json',doc)
            write_json_new(args.out_dir/'audit.json',review)
            with (args.out_dir/'transcript.txt').open('x',encoding='utf-8') as stream:
                for s in doc['segments']:
                    stream.write(f"[{s['start']:.3f}–{s['end']:.3f}] ({s['id']}, {s['review_status']}) {s['text']}\n")
            print(json.dumps({'export_dir':str(args.out_dir),'segments':len(doc['segments'])}))
        else:
            from .server import serve
            runner,policy_kind=make_runner(args,optional=True)
            serve(args.review,port=args.port,save_dir=args.save_dir,input_path=args.input,
                  runner=runner,policy_kind=policy_kind)
        return 0
    except (OSError,ValueError,ToolError) as exc:
        print(f'error: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())
