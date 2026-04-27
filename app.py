from flask import Flask, jsonify, request, Response, session, redirect
import pandas as pd
import boto3
from botocore.config import Config
from io import StringIO, BytesIO
import os
import json
import re
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mx-efile-tracker-secret-2026')

S3_BUCKET = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
S3_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

HARDCODED_ADMINS = ['alemaga', 'soemilio', 'gregonz']
DATASETS = {
    'action-plan': 'Action Plan',
    'scenarios': 'Scenarios',
    'business-requirements': 'Business Requirements',
    'doc-checklist': 'Doc Checklist',
    'stakeholder-matrix': 'Stakeholder Matrix',
    'risk-penalties': 'Risk and Penalties',
    'operational-volume': 'Operational Volume'
}
}

TEAMS = ['GTS', 'AP/FinOps', 'Supply Chain', 'InTech', 'Legal', 'HR/Payroll', 'Accounting', 'Retail', 'GREF', 'Customs Broker']
PHASES = ['Short-Term', 'Mid-Term', 'Long-Term', 'Ongoing']
WORKSTREAMS = ['Document Discovery', 'System Integration', 'Process Design', 'Training & Change', 'Compliance & Audit', 'Vendor Management', 'Technology', 'Operations']
STATUSES = ['Planned', 'In Progress', 'Active', 'Complete', 'On Hold', 'Finished']
RAG_STATUSES = ['Green', 'Amber', 'Red']
PRIORITIES = ['P0', 'P1', 'P2']

def get_s3_client():
    return boto3.client('s3', region_name=S3_REGION, config=Config(connect_timeout=5, read_timeout=10))

def load_registered_editors():
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key='config/editors.json')
        return json.loads(response['Body'].read().decode('utf-8')).get('editors', [])
    except:
        return []

def save_registered_editors(editors):
    try:
        s3 = get_s3_client()
        s3.put_object(Bucket=S3_BUCKET, Key='config/editors.json', 
                      Body=json.dumps({"editors": editors}), ContentType='application/json')
        return True
    except:
        return False

def load_from_s3(folder):
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key=f"{folder}/data.csv")
        df = pd.read_csv(StringIO(response['Body'].read().decode('utf-8')))
        df = df.fillna('')
        for col in df.columns:
            df[col] = df[col].astype(str).replace('nan', '')
        return df
    except Exception as e:
        return str(e)

def save_to_s3(folder, df):
    try:
        s3 = get_s3_client()
        buf = StringIO()
        df.to_csv(buf, index=False)
        s3.put_object(Bucket=S3_BUCKET, Key=f"{folder}/data.csv", Body=buf.getvalue(), ContentType='text/csv')
        return True
    except Exception as e:
        return str(e)

def is_admin():
    return session.get('user', '').lower() in [a.lower() for a in HARDCODED_ADMINS]

def is_editor():
    user = session.get('user', '').lower()
    if not user:
        return False
    if user in [a.lower() for a in HARDCODED_ADMINS]:
        return True
    return user in [e.lower() for e in load_registered_editors()]

def login_required_editor(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_editor():
            return jsonify({'success': False, 'error': 'Login required', 'needsLogin': True}), 401
        return f(*args, **kwargs)
    return decorated

def login_required_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin():
            return jsonify({'success': False, 'error': 'Admin required', 'needsLogin': True}), 401
        return f(*args, **kwargs)
    return decorated

def esc(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def parse_date(d):
    if not d or d == 'nan':
        return ''
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', str(d))
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    if re.match(r'^\d{4}-\d{2}-\d{2}$', str(d)):
        return str(d)
    return ''

def make_options(options, selected_value):
    html = ''
    for opt in options:
        sel = ' selected' if selected_value == opt else ''
        html += f'<option value="{esc(opt)}"{sel}>{esc(opt)}</option>'
    return html

def get_unique_values(rows, column):
    values = set()
    for row in rows:
        val = str(row.get(column, '') or '').strip()
        if val:
            values.add(val)
    return sorted(values)

def render_page(dataset):
    user = session.get('user')
    is_adm = is_admin()
    is_edt = is_editor()
    
    result = load_from_s3(dataset)
    if isinstance(result, str):
        rows, columns, error = [], [], result
    else:
        rows, columns, error = result.to_dict('records'), result.columns.tolist(), None
    
    stats = None
    if dataset == 'action-plan' and not error and 'Status' in columns:
        df = result
        stats = {'total': len(df), 'active': len(df[df['Status']=='Active']), 
                 'progress': len(df[df['Status']=='In Progress']), 'planned': len(df[df['Status']=='Planned']),
                 'finished': len(df[df['Status']=='Finished'])}
    
    nav_html = ''
    for k, v in DATASETS.items():
        active = 'active' if k == dataset else ''
        nav_html += f'<a href="/{k}" class="{active}">{v}</a>'
    
    stats_html = ''
    if stats:
        stats_html = f'''<div class="stats">
            <div class="stat"><div class="stat-num">{stats['total']}</div><div>Total</div></div>
            <div class="stat"><div class="stat-num">{stats['active']}</div><div>Active</div></div>
            <div class="stat"><div class="stat-num">{stats['progress']}</div><div>In Progress</div></div>
            <div class="stat"><div class="stat-num">{stats['finished']}</div><div>Finished</div></div>
        </div>'''
    
    if user:
        role = '<span class="role admin">Admin</span>' if is_adm else '<span class="role editor">Editor</span>' if is_edt else ''
        user_html = f'<span class="user-info">👤 {esc(user)} {role}</span> <a href="/logout" class="btn">Logout</a>'
    else:
        user_html = '<button class="btn" onclick="showLogin()">Login</button>'
    
    btns = f'<a href="/export/{dataset}/csv" class="btn gray">📥 Export</a>'
    if is_adm:
        btns += ' <button class="btn green" onclick="showAdd()">+ Add New</button>'
    
    notice = ''
    if not user:
        notice = '<div class="notice yellow">🔒 View Only - <a href="#" onclick="showLogin();return false">Login</a> or <a href="#" onclick="showSignup();return false">Sign up</a> to edit.</div>'
    elif is_edt and not is_adm:
        notice = '<div class="notice blue">✏️ Editor Mode - Edit using dropdowns or Edit button.</div>'
    
    col_unique_values = {}
    for c in columns:
        col_unique_values[c] = get_unique_values(rows, c)
    
    if error:
        table = f'<div class="error">{esc(error)}</div>'
    else:
        table = '<table id="dataTable"><thead><tr>'
        if is_edt:
            table += '<th>Actions</th>'
        for c in columns:
            table += f'<th>{esc(c)}</th>'
        table += '</tr>'
        
        table += '<tr class="filter-row">'
        if is_edt:
            table += '<td></td>'
        for idx, c in enumerate(columns):
            unique_vals = col_unique_values[c]
            if len(unique_vals) <= 20 and len(unique_vals) > 0:
                opts = '<option value="">All</option>'
                for v in unique_vals:
                    opts += f'<option value="{esc(v)}">{esc(v)}</option>'
                table += f'<td><select class="filter-input" data-col="{idx}" onchange="applyFilters()">{opts}</select></td>'
            else:
                table += f'<td><input type="text" class="filter-input" data-col="{idx}" placeholder="Filter..." onkeyup="applyFilters()"></td>'
        table += '</tr></thead><tbody>'
        
        for i, row in enumerate(rows):
            table += f'<tr data-row="{i}">'
            if is_edt:
                table += f'<td><button class="btn small" onclick="showEdit({i})">Edit</button>'
                if is_adm:
                    table += f' <button class="btn small red" onclick="doDelete({i})">✕</button>'
                table += '</td>'
            
            for c in columns:
                val = str(row.get(c, '') or '')
                
                # Inline editing for Action Plan
                if dataset == 'action-plan' and c == 'Deadline' and is_edt:
                    table += f'<td><input type="text" class="inline" style="width:80px" value="{esc(val)}" onchange="inlineUpd({i},\'Deadline\',this.value)"></td>'
                elif dataset == 'action-plan' and c == 'Status' and is_edt:
                    opts = make_options(STATUSES, val)
                    table += f'<td><select class="inline" onchange="inlineUpd({i},\'Status\',this.value)">{opts}</select></td>'
                elif dataset == 'action-plan' and c == 'RAG Status' and is_edt:
                    opts = make_options(RAG_STATUSES, val)
                    table += f'<td><select class="inline" onchange="inlineUpd({i},\'RAG Status\',this.value)">{opts}</select></td>'
                elif dataset == 'action-plan' and c == 'Priority' and is_edt:
                    opts = make_options(PRIORITIES, val)
                    table += f'<td><select class="inline" onchange="inlineUpd({i},\'Priority\',this.value)">{opts}</select></td>'
                # Badge styling
                elif c == 'Status':
                    cls = val.lower().replace(' ', '')
                    table += f'<td><span class="badge {cls}">{esc(val)}</span></td>'
                elif c == 'RAG Status':
                    table += f'<td><span class="badge rag-{val.lower()}">{esc(val)}</span></td>'
                elif c == 'Priority':
                    table += f'<td><span class="badge {val.lower()}">{esc(val)}</span></td>'
                # Phonetool links for alias columns
                elif c in ['Owner', 'Stakeholder', 'Alias', 'POC', 'Escalation'] and val:
                    # Handle multiple aliases separated by comma
                    aliases = [a.strip().replace('@', '') for a in val.split(',')]
                    links = ', '.join([f'<a href="https://phonetool.amazon.com/users/{esc(a)}" target="_blank" class="link">{esc(a)}</a>' for a in aliases if a])
                    table += f'<td>{links}</td>'
                else:
                    table += f'<td>{esc(val)}</td>'
            table += '</tr>'
        table += '</tbody></table>'
        table += '<div class="filter-info"><span id="filterCount"></span> <button class="btn small" onclick="clearFilters()" style="margin-left:10px">Clear Filters</button></div>'
    
    rows_js = json.dumps(rows).replace('</script>', '<\\/script>')
    cols_js = json.dumps(columns)
    col_offset_js = '1' if is_edt else '0'
    
    html = '''<!DOCTYPE html>
<html>
<head>
<title>MX Customs E-File Tracker</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,sans-serif;margin:0;padding:20px;background:#f5f5f5}
.header{background:#003366;color:#fff;padding:20px;margin:-20px -20px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.header h1{margin:0;font-size:22px}
.header p{margin:5px 0 0;opacity:.8;font-size:13px}
.nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.nav a{padding:10px 18px;background:#003366;color:#fff;text-decoration:none;border-radius:5px;font-size:14px}
.nav a:hover,.nav a.active{background:#0070c0}
.card{background:#fff;padding:20px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,.1);margin-bottom:20px}
.card-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;flex-wrap:wrap;gap:10px}
.card-hdr h2{margin:0}
.stats{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}
.stat{background:#fff;padding:15px 25px;border-radius:8px;text-align:center;box-shadow:0 2px 4px rgba(0,0,0,.1)}
.stat-num{font-size:28px;font-weight:700;color:#003366}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#003366;color:#fff;padding:8px 5px;text-align:left;white-space:nowrap}
td{padding:6px 5px;border-bottom:1px solid #eee;vertical-align:middle}
tr:hover{background:#f0f7ff}
tr.filter-row{background:#f8f9fa}
tr.filter-row:hover{background:#f8f9fa}
tr.filter-row td{padding:4px 3px;border-bottom:2px solid #003366}
.filter-input{width:100%;padding:4px;border:1px solid #ccc;border-radius:4px;font-size:11px}
.filter-input:focus{border-color:#0070c0;outline:none}
.filter-info{margin-top:10px;font-size:13px;color:#666}
.btn{background:#0070c0;color:#fff;border:none;padding:8px 14px;border-radius:5px;cursor:pointer;text-decoration:none;font-size:13px;display:inline-block}
.btn:hover{background:#005a9e}
.btn.gray{background:#6c757d}.btn.gray:hover{background:#5a6268}
.btn.green{background:#28a745}.btn.green:hover{background:#218838}
.btn.red{background:#dc3545}.btn.red:hover{background:#c82333}
.btn.small{padding:4px 8px;font-size:11px}
.inline{padding:4px;border:1px solid #ddd;border-radius:4px;font-size:11px}
.badge{padding:2px 6px;border-radius:3px;font-size:11px}
.badge.active,.badge.rag-green,.badge.p2{background:#90EE90}
.badge.inprogress,.badge.rag-amber,.badge.p1{background:#FFD700}
.badge.planned{background:#E0E0E0}
.badge.complete,.badge.finished{background:#4CAF50;color:#fff}
.badge.onhold{background:#999;color:#fff}
.badge.rag-red,.badge.p0{background:#FF6B6B;color:#fff}
.link{color:#0070c0;text-decoration:none}.link:hover{text-decoration:underline}
.notice{padding:10px 15px;border-radius:6px;margin-bottom:15px;font-size:14px}
.notice.yellow{background:#fff3cd;color:#856404}
.notice.blue{background:#d1ecf1;color:#0c5460}
.error{background:#fee;padding:20px;border-radius:8px;color:#c00}
.user-info{color:#fff;font-size:14px}
.role{padding:2px 8px;border-radius:3px;font-size:11px;margin-left:5px}
.role.admin{background:#28a745}
.role.editor{background:#ffc107;color:#333}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center}
.modal.show{display:flex}
.modal-box{background:#fff;padding:30px;border-radius:12px;width:90%;max-width:600px;max-height:90vh;overflow-y:auto}
.modal-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.modal-hdr h2{margin:0;color:#003366}
.close{background:none;border:none;font-size:24px;cursor:pointer;color:#666}
.form-group{margin-bottom:15px}
.form-group label{display:block;margin-bottom:5px;font-weight:600}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:10px;border:1px solid #ddd;border-radius:6px;font-size:14px}
.form-group textarea{min-height:60px;resize:vertical}
.msg{padding:10px;border-radius:6px;margin-bottom:15px;display:none}
.msg.ok{background:#d4edda;color:#155724}
.msg.err{background:#f8d7da;color:#721c24}
.hidden{display:none}
</style>
</head>
<body>
<div class="header">
<div><h1>🇲🇽 MX Customs E-File Compliance Tracker</h1><p>GTS LATAM | Article 59 MX Customs Law</p></div>
<div>%%USER_HTML%%</div>
</div>
<div class="nav">%%NAV_HTML%%</div>
%%STATS_HTML%%
<div class="card">
<div class="card-hdr"><h2>%%TITLE%%</h2><div>%%BTNS%%</div></div>
%%NOTICE%%
<div style="overflow-x:auto">%%TABLE%%</div>
</div>

<div id="loginModal" class="modal">
<div class="modal-box" style="max-width:400px">
<div class="modal-hdr"><h2>Login</h2><button class="close" onclick="hideModal('loginModal')">&times;</button></div>
<div id="loginErr" class="msg err"></div>
<form onsubmit="doLogin(event)">
<div class="form-group"><label>Amazon Alias</label><input type="text" id="loginAlias" required></div>
<button type="submit" class="btn" style="width:100%">Login</button>
</form>
<p style="text-align:center;margin-top:15px">New? <a href="#" onclick="hideModal('loginModal');showSignup();return false">Sign up</a></p>
</div>
</div>

<div id="signupModal" class="modal">
<div class="modal-box" style="max-width:400px">
<div class="modal-hdr"><h2>Sign Up</h2><button class="close" onclick="hideModal('signupModal')">&times;</button></div>
<div id="signupOk" class="msg ok"></div>
<div id="signupErr" class="msg err"></div>
<form id="signupForm" onsubmit="doSignup(event)">
<div class="form-group"><label>Amazon Alias</label><input type="text" id="signupAlias" required></div>
<p style="font-size:12px;color:#666">Editors can edit items. Admins can add/delete.</p>
<button type="submit" class="btn" style="width:100%">Register</button>
</form>
<p style="text-align:center;margin-top:15px">Have account? <a href="#" onclick="hideModal('signupModal');showLogin();return false">Login</a></p>
</div>
</div>

<div id="editModal" class="modal">
<div class="modal-box">
<div class="modal-hdr"><h2 id="editTitle">Edit</h2><button class="close" onclick="hideModal('editModal')">&times;</button></div>
<div id="editOk" class="msg ok">Saved!</div>
<div id="editErr" class="msg err"></div>
<form onsubmit="doSave(event)">
<div id="editFields"></div>
<button type="submit" class="btn" style="width:100%">Save</button>
</form>
</div>
</div>

<script>
var DATA={rows:%%ROWS_JS%%,cols:%%COLS_JS%%,ds:"%%DATASET%%",teams:%%TEAMS_JS%%,phases:%%PHASES_JS%%,ws:%%WS_JS%%,st:%%ST_JS%%,rag:%%RAG_JS%%,priorities:%%PRIORITIES_JS%%};
var editIdx=-1,isNew=false;
var colOffset=%%COL_OFFSET%%;

function showLogin(){document.getElementById('loginModal').classList.add('show');document.getElementById('loginErr').style.display='none';}
function showSignup(){document.getElementById('signupModal').classList.add('show');document.getElementById('signupErr').style.display='none';document.getElementById('signupOk').style.display='none';document.getElementById('signupForm').style.display='block';}
function hideModal(id){document.getElementById(id).classList.remove('show');}

function applyFilters(){
    var table=document.getElementById('dataTable');
    if(!table)return;
    var filters=document.querySelectorAll('.filter-input');
    var filterVals=[];
    filters.forEach(function(f){filterVals.push(f.value.toLowerCase());});
    
    var rows=table.querySelectorAll('tbody tr');
    var visibleCount=0;
    var totalCount=rows.length;
    
    rows.forEach(function(row){
        var cells=row.querySelectorAll('td');
        var show=true;
        filterVals.forEach(function(fv,idx){
            if(fv){
                var cellIdx=idx+colOffset;
                if(cells[cellIdx]){
                    var cellText=cells[cellIdx].textContent.toLowerCase();
                    if(cellText.indexOf(fv)===-1)show=false;
                }
            }
        });
        if(show){row.classList.remove('hidden');visibleCount++;}
        else{row.classList.add('hidden');}
    });
    
    document.getElementById('filterCount').textContent='Showing '+visibleCount+' of '+totalCount+' items';
}

function clearFilters(){
    document.querySelectorAll('.filter-input').forEach(function(f){
        if(f.tagName==='SELECT')f.selectedIndex=0;
        else f.value='';
    });
    document.querySelectorAll('#dataTable tbody tr').forEach(function(r){r.classList.remove('hidden');});
    document.getElementById('filterCount').textContent='';
}

function doLogin(e){
e.preventDefault();
var alias=document.getElementById('loginAlias').value.trim().toLowerCase();
fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alias:alias})})
.then(function(r){return r.json();}).then(function(d){if(d.success)location.reload();else{document.getElementById('loginErr').textContent=d.error||'Failed';document.getElementById('loginErr').style.display='block';}});
}

function doSignup(e){
e.preventDefault();
var alias=document.getElementById('signupAlias').value.trim().toLowerCase();
fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alias:alias})})
.then(function(r){return r.json();}).then(function(d){if(d.success){document.getElementById('signupOk').innerHTML='✓ Welcome '+alias+'!';document.getElementById('signupOk').style.display='block';document.getElementById('signupForm').style.display='none';setTimeout(function(){location.reload();},1500);}else{document.getElementById('signupErr').textContent=d.error||'Failed';document.getElementById('signupErr').style.display='block';}});
}

function inlineUpd(idx,col,val){
fetch('/api/inline-update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:DATA.ds,rowIndex:idx,column:col,value:val})})
.then(function(r){return r.json();}).then(function(d){if(!d.success){alert(d.error||'Error');location.reload();}});
}

function showAdd(){
isNew=true;editIdx=-1;
document.getElementById('editTitle').textContent='Add New';
buildForm(null);
document.getElementById('editOk').style.display='none';
document.getElementById('editErr').style.display='none';
document.getElementById('editModal').classList.add('show');
}

function showEdit(idx){
isNew=false;editIdx=idx;
document.getElementById('editTitle').textContent='Edit Item';
buildForm(DATA.rows[idx]);
document.getElementById('editOk').style.display='none';
document.getElementById('editErr').style.display='none';
document.getElementById('editModal').classList.add('show');
}

function getFields(){
if(DATA.ds==='action-plan')return[
{n:'Action ID',t:'text',r:1},
{n:'Phase',t:'sel',o:DATA.phases},
{n:'Workstream',t:'sel',o:DATA.ws},
{n:'Priority',t:'sel',o:DATA.priorities},
{n:'Action Item',t:'area',r:1},
{n:'Team',t:'sel',o:[''].concat(DATA.teams)},
{n:'Owner',t:'text'},
{n:'Escalation',t:'text'},
{n:'Dependencies',t:'text'},
{n:'Deadline',t:'text'},
{n:'Status',t:'sel',o:DATA.st},
{n:'Notes',t:'area'},
{n:'RAG Status',t:'sel',o:DATA.rag},
{n:'Reason for R/A/G',t:'area'},
{n:'Path to Green',t:'area'}];
if(DATA.ds==='stakeholder-matrix')return[
{n:'Team',t:'sel',o:[''].concat(DATA.teams)},
{n:'Stakeholder',t:'text'},
{n:'Role',t:'text'},
{n:'Involvement',t:'sel',o:['High','Medium','Low']},
{n:'Communication',t:'sel',o:['Email','Chime','Meetings','Slack']},
{n:'Responsibilities',t:'area'},
{n:'Notes',t:'area'}];
return DATA.cols.map(function(c){return {n:c,t:'text'};});
}

function parseD(d){if(!d||d==='nan')return'';var m=d.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);if(m)return m[3]+'-'+m[1].padStart(2,'0')+'-'+m[2].padStart(2,'0');return/^\d{4}-\d{2}-\d{2}$/.test(d)?d:'';}

function makeOpts(opts,val){
var html='';
for(var i=0;i<opts.length;i++){
var sel=(opts[i]===val)?' selected':'';
html+='<option value="'+opts[i]+'"'+sel+'>'+opts[i]+'</option>';
}
return html;
}

function buildForm(row){
var fields=getFields(),html='';
var autoId='';
if(isNew&&DATA.ds==='action-plan'){var mx=0;DATA.rows.forEach(function(r){var m=(r['Action ID']||'').match(/AP-(\d+)/);if(m)mx=Math.max(mx,parseInt(m[1]));}); autoId='AP-'+String(mx+1).padStart(3,'0');}
fields.forEach(function(f,i){
var v=row?(row[f.n]||''):'';
if(isNew&&f.n==='Action ID'&&autoId)v=autoId;
var id='f'+i;
html+='<div class="form-group"><label>'+f.n+(f.r?' *':'')+'</label>';
if(f.t==='sel'){html+='<select id="'+id+'">'+makeOpts(f.o,v)+'</select>';}
else if(f.t==='area')html+='<textarea id="'+id+'">'+v.replace(/</g,'&lt;')+'</textarea>';
else if(f.t==='date')html+='<input type="date" id="'+id+'" value="'+parseD(v)+'">';
else html+='<input type="text" id="'+id+'" value="'+v.replace(/"/g,'&quot;')+'"'+(f.r?' required':'')+'>';
html+='</div>';
});
document.getElementById('editFields').innerHTML=html;
}

function doSave(e){
e.preventDefault();
var fields=getFields(),data={dataset:DATA.ds,rowIndex:editIdx,isNew:isNew,fields:{}};
fields.forEach(function(f,i){
var el=document.getElementById('f'+i),v=el?el.value:'';
data.fields[f.n]=v;
});
fetch('/api/update-generic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
.then(function(r){return r.json();}).then(function(d){if(d.success){document.getElementById('editOk').style.display='block';setTimeout(function(){location.reload();},1000);}else{document.getElementById('editErr').textContent=d.error||'Failed';document.getElementById('editErr').style.display='block';}});
}

function doDelete(idx){
var name=DATA.rows[idx]['Action ID']||DATA.rows[idx]['Team']||'Item '+(idx+1);
if(!confirm('Delete "'+name+'"?'))return;
fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:DATA.ds,rowIndex:idx})})
.then(function(r){return r.json();}).then(function(d){if(d.success)location.reload();else alert(d.error||'Error');});
}

document.querySelectorAll('.modal').forEach(function(m){m.addEventListener('click',function(e){if(e.target===m)m.classList.remove('show');});});
</script>
</body>
</html>'''
    
    # Replace placeholders
    html = html.replace('%%USER_HTML%%', user_html)
    html = html.replace('%%NAV_HTML%%', nav_html)
    html = html.replace('%%STATS_HTML%%', stats_html)
    html = html.replace('%%TITLE%%', DATASETS[dataset])
    html = html.replace('%%BTNS%%', btns)
    html = html.replace('%%NOTICE%%', notice)
    html = html.replace('%%TABLE%%', table)
    html = html.replace('%%ROWS_JS%%', rows_js)
    html = html.replace('%%COLS_JS%%', cols_js)
    html = html.replace('%%DATASET%%', dataset)
    html = html.replace('%%TEAMS_JS%%', json.dumps(TEAMS))
    html = html.replace('%%PHASES_JS%%', json.dumps(PHASES))
    html = html.replace('%%WS_JS%%', json.dumps(WORKSTREAMS))
    html = html.replace('%%ST_JS%%', json.dumps(STATUSES))
    html = html.replace('%%RAG_JS%%', json.dumps(RAG_STATUSES))
    html = html.replace('%%PRIORITIES_JS%%', json.dumps(PRIORITIES))
    html = html.replace('%%COL_OFFSET%%', col_offset_js)
    
    return html

@app.route('/')
def home():
    return render_page('action-plan')

@app.route('/<dataset>')
def view_dataset(dataset):
    if dataset not in DATASETS:
        return "Not found", 404
    return render_page(dataset)

@app.route('/api/login', methods=['POST'])
def login():
    alias = request.json.get('alias', '').strip().lower()
    if not alias:
        return jsonify({'success': False, 'error': 'Enter alias'})
    if alias in [a.lower() for a in HARDCODED_ADMINS]:
        session['user'] = alias
        return jsonify({'success': True})
    if alias in [e.lower() for e in load_registered_editors()]:
        session['user'] = alias
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': f'"{alias}" not registered. Sign up first.'})

@app.route('/api/signup', methods=['POST'])
def signup():
    alias = request.json.get('alias', '').strip().lower()
    if not alias:
        return jsonify({'success': False, 'error': 'Enter alias'})
    if alias in [a.lower() for a in HARDCODED_ADMINS]:
        session['user'] = alias
        return jsonify({'success': True})
    editors = load_registered_editors()
    if alias in [e.lower() for e in editors]:
        session['user'] = alias
        return jsonify({'success': True})
    editors.append(alias)
    if save_registered_editors(editors):
        session['user'] = alias
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Save failed'})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/export/<dataset>/csv')
def export_csv(dataset):
    if dataset not in DATASETS:
        return "Not found", 404
    df = load_from_s3(dataset)
    if isinstance(df, str):
        return f"Error: {df}", 500
    out = StringIO()
    df.to_csv(out, index=False)
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=MX_EFile_{dataset}_{datetime.now().strftime("%Y%m%d")}.csv'})

@app.route('/api/inline-update', methods=['POST'])
@login_required_editor
def inline_update():
    data = request.json
    df = load_from_s3(data['dataset'])
    if isinstance(df, str):
        return jsonify({'success': False, 'error': df})
    df.at[data['rowIndex'], data['column']] = data.get('value', '')
    result = save_to_s3(data['dataset'], df)
    return jsonify({'success': result is True, 'error': None if result is True else str(result)})

@app.route('/api/update-generic', methods=['POST'])
@login_required_editor
def update_generic():
    data = request.json
    if data.get('isNew') and not is_admin():
        return jsonify({'success': False, 'error': 'Admin required'})
    df = load_from_s3(data['dataset'])
    if isinstance(df, str):
        return jsonify({'success': False, 'error': df})
    if data.get('isNew'):
        new_row = {c: data['fields'].get(c, '') for c in df.columns}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        for c in df.columns:
            if c in data['fields']:
                df.at[data['rowIndex'], c] = data['fields'][c]
    result = save_to_s3(data['dataset'], df)
    return jsonify({'success': result is True, 'error': None if result is True else str(result)})

@app.route('/api/delete', methods=['POST'])
@login_required_admin
def delete_item():
    data = request.json
    df = load_from_s3(data['dataset'])
    if isinstance(df, str):
        return jsonify({'success': False, 'error': df})
    df = df.drop(index=data['rowIndex']).reset_index(drop=True)
    result = save_to_s3(data['dataset'], df)
    return jsonify({'success': result is True, 'error': None if result is True else str(result)})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
