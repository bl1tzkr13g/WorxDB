import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_DIR = tempfile.TemporaryDirectory()
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(TEST_DIR.name)/'test.db'), DATA_DIR=TEST_DIR.name, APP_PASSWORD='test-password', SECRET_KEY='test-session-secret')
import app as module

class AppTest(unittest.TestCase):
    def setUp(self):
        module.meta.drop_all(module.engine)
        module.init_db()
        self.client=module.app.test_client()
        self.auth={'Authorization':'Basic '+base64.b64encode(b'admin:test-password').decode()}
        self.client.get('/',headers=self.auth)
        with self.client.session_transaction() as s: self.csrf=s['csrf']
        self.headers={**self.auth,'X-CSRF-Token':self.csrf}
    def request(self,path,method='GET',data=None):
        return self.client.open(path,method=method,json=data,headers=self.headers)
    def create(self):
        r=self.request('/api/collections','POST',{'name':'Jobs','fields':[{'label':'Customer','type':'text'},{'label':'Hours','type':'number'},{'label':'Rate','type':'currency'},{'label':'Total','type':'currency','formula':'f2 * f3'},{'label':'Date','type':'date'}]})
        self.assertEqual(r.status_code,201,r.json)
        return r.json['id']
    def record(self,cid,customer='RichCo',hours='2.5'):
        r=self.request(f'/api/collections/{cid}/records','POST',dict(f1=customer,f2=hours,f3='125',f5='2026-11-04'))
        self.assertEqual(r.status_code,201,r.json)
        return r.json['id']
    def test_auth_and_csrf(self):
        self.assertEqual(self.client.get('/api/collections').status_code,401)
        self.assertEqual(self.client.post('/api/collections',headers=self.auth,json={}).status_code,403)
    def test_crud_calculation_and_stale_update(self):
        cid=self.create(); rid=self.record(cid)
        row=self.request(f'/api/collections/{cid}/records').json['rows'][0]
        self.assertEqual(float(row['f4']),312.5)
        row['f2']='3'
        self.assertEqual(self.request(f'/api/collections/{cid}/records/{rid}','PUT',row).status_code,200)
        self.assertEqual(self.request(f'/api/collections/{cid}/records/{rid}','PUT',row).status_code,409)
        self.assertEqual(self.request(f'/api/collections/{cid}/records/{rid}?revision=1','DELETE').status_code,409)
        self.assertEqual(self.request(f'/api/collections/{cid}/records/{rid}?revision=2','DELETE').status_code,200)
    def test_typed_sort_filter(self):
        cid=self.create(); self.record(cid,'Alpha','2');self.record(cid,'Beta','10')
        r=self.request(f'/api/collections/{cid}/records?sort=f2&direction=desc').json
        self.assertEqual(r['rows'][0]['f1'],'Beta')
        r=self.request(f'/api/collections/{cid}/records?filter_field=f2&filter_op=gt&filter_value=5').json
        self.assertEqual(r['total'],1)
        self.assertEqual(self.request(f'/api/collections/{cid}/records?query=Alpha').json['total'],1)
    def preview(self,text):
        return self.client.post('/api/import/preview',headers=self.headers,data={'file':(io.BytesIO(text.encode()),'data.csv')})
    def test_csv_import_and_leading_zeroes(self):
        p=self.preview('Customer,ZIP\nRichCo,00123\n').json
        self.assertEqual(p['fields'][1]['type'],'text')
        r=self.request('/api/import/commit','POST',dict(name='Imported',token=p['token'],fields=p['fields']))
        self.assertEqual(r.status_code,201,r.json)
        rows=self.request(f"/api/collections/{r.json['id']}/records").json['rows']
        self.assertEqual(rows[0]['f2'],'00123')
    def test_import_is_atomic_on_invalid_type(self):
        p=self.preview('Customer,Hours\nAlpha,2\nBeta,bad\n').json
        p['fields'][1]['type']='number'
        r=self.request('/api/import/commit','POST',dict(name='Fail',token=p['token'],fields=p['fields']))
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.request('/api/collections').json,[])
    def test_bad_csv_shape_and_duplicate_names(self):
        self.assertEqual(self.preview('A,B\n1\n').status_code,400)
        r=self.request('/api/collections','POST',dict(name='Bad',fields=[dict(label='A'),dict(label='a')]))
        self.assertEqual(r.status_code,400)
    def test_report_groups_totals_filter_and_html_escaping(self):
        cid=self.create();self.record(cid,'<script>alert(1)</script>');self.record(cid,'Beta','4')
        config=dict(columns=['f1','f4'],group='f1',sum='f4',filter_field='f2',filter_op='lt',filter_value='4')
        r=self.request(f'/api/collections/{cid}/reports','POST',dict(name='Job totals',config=config))
        self.assertEqual(r.status_code,201,r.json)
        page=self.client.get('/report/'+r.json['id'],headers=self.auth)
        self.assertIn(b'312.50',page.data)
        self.assertIn(b'&lt;script&gt;',page.data)
        self.assertNotIn(b'<script>alert',page.data)
        self.assertNotIn(b'500.00',page.data)
    def test_invalid_formulas_dates_and_precision(self):
        for formula in ['__import__("os")','f99+1','2**100000']:
            r=self.request('/api/collections','POST',dict(name='Unsafe',fields=[dict(label='Calc',type='number',formula=formula)]))
            self.assertEqual(r.status_code,400)
        cid=self.create()
        self.assertEqual(self.request(f'/api/collections/{cid}/records','POST',dict(f2='1.1234567')).status_code,400)
        self.assertEqual(self.request(f'/api/collections/{cid}/records','POST',dict(f5='11/04/26')).status_code,400)
    def test_csv_export_neutralizes_formula(self):
        cid=self.create();self.record(cid,'=1+1')
        r=self.client.get(f'/api/collections/{cid}/export.csv',headers=self.auth)
        self.assertIn(b"'=1+1",r.data)
    def test_wdb_converter_failures_are_actionable(self):
        with patch('app.subprocess.run',side_effect=FileNotFoundError):
            r=self.client.post('/api/import/preview',headers=self.headers,data={'file':(io.BytesIO(b'WDB test'),'sample.wdb')})
        self.assertEqual(r.status_code,400)
        self.assertIn('converter',r.json['error'])
    def test_wdb_converter_output_routes_to_review(self):
        def fake_converter(command,**kwargs):
            Path(command[command.index('-o')+1]).write_text('Name,ZIP\nSample,00123\n')
            import subprocess
            return subprocess.CompletedProcess(command,0,b'',b'')
        with patch('app.subprocess.run',side_effect=fake_converter):
            r=self.client.post('/api/import/preview',headers=self.headers,data={'file':(io.BytesIO(b'WDB test'),'sample.wdb')})
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['sample'][0][1],'00123')
        self.assertTrue(r.json['warnings'])

if __name__=='__main__':unittest.main()
