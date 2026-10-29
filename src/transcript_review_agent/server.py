"""Loopback-only review workbench. Routes never expose an arbitrary filesystem."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from .core import MAX_MEDIA_BYTES, ReviewInputError, decide, export_document, load_import, now, read_json, run_review, validate_review, write_json_new

MAX_REVIEW_BYTES=32*1024*1024
MAX_MUTATION_BYTES=8192
WEB_ROOT=Path(__file__).parent/'web'
DEMO_ROOT=Path(__file__).parent/'demo'
CSP="default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


class ConflictError(ValueError):
    pass


def _source_digest(path: Path) -> str:
    digest=hashlib.sha256();total=0
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            total+=len(chunk)
            if total>MAX_MEDIA_BYTES:raise ReviewInputError('source exceeds media size limit')
            digest.update(chunk)
    return digest.hexdigest()


class ReviewWorkspace:
    """One loaded review, one fixed source, serialized append-only revisions."""
    def __init__(self,review_path: Path | str | None,save_dir: Path | str,*,input_path: Path | str | None=None):
        if review_path is not None and input_path is not None:raise ReviewInputError('choose a review or an input, not both')
        if input_path is not None:
            imported=load_import(input_path)
            # Zero calls creates the preservation contract; no tool is invoked.
            review=run_review(imported,None,max_tool_calls=0)
            for item in review['items']:
                item.update(status='pending',initial_status='pending',reason='not_checked')
            review['trace']=[]
            review['policy']={'kind':'not_run','llm_agent':False,'tool_calls_used':0}
            self.name=Path(input_path).name
        elif review_path is None:
            portable=read_json(DEMO_ROOT/'review.json',MAX_REVIEW_BYTES)
            if portable.get('format')!='portable-review-demo-0.1':
                raise ReviewInputError('unsupported bundled demo format')
            review=copy.deepcopy(portable['review'])
            declared=review['original']['source']['path']
            source=(DEMO_ROOT/declared).resolve()
            if not source.is_relative_to(DEMO_ROOT.resolve()):
                raise ReviewInputError('invalid bundled demo media')
            review['source_locator']={'resolved_path':str(source),'base_directory':str(DEMO_ROOT.resolve()),
                                      'declared_path':declared,'source_sha256':review['source_integrity']['source_sha256']}
            self.name=portable.get('title','合成語音示範')
        else:
            review=read_json(review_path,MAX_REVIEW_BYTES)
            self.name=Path(review_path).name
        validate_review(review)
        self.review=review
        self.source=Path(review['source_locator']['resolved_path'])
        if not self.source.is_file() or _source_digest(self.source)!=review['source_integrity']['source_sha256']:
            raise ReviewInputError('loaded source is missing or its hash differs from the review')
        self.source_signature=self._signature()
        self.save_dir=Path(save_dir).resolve()
        self.revision=0
        self.token=secrets.token_urlsafe(32)
        self.lock=threading.RLock()
        self.latest_revision=None
        self._runner=None
        self.job_state={'status':'idle','configured':False,'policy_kind':None,
                        'message':'顯示既有查核結果，未啟動新模型工作','error':None}
        self.job_done=threading.Event();self.job_done.set()

    def _signature(self):
        st=self.source.stat()
        return st.st_size,st.st_mtime_ns

    def source_unchanged(self) -> bool:
        try:return self._signature()==self.source_signature
        except OSError:return False

    def verify_source_content(self) -> None:
        try:
            if (not self.source_unchanged() or _source_digest(self.source)!=self.review['source_integrity']['source_sha256']):
                raise ConflictError('原始媒體內容已變更，請重新驗證後開啟')
        except OSError as exc:
            raise ConflictError('原始媒體無法驗證，請重新開啟') from exc

    @contextmanager
    def media_snapshot(self,start: int,end: int,*,capture: bool=True):
        """Serve bytes taken from the same pass that verifies the complete hash.

        A bounded spool avoids reopening a possibly replaced path after checking.
        It contains only the requested range and is removed when the request ends.
        """
        if not self.source_unchanged():raise ConflictError('原始媒體已變更，停止播放')
        self.save_dir.mkdir(parents=True,exist_ok=True)
        with tempfile.SpooledTemporaryFile(max_size=4*1024*1024,dir=self.save_dir,mode='w+b') as snapshot:
            digest=hashlib.sha256();offset=0
            try:
                with self.source.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        digest.update(chunk)
                        next_offset=offset+len(chunk)
                        if next_offset>MAX_MEDIA_BYTES:raise ConflictError('原始媒體超過大小上限')
                        if capture:
                            first,last=max(start,offset),min(end+1,next_offset)
                            if first<last:snapshot.write(chunk[first-offset:last-offset])
                        offset=next_offset
            except OSError as exc:raise ConflictError('原始媒體無法驗證，停止播放') from exc
            if offset!=self.source_signature[0] or digest.hexdigest()!=self.review['source_integrity']['source_sha256']:
                raise ConflictError('原始媒體內容已變更，停止播放以保護查核依據')
            snapshot.seek(0)
            yield snapshot

    def snapshot(self) -> dict:
        with self.lock:
            # Private absolute locators remain in audit downloads, not the UI payload.
            review=copy.deepcopy(self.review)
            review.pop('source_locator',None)
            return {'name':self.name,'revision':self.revision,'review':review,'mutation_token':self.token,
                    'source':{'name':self.source.name,'available':self.source_unchanged(),
                              'seconds':self.review['original']['source']['duration']},
                    'mode':'new_input' if self.review['policy'].get('kind')=='not_run' else 'existing_review',
                    'job':copy.deepcopy(self.job_state)}

    def configure_runner(self,runner,*,policy_kind: str):
        """Configuration is supplied only by local CLI code, never by HTTP data."""
        if not callable(runner) or policy_kind not in {'fixed_baseline','llm_agent'}:
            raise ReviewInputError('invalid local runner configuration')
        with self.lock:
            if self.job_state['status']=='running':raise ConflictError('查核工作正在執行')
            self._runner=runner
            self.job_state.update(configured=True,policy_kind=policy_kind,message='模型已設定，尚未執行本次查核')

    def start_job(self,payload: dict) -> dict:
        if not isinstance(payload,dict) or set(payload)!={'revision'}:
            raise ReviewInputError('run request accepts only the current revision')
        with self.lock:
            if not self._runner:raise ReviewInputError('尚未在本機 CLI 設定查核模型')
            if self.job_state['status']=='running':raise ConflictError('已有查核工作正在執行')
            if type(payload['revision']) is not int or payload['revision']!=self.revision:
                raise ConflictError('畫面已有較新修訂，請重新載入')
            if self.review['decisions']:
                raise ConflictError('此工作階段已有人工決策，請另開輸入以保留完整歷史')
            self.verify_source_content()
            imported={'document':copy.deepcopy(self.review['original']),'source_path':str(self.source),
                      'media_root':self.review['source_locator']['base_directory'],
                      **self.review['source_integrity']}
            expected_revision=self.revision
            self.job_state.update(status='running',started_at=now(),finished_at=None,error=None,
                                  message='正在載入本機模型並執行查核；畫面保留上一份結果')
            self.job_done.clear()

            def work():
                try:
                    updated=self._runner(imported)
                    validate_review(updated)
                    if updated['source_integrity']!=self.review['source_integrity']:
                        raise ReviewInputError('查核結果與本次輸入不一致')
                    with self.lock:
                        if self.revision!=expected_revision:raise ConflictError('查核期間修訂已變更')
                        self.verify_source_content()
                        destination=self.save_dir/f'review-job-{self.revision+1:05d}-{uuid4().hex[:12]}.json'
                        write_json_new(destination,updated)
                        self.review=updated;self.revision+=1;self.latest_revision=destination
                        self.job_state.update(status='completed',finished_at=now(),
                                              message='本次查核流程結束，請人工檢視候選與未解項目')
                except Exception as exc:
                    with self.lock:
                        self.job_state.update(status='error',finished_at=now(),error=str(exc)[:1000],
                                              message='本次查核失敗，上一份資料與決策保持不變')
                finally:self.job_done.set()
            threading.Thread(target=work,name='transcript-review-job',daemon=True).start()
            return self.snapshot()

    def apply_decision(self,payload: dict) -> dict:
        if not isinstance(payload,dict):raise ReviewInputError('decision must be an object')
        if set(payload)-{'segment_id','action','reviewer','note','revision'}:
            raise ReviewInputError('unknown decision fields')
        sid,action,reviewer,note=map(payload.get,['segment_id','action','reviewer','note'])
        if (not isinstance(sid,str) or not isinstance(action,str) or not isinstance(reviewer,str)
                or not 1<=len(reviewer.strip())<=100 or not isinstance(note,str) or len(note)>2000):
            raise ReviewInputError('invalid decision fields')
        with self.lock:
            if self.job_state['status']=='running':raise ConflictError('查核工作執行中，請等待結果再決定')
            if isinstance(payload.get('revision'),bool) or payload.get('revision')!=self.revision:
                raise ConflictError('畫面已有較新修訂，請重新載入後再決定')
            self.verify_source_content()
            updated=decide(self.review,sid,action,reviewer=reviewer.strip(),note=note)
            validate_review(updated)
            filename=f'review-{self.revision+1:05d}-{uuid4().hex[:12]}.json'
            destination=self.save_dir/filename
            write_json_new(destination,updated)
            self.review=updated
            self.revision+=1
            self.latest_revision=destination
            return self.snapshot()

    def export(self,kind: str) -> tuple[bytes,str]:
        with self.lock:
            if kind=='audit.json':
                value=self.review
            elif kind=='transcript.json':
                value=export_document(self.review)
            elif kind=='transcript.txt':
                doc=export_document(self.review)
                lines=[f"[{s['start']:.3f}–{s['end']:.3f}] ({s['id']}, {s['review_status']}) {s['text']}" for s in doc['segments']]
                return ('\n'.join(lines)+'\n').encode('utf-8'),'text/plain; charset=utf-8'
            else:raise ReviewInputError('unknown export')
            return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'),'application/json; charset=utf-8'


def _byte_range(value: str | None,size: int) -> tuple[int,int,bool]:
    if value is None:return 0,size-1,False
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
    if not match or not any(match.groups()):raise ValueError('only a single byte range is supported')
    first,last=match.groups()
    if not first:
        suffix=int(last)
        if suffix<=0:raise ValueError('invalid suffix range')
        start,end=max(0,size-suffix),size-1
    else:
        start=int(first);end=min(int(last),size-1) if last else size-1
    if not 0<=start<=end<size:raise ValueError('unsatisfiable range')
    return start,end,True


def make_server(workspace: ReviewWorkspace,*,port: int=8765) -> ThreadingHTTPServer:
    if isinstance(port,bool) or not isinstance(port,int) or not 0<=port<=65535:
        raise ReviewInputError('invalid loopback port')

    class Handler(BaseHTTPRequestHandler):
        server_version='TranscriptReview/0.1'
        protocol_version='HTTP/1.0'

        def log_message(self,format,*args):
            # Request URLs and transcript data are not written to process logs.
            pass

        def setup(self):
            super().setup();self.connection.settimeout(10)

        def _headers(self,status: int,content_type: str,length: int,extra=None):
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(length))
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',CSP)
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            for key,value in (extra or {}).items():self.send_header(key,value)
            self.end_headers()

        def _send(self,status: int,data: bytes,content_type='application/json; charset=utf-8',extra=None):
            self._headers(status,content_type,len(data),extra)
            if self.command!='HEAD':self.wfile.write(data)

        def _json(self,status: int,value: dict):
            self._send(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'))

        def _trusted_request(self,mutation=False) -> bool:
            host=f'127.0.0.1:{self.server.server_address[1]}'
            origins=self.headers.get_all('Origin',[])
            if self.headers.get_all('Host',[])!=[host]:
                self._json(403,{'error':'不允許的 Host'});return False
            expected=f'http://{host}'
            if len(origins)>1 or (origins and origins[0]!=expected) or (mutation and origins!=[expected]):
                self._json(403,{'error':'不允許的 Origin'});return False
            site=self.headers.get('Sec-Fetch-Site')
            if site and site not in {'same-origin','none'}:
                self._json(403,{'error':'拒絕跨站請求'});return False
            if mutation:
                tokens=self.headers.get_all('X-Review-Token',[])
                if len(tokens)!=1 or not secrets.compare_digest(tokens[0],workspace.token):
                    self._json(403,{'error':'變更 token 無效，請重新載入'});return False
            parsed=urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                self._json(400,{'error':'不支援的請求路徑'});return False
            return True

        def do_HEAD(self):self.do_GET()

        def do_GET(self):
            if not self._trusted_request():return
            assets={'/':'index.html','/assets/workbench.css':'workbench.css','/assets/workbench.js':'workbench.js'}
            if self.path in assets:
                target=WEB_ROOT/assets[self.path]
                types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}
                self._send(200,target.read_bytes(),types[target.suffix]);return
            if self.path=='/api/state':self._json(200,workspace.snapshot());return
            if self.path=='/media/source':
                if not workspace.source_unchanged():
                    self._json(409,{'error':'原始媒體已變更，停止播放以保護查核依據'});return
                size=workspace.source_signature[0]
                try:
                    if len(self.headers.get_all('Range',[]))>1:raise ValueError('duplicate ranges')
                    start,end,partial=_byte_range(self.headers.get('Range'),size)
                except (ValueError,OverflowError):
                    self._send(416,b'',extra={'Content-Range':f'bytes */{size}'});return
                extras={'Accept-Ranges':'bytes'}
                if partial:extras['Content-Range']=f'bytes {start}-{end}/{size}'
                content_type=mimetypes.guess_type(workspace.source.name)[0] or 'application/octet-stream'
                try:
                    with workspace.media_snapshot(start,end,capture=self.command!='HEAD') as snapshot:
                        self._headers(206 if partial else 200,content_type,end-start+1,extras)
                        if self.command=='HEAD':return
                        while chunk:=snapshot.read(65536):self.wfile.write(chunk)
                except ConflictError as exc:self._json(409,{'error':str(exc)})
                except (BrokenPipeError,ConnectionResetError):pass
                return
            downloads={'/download/transcript.json':'transcript.json','/download/transcript.txt':'transcript.txt','/download/audit.json':'audit.json'}
            if self.path in downloads:
                name=downloads[self.path];data,kind=workspace.export(name)
                self._send(200,data,kind,{'Content-Disposition':f'attachment; filename="{name}"'});return
            self._json(404,{'error':'找不到此路由'})

        def do_POST(self):
            if not self._trusted_request(mutation=True):return
            if self.path not in {'/api/decision','/api/run'}:self._json(404,{'error':'找不到此變更路由'});return
            if self.headers.get('Transfer-Encoding') or self.headers.get_all('Content-Length',[])==[]:
                self._json(400,{'error':'必須提供受限的 Content-Length'});return
            lengths=self.headers.get_all('Content-Length',[])
            try:length=int(lengths[0])
            except (ValueError,IndexError):length=-1
            if len(lengths)!=1 or not 0<length<=MAX_MUTATION_BYTES:
                self._json(413,{'error':'變更內容超過大小上限'});return
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                self._json(415,{'error':'變更內容必須為 JSON'});return
            try:
                data=self.rfile.read(length)
                if len(data)!=length:raise ReviewInputError('incomplete request body')
                payload=json.loads(data.decode('utf-8'))
                if self.path=='/api/run':self._json(202,workspace.start_job(payload))
                else:self._json(200,workspace.apply_decision(payload))
            except ConflictError as exc:self._json(409,{'error':str(exc)})
            except (ValueError,UnicodeError) as exc:self._json(400,{'error':str(exc)})
            except OSError:self._json(500,{'error':'修訂寫入失敗；尚未變更目前決策'})

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def serve(review_path: Path | None,*,port: int=8765,save_dir: Path | str='.local/workbench/revisions',
          input_path: Path | None=None,runner=None,policy_kind: str='fixed_baseline') -> None:
    workspace=ReviewWorkspace(review_path,save_dir,input_path=input_path)
    if runner is not None:workspace.configure_runner(runner,policy_kind=policy_kind)
    server=make_server(workspace,port=port)
    print(f'Workbench: http://127.0.0.1:{server.server_address[1]}/',flush=True)
    print('Loopback only. Existing review; no model job started. Ctrl+C to stop.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
