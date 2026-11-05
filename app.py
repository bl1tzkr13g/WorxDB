import ast
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import subprocess
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, session
from sqlalchemy import (Column, Date, Integer, MetaData, Numeric, String, Table, Text,
                        create_engine, delete, func, insert, select, update)
from sqlalchemy.engine import URL
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY', secrets.token_hex(32)),
                  MAX_CONTENT_LENGTH=20*1024*1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Strict')
DATA = Path(os.environ.get('DATA_DIR', '/tmp/worxdb'))
DATA.mkdir(parents=True, exist_ok=True)
url = os.environ.get('DATABASE_URL') or URL.create('mysql+pymysql', username=os.environ.get('DB_USER', 'worxdb'), password=os.environ.get('DB_PASSWORD', ''), host=os.environ.get('DB_HOST', 'db'), database=os.environ.get('DB_NAME', 'worxdb'), query={'charset': 'utf8mb4'})
engine = create_engine(url, pool_pre_ping=True)
meta = MetaData()
collections = Table('wb_collections', meta, Column('id', String(32), primary_key=True), Column('name', String(120), nullable=False), Column('fields', Text, nullable=False), Column('source', Text), Column('created', String(32)))
reports = Table('wb_reports', meta, Column('id', String(32), primary_key=True), Column('collection_id', String(32), nullable=False), Column('name', String(120), nullable=False), Column('config', Text, nullable=False))
TYPES = {'text': Text, 'number': Numeric(24, 6), 'currency': Numeric(24, 2), 'date': Date, 'boolean': Integer}

@app.before_request
def guard():
    user, password = os.environ.get('APP_USER', 'admin'), os.environ.get('APP_PASSWORD', '')
    auth = request.authorization
    if not password:
        return jsonify(error='APP_PASSWORD must be configured before using WorxDB.'), 503
    if not auth or not hmac.compare_digest(auth.username or '', user) or not hmac.compare_digest(auth.password or '', password):
        return Response('Sign in to WorxDB', 401, {'WWW-Authenticate': 'Basic realm="WorxDB"'})
    session.setdefault('csrf', secrets.token_hex(24))
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
        abort(403, 'Reload the page before saving.')

@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if isinstance(exc, (ValueError, InvalidOperation)):
        return jsonify(error=str(exc)), 400
    app.logger.exception('Request failed')
    return jsonify(error='The operation failed. No record changes were committed. Check server logs.'), 500


def init_db():
    meta.create_all(engine)


def spec(cid):
    with engine.connect() as conn:
        r = conn.execute(select(collections).where(collections.c.id == cid)).mappings().first()
    if not r:
        abort(404, 'Database not found')
    d = dict(r)
    d['fields'] = json.loads(d['fields'])
    return d


def table_for(s):
    return Table('wb_data_' + s['id'], MetaData(), Column('_id', Integer, primary_key=True, autoincrement=True), Column('_rev', Integer, nullable=False, default=1), *[Column(f['key'], TYPES[f['type']], nullable=True) for f in s['fields'] if not f.get('formula')])


def fields_valid(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 80:
        raise ValueError('Choose between 1 and 80 fields.')
    out = []
    names = set()
    for i, f in enumerate(fields):
        label = str(f.get('label', '')).strip()
        if not label or len(label) > 120 or label.casefold() in names:
            raise ValueError('Field names must be unique and between 1 and 120 characters.')
        names.add(label.casefold())
        kind = f.get('type', 'text')
        if kind not in TYPES:
            raise ValueError('Unknown field type')
        formula = str(f.get('formula', '')).strip()
        if formula:
            if kind not in ('number', 'currency'):
                raise ValueError('Calculated fields must be number or currency fields.')
            calc(formula, {f'f{n+1}': 1 for n in range(i)})
        out.append(dict(key=f'f{i+1}', label=label, type=kind, required=bool(f.get('required')), formula=formula))
    return out


def calc(expression, row):
    if len(expression) > 240:
        raise ValueError('Formula is too long')
    try:
        root = ast.parse(expression, mode='eval')
    except SyntaxError:
        raise ValueError('Use arithmetic formulas such as f1 * f2.')
    def visit(n):
        if isinstance(n, ast.Expression): return visit(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float): return Decimal(str(n.value))
        if isinstance(n, ast.Name) and n.id in row: return Decimal(str(row[n.id] or 0))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)): return visit(n.operand) * (-1 if isinstance(n.op, ast.USub) else 1)
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Add): return a+b
            if isinstance(n.op, ast.Sub): return a-b
            if isinstance(n.op, ast.Mult): return a*b
            if b == 0: raise ValueError('Formula divides by zero')
            return a/b
        raise ValueError('Formulas allow numbers, earlier numeric field IDs, +, -, *, / and parentheses.')
    return visit(root)


def convert(value, field):
    if value is None or value == '':
        if field.get('required'): raise ValueError(f"{field['label']} is required")
        return None
    kind = field['type']
    if kind == 'text': return str(value)
    if kind in ('number', 'currency'):
        d = Decimal(str(value))
        scale = 2 if kind == 'currency' else 6
        if not d.is_finite() or abs(d) >= Decimal(10)**(24-scale): raise ValueError('Number out of range')
        if d != d.quantize(Decimal(10)**(-scale)): raise ValueError(f'Maximum {scale} decimal places')
        return d
    if kind == 'date': return date.fromisoformat(str(value))
    if str(value).lower() in ('true', '1', 'yes'): return 1
    if str(value).lower() in ('false', '0', 'no'): return 0
    raise ValueError('Use yes/no, true/false or 1/0')


def values(payload, s):
    result = {}
    for f in s['fields']:
        if f.get('formula'): continue
        try: result[f['key']] = convert(payload.get(f['key']), f)
        except (ValueError, InvalidOperation) as exc: raise ValueError(f"{f['label']}: {exc}")
    # Validate calculated values too; retain source numeric values in MariaDB.
    expanded = dict(result)
    for f in s['fields']:
        if f.get('formula'):
            try: expanded[f['key']] = calc(f['formula'], expanded)
            except (ValueError, InvalidOperation) as exc: raise ValueError(f"{f['label']}: {exc}")
    return result


def expanded(row, s):
    r = dict(row)
    for f in s['fields']:
        if f.get('formula'):
            try: r[f['key']] = calc(f['formula'], r)
            except (ValueError, InvalidOperation): r[f['key']] = None
    return {k: (str(v) if isinstance(v, (Decimal, date)) else v) for k, v in r.items()}


def filtered_rows(s, config):
    t = table_for(s)
    with engine.connect() as conn:
        rows = [expanded(r, s) for r in conn.execute(select(t)).mappings()]
    fields = {f['key']: f for f in s['fields']}
    query = str(config.get('query', '')).casefold()
    if query: rows = [r for r in rows if any(query in str(r.get(k) or '').casefold() for k in fields)]
    key, op, val = config.get('filter_field'), config.get('filter_op', 'contains'), config.get('filter_value', '')
    if key:
        if key not in fields: raise ValueError('Unknown filter field')
        f = fields[key]
        def match(r):
            v = r.get(key)
            if op == 'blank': return v is None or v == ''
            if op == 'contains': return str(val).casefold() in str(v or '').casefold()
            expected = convert(val, f)
            actual = convert(v, f)
            if op == 'eq': return actual == expected
            if actual is None or expected is None: return False
            if op == 'gt': return actual > expected
            if op == 'lt': return actual < expected
            raise ValueError('Unknown filter operator')
        rows = [r for r in rows if match(r)]
    sort = config.get('sort')
    if sort:
        if sort not in fields: raise ValueError('Unknown sort field')
        f = fields[sort]
        rows.sort(key=lambda r: (r.get(sort) is None, convert(r.get(sort), {**f, 'required': False}) or (Decimal(0) if f['type'] in ('number','currency','boolean') else date.min if f['type']=='date' else '')), reverse=config.get('direction') == 'desc')
    return rows

@app.get('/')
def home():
    return render_template('index.html', csrf=session['csrf'])

@app.get('/api/collections')
def list_collections():
    with engine.connect() as conn:
        result = []
        for r in conn.execute(select(collections).order_by(collections.c.name)).mappings():
            s = dict(r); s['fields'] = json.loads(s['fields'])
            s['count'] = conn.scalar(select(func.count()).select_from(table_for(s)))
            result.append(s)
    return jsonify(result)


def create_collection(name, fields, records, source=''):
    name = str(name).strip()
    if not 1 <= len(name) <= 120: raise ValueError('Database name must be 1–120 characters')
    s = dict(id=uuid.uuid4().hex, name=name, fields=fields_valid(fields), source=source, created=datetime.now().isoformat())
    clean = []
    for i, row in enumerate(records):
        try: clean.append(values({f'f{j+1}': v for j, v in enumerate(row)}, s))
        except ValueError as exc: raise ValueError(f'Record {i+1}: {exc}. Nothing imported.')
    t = table_for(s)
    t.create(engine)
    try:
        with engine.begin() as conn:
            conn.execute(insert(collections).values(**{**s, 'fields': json.dumps(s['fields'])}))
            if clean: conn.execute(insert(t), clean)
    except Exception:
        t.drop(engine)
        raise
    return s

@app.post('/api/collections')
def create():
    p = request.get_json()
    return jsonify(create_collection(p.get('name'), p.get('fields'), [])), 201

@app.post('/api/import/preview')
def import_preview():
    f = request.files.get('file')
    if not f: raise ValueError('Choose a WDB, CSV or TSV file')
    ext = Path(f.filename).suffix.lower()
    if ext not in ('.wdb', '.csv', '.tsv'): raise ValueError('Supported files: .wdb, .csv, .tsv')
    token = uuid.uuid4().hex
    folder = DATA / token
    folder.mkdir(mode=0o700)
    original = folder / ('original'+ext)
    f.save(original)
    warnings = []
    if ext == '.wdb':
        output = folder / 'converted.csv'
        try:
            run = subprocess.run(['wks2csv', '-D', '%Y-%m-%d', '-o', str(output), str(original)], capture_output=True, timeout=45)
        except FileNotFoundError: raise ValueError('WDB converter is not installed. Use the Docker image or export CSV from Works.')
        except subprocess.TimeoutExpired: raise ValueError('Conversion timed out. Try a CSV export from Works.')
        if run.returncode != 0 or not output.exists() or not output.stat().st_size:
            raise ValueError('This Works file could not be converted. Export CSV from Microsoft Works and import that instead.')
        if output.stat().st_size > 40*1024*1024: raise ValueError('Converted data exceeds the 40 MB limit')
        raw = output.read_bytes()
        warnings.append('Works filters, forms, formulas and report layouts are not imported. Verify every field and record count against the original.')
        if run.stderr.strip(): warnings.append('The converter issued warnings. Check the original carefully; conversion may be incomplete.')
    else: raw = original.read_bytes()
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252'); warnings.append('Read using Windows-1252 encoding. Verify accented characters.')
    delimiter = '\t' if ext == '.tsv' else ','
    try:
        if ext == '.csv': delimiter = csv.Sniffer().sniff(text[:8192], delimiters=',;\t').delimiter
    except csv.Error: pass
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [r for r in rows if any(v != '' for v in r)]
    if len(rows) < 2: raise ValueError('The file needs a header and at least one record. Export column headings from Works.')
    width = len(rows[0])
    if not 1 <= width <= 80 or len(rows) > 100001: raise ValueError('Import limit: 80 fields and 100,000 records')
    if any(len(r) != width for r in rows): raise ValueError('Rows have different field counts. Fix the CSV before importing.')
    labels = [v.strip() or f'Field {i+1}' for i,v in enumerate(rows[0])]
    fields = [dict(label=label, type='text') for label in labels]
    # Default to text to retain leading zeroes, original dates and identifiers.
    snapshot = dict(rows=rows[1:], filename=Path(f.filename).name, sha256=hashlib.sha256(original.read_bytes()).hexdigest())
    (folder/'preview.json').write_text(json.dumps(snapshot), encoding='utf-8')
    return jsonify(token=token, fields=fields, sample=rows[1:6], count=len(rows)-1, warnings=warnings)

@app.post('/api/import/commit')
def import_commit():
    p = request.get_json(); token = p.get('token','')
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token): abort(400)
    path = DATA/token/'preview.json'
    if not path.exists(): abort(404, 'Import preview not found')
    snapshot = json.loads(path.read_text())
    if len(p['fields']) != len(snapshot['rows'][0]): raise ValueError('Field count changed; preview the file again')
    s = create_collection(p['name'], p['fields'], snapshot['rows'], json.dumps({k:snapshot[k] for k in ('filename','sha256')}))
    return jsonify(s), 201

@app.get('/api/collections/<cid>/records')
def records(cid):
    s = spec(cid); rows = filtered_rows(s, request.args)
    page = max(1, int(request.args.get('page', 1))); size=100
    return jsonify(rows=rows[(page-1)*size:page*size], total=len(rows), page=page)

@app.post('/api/collections/<cid>/records')
def add_record(cid):
    s=spec(cid); t=table_for(s)
    with engine.begin() as conn:
        r=conn.execute(insert(t).values(**values(request.get_json(), s)))
        rid=r.inserted_primary_key[0]
    return jsonify(id=rid),201

@app.put('/api/collections/<cid>/records/<int:rid>')
def edit_record(cid,rid):
    s=spec(cid); t=table_for(s); p=request.get_json()
    with engine.begin() as conn:
        r=conn.execute(update(t).where(t.c._id==rid,t.c._rev==int(p.get('_rev',0))).values(**values(p,s), _rev=t.c._rev+1))
        if not r.rowcount: abort(409,'This record changed or was deleted. Reload before editing.')
    return jsonify(ok=True)

@app.delete('/api/collections/<cid>/records/<int:rid>')
def remove_record(cid,rid):
    t=table_for(spec(cid)); rev=int(request.args.get('revision',0))
    with engine.begin() as conn:
        r=conn.execute(delete(t).where(t.c._id==rid,t.c._rev==rev))
        if not r.rowcount: abort(409,'This record changed or was deleted. Reload before deleting.')
    return jsonify(ok=True)

@app.get('/api/collections/<cid>/export.csv')
def export_csv(cid):
    s=spec(cid); rows=filtered_rows(s,request.args); out=io.StringIO(); w=csv.writer(out)
    # Avoid spreadsheet execution when a CSV is opened in Excel/Calc.
    def safe(v):
        if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')): return "'"+v
        return v
    w.writerow([f['label'] for f in s['fields']])
    for r in rows: w.writerow([safe(r.get(f['key'],'')) for f in s['fields']])
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="records.csv"'})

@app.get('/api/collections/<cid>/reports')
def list_reports(cid):
    spec(cid)
    with engine.connect() as conn:
        return jsonify([{**dict(r),'config':json.loads(r['config'])} for r in conn.execute(select(reports).where(reports.c.collection_id==cid)).mappings()])

@app.post('/api/collections/<cid>/reports')
def save_report(cid):
    s=spec(cid); p=request.get_json(); name=str(p.get('name','')).strip()
    if not 1<=len(name)<=120: raise ValueError('Report name must be 1–120 characters')
    config=p.get('config',{}); keys={f['key'] for f in s['fields']}
    if not config.get('columns') or any(k not in keys for k in config['columns']): raise ValueError('Choose report columns')
    for k in ('group','sum'):
        if config.get(k) and config[k] not in keys: raise ValueError('Unknown report field')
    if config.get('sum') and next(f for f in s['fields'] if f['key']==config['sum'])['type'] not in ('number','currency'): raise ValueError('Totals require a numeric field')
    filtered_rows(s,config)
    rid=uuid.uuid4().hex
    with engine.begin() as conn: conn.execute(insert(reports).values(id=rid,collection_id=cid,name=name,config=json.dumps(config)))
    return jsonify(id=rid),201

@app.get('/report/<rid>')
def show_report(rid):
    with engine.connect() as conn: r=conn.execute(select(reports).where(reports.c.id==rid)).mappings().first()
    if not r: abort(404)
    s=spec(r['collection_id']); config=json.loads(r['config']); rows=filtered_rows(s,config)
    fields=[next(f for f in s['fields'] if f['key']==k) for k in config['columns']]
    grouped={}
    for row in rows: grouped.setdefault(str(row.get(config.get('group')) or 'All records'),[]).append(row)
    sumkey=config.get('sum')
    groups=[dict(name=k,rows=v,total=str(sum((Decimal(str(x.get(sumkey) or 0)) for x in v),Decimal(0))) if sumkey else None) for k,v in grouped.items()]
    total=str(sum((Decimal(str(x.get(sumkey) or 0)) for x in rows),Decimal(0))) if sumkey else None
    return render_template('report.html',title=r['name'],database=s['name'],fields=fields,groups=groups,total=total,count=len(rows),config=config,today=date.today().isoformat())

if __name__=='__main__':
    init_db()
    app.run(host='0.0.0.0',port=8080)
