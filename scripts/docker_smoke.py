"""Exercise the running Docker app and its real MariaDB database."""
import base64
import http.cookiejar
import json
import os
import re
import time
import urllib.request

base=os.environ.get('APP_URL','http://localhost:8080')
auth='Basic '+base64.b64encode((os.environ.get('APP_USER','admin')+':'+os.environ['APP_PASSWORD']).encode()).decode()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
csrf=''
def call(path, method='GET', payload=None):
    headers={'Authorization':auth,'X-CSRF-Token':csrf}
    if payload is not None: headers['Content-Type']='application/json'
    req=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers,method=method)
    with opener.open(req,timeout=10) as r:
        raw=r.read().decode()
        return json.loads(raw) if r.headers.get_content_type()=='application/json' else raw
for attempt in range(45):
    try:
        html=call('/');break
    except Exception:
        if attempt==44: raise
        time.sleep(2)
csrf=json.loads(re.search(r'const CSRF=(.*?);',html).group(1))
s=call('/api/collections','POST',{'name':'Docker smoke test','fields':[{'label':'Customer','type':'text'},{'label':'Hours','type':'number'},{'label':'Rate','type':'currency'},{'label':'Total','type':'currency','formula':'f2*f3'}]})
cid=s['id']
rid=call(f'/api/collections/{cid}/records','POST',{'f1':'Sample customer','f2':'2.5','f3':'125'})['id']
row=call(f'/api/collections/{cid}/records')['rows'][0]
assert float(row['f4'])==312.5,row
row['f2']='3'
call(f'/api/collections/{cid}/records/{rid}','PUT',row)
report=call(f'/api/collections/{cid}/reports','POST',{'name':'Smoke totals','config':{'columns':['f1','f4'],'sum':'f4','group':'f1'}})
assert '375.00' in call('/report/'+report['id'])
assert 'Sample customer' in call(f'/api/collections/{cid}/export.csv')
call(f'/api/collections/{cid}/records/{rid}?revision=2','DELETE')
assert call(f'/api/collections/{cid}/records')['total']==0
print('Docker + MariaDB smoke test passed: create, calculate, update, report, export, delete.')
