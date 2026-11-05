import unittest
import test_app as base

class ClassicTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    request=base.AppTest.request
    create=base.AppTest.create
    record=base.AppTest.record
    def test_workspace_settings_survive_reload(self):
        cid=self.create()
        settings=dict(fields={'f1':dict(font='Arial',bold=True,width=160,format='Text')},formOrder=['f2','f1','f3','f4','f5'],formHidden=['f5'],markedRecords=[2],gridlines=False)
        r=self.request(f'/api/collections/{cid}/preferences','PUT',settings)
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.request(f'/api/collections/{cid}/preferences').json,settings)
    def test_batch_is_atomic_on_conflicting_revision(self):
        cid=self.create();a=self.record(cid,'Alpha');b=self.record(cid,'Beta')
        changes=[dict(_id=a,_rev=1,values={'f2':'5'}),dict(_id=b,_rev=999,values={'f2':'8'})]
        r=self.request(f'/api/collections/{cid}/records/batch','POST',dict(changes=changes))
        self.assertEqual(r.status_code,409)
        rows=self.request(f'/api/collections/{cid}/records').json['rows']
        self.assertTrue(all(float(row['f2'])==2.5 for row in rows))
    def test_batch_recalculates_and_undo_restores(self):
        cid=self.create();rid=self.record(cid)
        path=f'/api/collections/{cid}/records/batch'
        r=self.request(path,'POST',dict(changes=[dict(_id=rid,_rev=1,values={'f2':'4'})]))
        self.assertEqual(r.status_code,200,r.json)
        row=self.request(f'/api/collections/{cid}/records').json['rows'][0]
        self.assertEqual(float(row['f4']),500)
        self.assertEqual(self.request(path,'POST',dict(changes=[dict(_id=rid,_rev=2,values={'f2':'2.5'})])).status_code,200)
        self.assertEqual(float(self.request(f'/api/collections/{cid}/records').json['rows'][0]['f4']),312.5)
    def test_report_rename_delete_and_duplicate(self):
        cid=self.create();self.record(cid)
        p=dict(name='Original',config=dict(columns=['f1','f4'],sum='f4'))
        rid=self.request(f'/api/collections/{cid}/reports','POST',p).json['id']
        self.assertEqual(self.request('/api/reports/'+rid,'PUT',dict(name='Renamed')).status_code,200)
        self.assertIn(b'Renamed',self.client.get('/report/'+rid,headers=self.auth).data)
        report=self.request(f'/api/collections/{cid}/reports').json[0]
        r=self.request(f'/api/collections/{cid}/reports','POST',dict(name='Copy',config=report['config']))
        self.assertEqual(r.status_code,201,r.json)
        self.assertEqual(self.request('/api/reports/'+rid,'DELETE').status_code,200)
        self.assertEqual(self.client.get('/report/'+rid,headers=self.auth).status_code,404)
        self.assertEqual(len(self.request(f'/api/collections/{cid}/reports').json),1)
    def test_field_rename_keeps_data_and_rejects_duplicates(self):
        cid=self.create();self.record(cid)
        self.assertEqual(self.request(f'/api/collections/{cid}/fields/f1','PUT',dict(label='Client')).status_code,200)
        self.assertEqual(self.request('/api/collections').json[0]['fields'][0]['label'],'Client')
        self.assertEqual(self.request(f'/api/collections/{cid}/records').json['rows'][0]['f1'],'RichCo')
        self.assertEqual(self.request(f'/api/collections/{cid}/fields/f1','PUT',dict(label='Hours')).status_code,400)
    def test_classic_assets_are_served_and_shell_has_no_personal_content(self):
        html=self.client.get('/',headers=self.auth).data
        self.assertIn(b'classic.js',html)
        r=self.client.get('/static/classic.js',headers=self.auth)
        self.assertEqual(r.status_code,200)
        self.assertIn(b'Form Design',r.data)
        self.assertIn(b'ReportCreator',r.data)
        self.assertNotIn(b'AmericanRHAC',r.data)
        r.close()
