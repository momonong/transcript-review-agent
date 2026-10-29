import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import wave

from transcript_review_agent.core import load_import, run_review, write_json_new
from transcript_review_agent.tools import FixtureTool
from transcript_review_agent.server import ReviewWorkspace, make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        local=Path(__file__).resolve().parents[1]/'.local'/'test-temp'
        local.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=local)
        self.root=Path(self.tmp.name)
        with wave.open(str(self.root/'source.wav'),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
            stream.writeframes(b'\0\0'*16000)
        doc={'source':{'path':'source.wav','duration':1},'segments':[
            {'id':'s1','start':0,'end':1,'text':'<img src=x onerror=alert(1)> 我拿了十五個。'}]}
        write_json_new(self.root/'input.json',doc)
        review=run_review(load_import(self.root/'input.json'),FixtureTool({'s1':{'text':'我、我沒有拿十五個。我拿了五十個。'}}))
        write_json_new(self.root/'review.json',review)
        self.workspace=ReviewWorkspace(self.root/'review.json',self.root/'revisions')
        self.server=make_server(self.workspace,port=0)
        self.port=self.server.server_address[1]
        self.origin=f'http://127.0.0.1:{self.port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request(method,path,body=body,headers=headers or {})
        response=conn.getresponse();data=response.read();status=response.status;response_headers=dict(response.getheaders());conn.close()
        return status,data,response_headers

    def decision(self,action,revision=0,**extra):
        payload=json.dumps({'segment_id':'s1','action':action,'reviewer':'測試者','note':'','revision':revision},ensure_ascii=False).encode('utf-8')
        headers={'Content-Type':'application/json','Origin':self.origin,'X-Review-Token':self.workspace.token}
        headers.update(extra)
        return self.request('POST','/api/decision',payload,headers)

    def test_only_whitelisted_routes_and_exact_host(self):
        self.assertEqual(self.request('GET','/')[0],200)
        self.assertEqual(self.request('GET','/../../README.md')[0],404)
        self.assertEqual(self.request('GET','/media/source?path=../secret')[0],404)
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/state',headers={'Origin':'https://evil.example'})[0],403)

    def test_mutations_require_origin_and_token(self):
        self.assertEqual(self.decision('accept',**{'X-Review-Token':'wrong'})[0],403)
        self.assertEqual(self.decision('accept',Origin='https://evil.example')[0],403)
        status,_,_=self.request('POST','/api/decision',b'{}',{'Content-Type':'application/json','X-Review-Token':self.workspace.token})
        self.assertEqual(status,403)
        self.assertEqual(self.workspace.revision,0)

    def test_accept_revert_save_new_revisions_and_export(self):
        status,data,_=self.decision('accept')
        self.assertEqual(status,200);self.assertEqual(json.loads(data)['revision'],1)
        self.assertEqual(self.decision('revert',revision=0)[0],409)
        self.assertEqual(self.decision('revert',revision=1)[0],200)
        self.assertEqual(len(list((self.root/'revisions').glob('*.json'))),2)
        status,data,_=self.request('GET','/download/transcript.json')
        self.assertEqual(status,200)
        self.assertIn('<img',json.loads(data)['segments'][0]['text'])
        self.assertEqual(json.loads(data)['segments'][0]['review_status'],'reverted')
        self.assertEqual(len(self.workspace.review['decisions']),2)
        self.assertEqual(json.loads((self.root/'review.json').read_text(encoding='utf-8'))['decisions'],[])

    def test_media_supports_bounded_single_ranges(self):
        status,data,headers=self.request('GET','/media/source',headers={'Range':'bytes=0-43'})
        self.assertEqual(status,206);self.assertEqual(len(data),44);self.assertTrue(data.startswith(b'RIFF'))
        self.assertTrue(headers['Content-Range'].startswith('bytes 0-43/'))
        self.assertEqual(self.request('GET','/media/source',headers={'Range':'bytes=0-1,5-6'})[0],416)
        self.assertEqual(self.request('GET','/media/source',headers={'Range':'bytes=999999-'})[0],416)
        status,data,_=self.request('GET','/media/source',headers={'Range':'bytes=-12'})
        self.assertEqual(status,206);self.assertEqual(len(data),12)
        status,data,headers=self.request('HEAD','/media/source',headers={'Range':'bytes=0-43'})
        self.assertEqual(status,206);self.assertEqual(data,b'');self.assertEqual(headers['Content-Length'],'44')

    def test_source_change_is_not_served_as_verified_audio(self):
        with (self.root/'source.wav').open('ab') as stream:stream.write(b'x')
        self.assertEqual(self.request('GET','/media/source')[0],409)

    def test_same_size_change_with_restored_mtime_cannot_play_or_accept(self):
        source=self.root/'source.wav';st=source.stat()
        with source.open('r+b') as stream:stream.seek(100);stream.write(b'\x01')
        os.utime(source,ns=(st.st_atime_ns,st.st_mtime_ns))
        self.assertEqual(self.request('GET','/media/source',headers={'Range':'bytes=0-43'})[0],409)
        self.assertEqual(self.decision('accept')[0],409)

    def test_transcript_is_json_data_not_executable_markup(self):
        status,data,headers=self.request('GET','/api/state')
        self.assertEqual(status,200);self.assertIn('application/json',headers['Content-Type'])
        self.assertIn('<img',json.loads(data)['review']['items'][0]['original_text'])
        self.assertIn("default-src 'self'",headers['Content-Security-Policy'])
        _,html,_=self.request('GET','/')
        self.assertNotIn(b'<img src=x',html)

    def test_oversized_body_and_non_json_mutation_are_rejected(self):
        headers={'Origin':self.origin,'X-Review-Token':self.workspace.token,'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/decision',b' '*8193,headers)[0],413)
        headers['Content-Type']='text/plain'
        self.assertEqual(self.request('POST','/api/decision',b'{}',headers)[0],415)
        self.assertEqual(self.workspace.revision,0)

    def test_bundled_demo_is_portable_and_previously_computed(self):
        from transcript_review_agent.server import DEMO_ROOT
        payload=(DEMO_ROOT/'review.json').read_text(encoding='utf-8')
        self.assertNotIn('D:/projects/',payload);self.assertNotIn('C:/Users/',payload)
        demo=ReviewWorkspace(None,self.root/'demo-revisions')
        self.assertEqual(len(demo.review['items']),4)
        self.assertEqual(demo.review['demo']['kind'],'synthetic_verified_gpu_snapshot')
        self.assertEqual(demo.snapshot()['job']['status'],'idle')
        self.assertTrue(demo.source_unchanged())

    def test_background_job_is_explicit_and_preserves_prior_review_on_failure(self):
        self.assertEqual(self.workspace.snapshot()['job']['status'],'idle')
        self.assertEqual(self.workspace.snapshot()['job']['configured'],False)
        started=threading.Event();release=threading.Event()
        def runner(imported):
            started.set();release.wait(2)
            raise RuntimeError('synthetic runner failure')
        self.workspace.configure_runner(runner,policy_kind='fixed_baseline')
        previous=self.workspace.review['items'][0]['candidate_text']
        response=self.workspace.start_job({'revision':0})
        self.assertEqual(response['job']['status'],'running')
        self.assertTrue(started.wait(1))
        self.assertEqual(self.decision('accept')[0],409)
        release.set();self.assertTrue(self.workspace.job_done.wait(2))
        self.assertEqual(self.workspace.snapshot()['job']['status'],'error')
        self.assertEqual(self.workspace.review['items'][0]['candidate_text'],previous)
        self.assertEqual(self.workspace.revision,0)

    def test_background_job_result_is_saved_and_requires_no_prior_human_decisions(self):
        self.workspace.configure_runner(lambda imported:run_review(imported,FixtureTool({'s1':{'text':'新候選'}})),policy_kind='fixed_baseline')
        self.workspace.start_job({'revision':0})
        self.assertTrue(self.workspace.job_done.wait(2))
        self.assertEqual(self.workspace.snapshot()['job']['status'],'completed')
        self.assertEqual(self.workspace.review['items'][0]['candidate_text'],'新候選')
        self.assertEqual(self.workspace.revision,1)
        self.assertEqual(len(list((self.root/'revisions').glob('*.json'))),1)
        self.assertEqual(self.decision('accept',revision=1)[0],200)
        with self.assertRaises(ValueError):self.workspace.start_job({'revision':2})


if __name__=='__main__':unittest.main()
