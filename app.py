from flask import Flask, render_template_string, jsonify, request, Response, session, redirect, url_for
import pandas as pd
import boto3
from botocore.config import Config
from io import StringIO, BytesIO
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mx-efile-tracker-secret-2026')

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
S3_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
SES_SENDER = os.environ.get('SES_SENDER', 'noreply@amazon.com')

# Two-tier permissions:
# ADMINS: Can Add, Edit, Delete across all sections
# EDITORS: Can only Edit existing items across all sections
AUTHORIZED_ADMINS = os.environ.get('AUTHORIZED_ADMINS', 'alemaga').split(',')
AUTHORIZED_EDITORS = os.environ.get('AUTHORIZED_EDITORS', '').split(',')

# Notification recipients
NOTIFICATION_EMAILS = os.environ.get('NOTIFICATION_EMAILS', '').split(',')

DATASETS = {
    'action-plan': 'Action Plan',
    'business-requirements': 'Business Requirements',
    'doc-checklist': 'Doc Checklist',
    'stakeholder-matrix': 'Stakeholder Matrix',
    'risk-penalties': 'Risk and Penalties',
    'operational-volume': 'Operational Volume'
}

TEAMS = ['GTS', 'AP/FinOps', 'Supply Chain', 'InTech', 'Legal', 'HR/Payroll', 'Accounting', 'Retail', 'GREF', 'Customs Broker']
PHASES = ['Short-Term', 'Mid-Term', 'Long-Term', 'Ongoing']
WORKSTREAMS = ['Document Discovery', 'System Integration', 'Process Design', 'Training & Change', 'Compliance & Audit', 'Vendor Management', 'Technology', 'Operations']

def get_s3_client():
    config = Config(connect_timeout=5, read_timeout=10)
    return boto3.client('s3', region_name=S3_REGION, config=config)

def get_ses_client():
    return boto3.client('ses', region_name=S3_REGION)

def load_from_s3(folder):
    try:
        s3 = get_s3_client()
        key = f"{folder}/data.csv"
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        df = pd.read_csv(StringIO(response['Body'].read().decode('utf-8')))
        df = df.fillna('')
        for col in df.columns:
            df[col] = df[col].astype(str).replace('nan', '')
        
        if folder == 'action-plan':
            if 'Target Date' in df.columns and 'ETA' not in df.columns:
                df = df.rename(columns={'Target Date': 'ETA'})
            if 'Team' not in df.columns:
                cols = df.columns.tolist()
                idx = cols.index('Action Item') + 1 if 'Action Item' in cols else 4
                df.insert(idx, 'Team', '')
        return df
    except Exception as e:
        return str(e)

def save_to_s3(folder, df):
    try:
        s3 = get_s3_client()
        key = f"{folder}/data.csv"
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=csv_buffer.getvalue(), ContentType='text/csv')
        return True
    except Exception as e:
        return str(e)

def send_notification(action_id, action_item, old_status, new_status, changed_by):
    if not NOTIFICATION_EMAILS or not NOTIFICATION_EMAILS[0]:
        return
    try:
        ses = get_ses_client()
        subject = f"[MX E-File Tracker] Status Change: {action_id}"
        body = f"""
Action Item Status Changed

Action ID: {action_id}
Action Item: {action_item}
Previous Status: {old_status}
New Status: {new_status}
Changed By: {changed_by}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

View tracker: https://tckiezxcqn.us-east-1.awsapprunner.com/action-plan
"""
        ses.send_email(
            Source=SES_SENDER,
            Destination={'ToAddresses': [e.strip() for e in NOTIFICATION_EMAILS if e.strip()]},
            Message={'Subject': {'Data': subject}, 'Body': {'Text': {'Data': body}}}
        )
    except Exception as e:
        print(f"Failed to send notification: {e}")

def is_admin():
    user = session.get('user', '').lower()
    return user in [a.lower().strip() for a in AUTHORIZED_ADMINS if a.strip()]

def is_editor():
    user = session.get('user', '').lower()
    admins = [a.lower().strip() for a in AUTHORIZED_ADMINS if a.strip()]
    editors = [e.lower().strip() for e in AUTHORIZED_EDITORS if e.strip()]
    return user in admins or user in editors

def can_edit():
    return is_editor()

def can_add_delete():
    return is_admin()

def login_required_editor(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_editor():
            return jsonify({'success': False, 'error': 'Editor access required', 'needsLogin': True}), 401
        return f(*args, **kwargs)
    return decorated_function

def login_required_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            return jsonify({'success': False, 'error': 'Admin access required', 'needsLogin': True}), 401
        return f(*args, **kwargs)
    return decorated_function

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>MX E-File Tracker</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #003366; color: white; padding: 20px; margin: -20px -20px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .header-left h1 { margin: 0; }
        .header-left p { margin: 5px 0 0; opacity: 0.8; }
        .header-right { display: flex; align-items: center; gap: 15px; }
        .user-info { color: white; font-size: 14px; }
        .user-role { background: #0070c0; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 5px; }
        .user-role.admin { background: #28a745; }
        .user-role.editor { background: #ffc107; color: #333; }
        .login-btn, .logout-btn { background: #0070c0; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; text-decoration: none; font-size: 14px; }
        .login-btn:hover, .logout-btn:hover { background: #005a9e; }
        .nav { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .nav a { padding: 10px 20px; background: #003366; color: white; text-decoration: none; border-radius: 5px; }
        .nav a:hover, .nav a.active { background: #0070c0; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
        .card-header h2 { margin: 0; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th { background: #003366; color: white; padding: 8px 5px; text-align: left; position: sticky; top: 0; white-space: nowrap; }
        td { padding: 6px 5px; border-bottom: 1px solid #eee; vertical-align: top; }
        tr:hover { background: #f0f7ff; }
        .error { background: #fee; padding: 20px; border-radius: 8px; color: #c00; }
        .stats { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat { background: white; padding: 15px 25px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-num { font-size: 28px; font-weight: bold; color: #003366; }
        .status-active { background: #90EE90; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-inprogress { background: #FFD700; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-planned { background: #E0E0E0; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-complete { background: #4CAF50; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .rag-green { background: #90EE90; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .rag-amber { background: #FFD700; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .rag-red { background: #FF6B6B; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .priority-p0 { background: #FF6B6B; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 11px; }
        .priority-p1 { background: #FFD700; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .priority-p2 { background: #90EE90; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .edit-btn { background: #0070c0; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
        .edit-btn:hover { background: #005a9e; }
        .add-btn { background: #28a745; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; font-size: 14px; }
        .add-btn:hover { background: #218838; }
        .export-btn { background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; font-size: 14px; text-decoration: none; }
        .export-btn:hover { background: #5a6268; }
        .delete-btn { background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 5px; }
        .delete-btn:hover { background: #c82333; }
        .owner-link { color: #0070c0; text-decoration: none; }
        .owner-link:hover { text-decoration: underline; }
        
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
        .modal.active { display: flex; align-items: center; justify-content: center; }
        .modal-content { background: white; padding: 30px; border-radius: 12px; width: 90%; max-width: 700px; max-height: 90vh; overflow-y: auto; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .modal-header h2 { margin: 0; color: #003366; }
        .close-btn { background: none; border: none; font-size: 24px; cursor: pointer; color: #666; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 600; color: #333; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
        .form-group textarea { min-height: 60px; resize: vertical; }
        .form-row { display: flex; gap: 15px; }
        .form-row .form-group { flex: 1; }
        .save-btn { background: #003366; color: white; border: none; padding: 12px 30px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; margin-top: 10px; }
        .save-btn:hover { background: #004488; }
        .save-btn:disabled { background: #ccc; cursor: not-allowed; }
        .success-msg { background: #d4edda; color: #155724; padding: 10px; border-radius: 6px; margin-bottom: 15px; display: none; }
        .error-msg { background: #f8d7da; color: #721c24; padding: 10px; border-radius: 6px; margin-bottom: 15px; display: none; }
        .readonly { background: #f5f5f5; }
        .alias-wrapper { position: relative; }
        .alias-input { padding-right: 80px !important; }
        .lookup-btn { position: absolute; right: 5px; top: 50%; transform: translateY(-50%); background: #0070c0; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .lookup-btn:hover { background: #005a9e; }
        .read-only-notice { background: #fff3cd; color: #856404; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
        .editor-notice { background: #d1ecf1; color: #0c5460; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>🇲🇽 MX E-File Compliance Tracker</h1>
            <p>GTS LATAM | Article 59 MX Customs Law</p>
        </div>
        <div class="header-right">
            {% if user %}
            <span class="user-info">
                👤 {{ user }}
                {% if user_is_admin %}
                <span class="user-role admin">Admin</span>
                {% elif user_is_editor %}
                <span class="user-role editor">Editor</span>
                {% endif %}
            </span>
            <a href="/logout" class="logout-btn">Logout</a>
            {% else %}
            <button class="login-btn" onclick="openLoginModal()">Login</button>
            {% endif %}
        </div>
    </div>
    
    <div class="nav">
        {% for key, name in datasets.items() %}
        <a href="/{{ key }}" class="{{ 'active' if active == key }}">{{ name }}</a>
        {% endfor %}
    </div>
    
    {% if stats %}
    <div class="stats">
        <div class="stat"><div class="stat-num">{{ stats.total }}</div><div>Total</div></div>
        <div class="stat"><div class="stat-num">{{ stats.active }}</div><div>Active</div></div>
        <div class="stat"><div class="stat-num">{{ stats.progress }}</div><div>In Progress</div></div>
        <div class="stat"><div class="stat-num">{{ stats.planned }}</div><div>Planned</div></div>
    </div>
    {% endif %}
    
    <div class="card">
        <div class="card-header">
            <h2>{{ title }}</h2>
            <div class="btn-group">
                <a href="/export/{{ active }}/excel" class="export-btn">📥 Excel</a>
                <a href="/export/{{ active }}/csv" class="export-btn">📥 CSV</a>
                {% if user_is_admin %}
                <button class="add-btn" onclick="openAddModal()">+ Add New</button>
                {% endif %}
            </div>
        </div>
        
        {% if not user %}
        <div class="read-only-notice">
            🔒 <strong>View Only</strong> - <a href="#" onclick="openLoginModal(); return false;">Login</a> to edit items.
        </div>
        {% elif user_is_editor and not user_is_admin %}
        <div class="editor-notice">
            ✏️ <strong>Editor Mode</strong> - You can edit existing items. Contact an admin to add or delete items.
        </div>
        {% endif %}
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% else %}
        <div style="overflow-x:auto;">
        <table>
            <thead>
                <tr>
                    {% if user_is_editor %}<th>Actions</th>{% endif %}
                    {% for c in columns %}<th>{{ c }}</th>{% endfor %}
                </tr>
            </thead>
            <tbody>
            {% for row in rows %}
                <tr>
                    {% if user_is_editor %}
                    <td>
                        <button class="edit-btn" onclick="openEditModal({{ loop.index0 }})">Edit</button>
                        {% if user_is_admin %}
                        <button class="delete-btn" onclick="confirmDelete({{ loop.index0 }})">✕</button>
                        {% endif %}
                    </td>
                    {% endif %}
                    {% for c in columns %}
                    <td>
                        {% if c == 'Status' %}
                            <span class="status-{{ (row[c] or '')|lower|replace(' ', '') }}">{{ row[c] or '' }}</span>
                        {% elif c == 'RAG Status' %}
                            <span class="rag-{{ (row[c] or '')|lower }}">{{ row[c] or '' }}</span>
                        {% elif c == 'Priority' %}
                            <span class="priority-{{ (row[c] or '')|lower }}">{{ row[c] or '' }}</span>
                        {% elif (c == 'Owner' or c == 'POC' or c == 'Alias') and row[c] %}
                            <a href="https://phonetool.amazon.com/users/{{ row[c] }}" target="_blank" class="owner-link">{{ row[c] }}</a>
                        {% else %}
                            {{ row[c] or '' }}
                        {% endif %}
                    </td>
                    {% endfor %}
                </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>
        {% endif %}
    </div>
    
    <!-- Login Modal -->
    <div id="loginModal" class="modal">
        <div class="modal-content" style="max-width: 400px;">
            <div class="modal-header">
                <h2>Login</h2>
                <button class="close-btn" onclick="closeModal('loginModal')">&times;</button>
            </div>
            <div id="loginErrorMsg" class="error-msg"></div>
            <form id="loginForm">
                <div class="form-group">
                    <label>Amazon Alias</label>
                    <input type="text" id="loginAlias" name="alias" placeholder="Enter your Amazon alias" required>
                </div>
                <p style="font-size: 12px; color: #666;">
                    <strong>Admins</strong> (Add/Edit/Delete): {{ authorized_admins }}<br>
                    <strong>Editors</strong> (Edit only): {{ authorized_editors or 'None configured' }}
                </p>
                <button type="submit" class="save-btn">Login</button>
            </form>
        </div>
    </div>
    
    <!-- Generic Edit Modal -->
    <div id="editModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modalTitle">Edit Item</h2>
                <button class="close-btn" onclick="closeModal('editModal')">&times;</button>
            </div>
            <div id="successMsg" class="success-msg">Changes saved successfully!</div>
            <div id="errorMsg" class="error-msg"></div>
            <form id="editForm">
                <input type="hidden" id="rowIndex" name="rowIndex" value="-1">
                <input type="hidden" id="dataset" name="dataset" value="{{ active }}">
                <input type="hidden" id="isNew" name="isNew" value="false">
                <div id="formFields"></div>
                <button type="submit" class="save-btn" id="saveBtn">Save Changes</button>
            </form>
        </div>
    </div>
    
    <p style="color: #999; text-align: center; margin-top: 30px;">
        MX E-File Compliance Tracker | GTS LATAM | <a href="/health">Health</a>
    </p>
    
    <script>
        const rowData = {{ rows | tojson | safe }};
        const columns = {{ columns | tojson | safe }};
        const currentDataset = "{{ active }}";
        const userIsEditor = {{ 'true' if user_is_editor else 'false' }};
        const userIsAdmin = {{ 'true' if user_is_admin else 'false' }};
        
        const teams = {{ teams | tojson | safe }};
        const phases = {{ phases | tojson | safe }};
        const workstreams = {{ workstreams | tojson | safe }};
        
        // Field configurations per dataset
        const datasetFields = {
            'action-plan': [
                {name: 'Action ID', type: 'text', required: true},
                {name: 'Phase', type: 'select', options: phases},
                {name: 'Workstream', type: 'select', options: workstreams},
                {name: 'Action Item', type: 'textarea', required: true},
                {name: 'Team', type: 'select', options: ['', ...teams]},
                {name: 'Owner', type: 'alias'},
                {name: 'Dependencies', type: 'text'},
                {name: 'ETA', type: 'date'},
                {name: 'Status', type: 'select', options: ['Planned', 'In Progress', 'Active', 'Complete', 'On Hold']},
                {name: 'Priority', type: 'select', options: ['P0', 'P1', 'P2']},
                {name: 'RAG Status', type: 'select', options: ['Green', 'Amber', 'Red']},
                {name: 'Reason for R/A', type: 'textarea'},
                {name: 'Path to Green', type: 'textarea'},
                {name: 'Notes', type: 'textarea'}
            ],
            'stakeholder-matrix': [
                {name: 'Stakeholder', type: 'text', altNames: ['Name']},
                {name: 'Alias', type: 'alias', altNames: ['POC']},
                {name: 'Role', type: 'text', altNames: ['Title']},
                {name: 'Team', type: 'select', options: ['', ...teams], altNames: ['Organization']},
                {name: 'Involvement', type: 'select', options: ['High', 'Medium', 'Low'], altNames: ['Involvement Level']},
                {name: 'Communication', type: 'select', options: ['Email', 'Chime', 'Meetings', 'Slack'], altNames: ['Comm Preference']},
                {name: 'Responsibilities', type: 'textarea'},
                {name: 'Notes', type: 'textarea'}
            ],
            'default': [] // Will auto-generate from columns
        };
        
        function parseDate(dateStr) {
            if (!dateStr || dateStr === 'nan' || dateStr === '') return '';
            const mmddyyyy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/;
            let match = dateStr.match(mmddyyyy);
            if (match) return `${match[3]}-${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}`;
            try { const d = new Date(dateStr); if (!isNaN(d.getTime())) return d.toISOString().split('T')[0]; } catch (e) {}
            return '';
        }
        
        function formatDate(dateStr) {
            if (!dateStr) return '';
            const parts = dateStr.split('-');
            return parts.length === 3 ? `${parts[1]}/${parts[2]}/${parts[0]}` : dateStr;
        }
        
        function lookupAlias(fieldId) {
            const alias = document.getElementById(fieldId).value.trim();
            if (!alias) { alert('Please enter an alias'); return; }
            window.open(`https://phonetool.amazon.com/users/${alias}`, '_blank');
        }
        
        function closeModal(modalId) { document.getElementById(modalId).classList.remove('active'); }
        
        function openLoginModal() {
            document.getElementById('loginErrorMsg').style.display = 'none';
            document.getElementById('loginAlias').value = '';
            document.getElementById('loginModal').classList.add('active');
        }
        
        function getFieldConfig() {
            let fields = datasetFields[currentDataset];
            if (!fields || fields.length === 0) {
                // Auto-generate fields from columns
                fields = columns.map(col => {
                    if (col.toLowerCase().includes('date') || col === 'ETA') return {name: col, type: 'date'};
                    if (col.toLowerCase().includes('alias') || col === 'Owner' || col === 'POC') return {name: col, type: 'alias'};
                    if (col.toLowerCase().includes('status')) return {name: col, type: 'select', options: ['Active', 'In Progress', 'Planned', 'Complete']};
                    if (col.toLowerCase().includes('notes') || col.toLowerCase().includes('description')) return {name: col, type: 'textarea'};
                    return {name: col, type: 'text'};
                });
            }
            return fields;
        }
        
        function getColumnValue(row, fieldName, altNames) {
            if (row[fieldName] !== undefined && row[fieldName] !== '') return row[fieldName];
            if (altNames) {
                for (const alt of altNames) {
                    if (row[alt] !== undefined && row[alt] !== '') return row[alt];
                }
            }
            return '';
        }
        
        function buildFormFields(row, isNew) {
            const fields = getFieldConfig();
            let html = '';
            
            fields.forEach((field, idx) => {
                const value = row ? getColumnValue(row, field.name, field.altNames) : '';
                const fieldId = `field_${idx}`;
                const required = field.required ? 'required' : '';
                
                html += `<div class="form-group">`;
                html += `<label>${field.name}${field.required ? ' *' : ''}</label>`;
                
                if (field.type === 'select') {
                    html += `<select id="${fieldId}" name="${field.name}" ${required}>`;
                    (field.options || []).forEach(opt => {
                        const selected = value === opt ? 'selected' : '';
                        const display = opt || '-- Select --';
                        html += `<option value="${opt}" ${selected}>${display}</option>`;
                    });
                    html += `</select>`;
                } else if (field.type === 'textarea') {
                    html += `<textarea id="${fieldId}" name="${field.name}" ${required}>${value}</textarea>`;
                } else if (field.type === 'date') {
                    html += `<input type="date" id="${fieldId}" name="${field.name}" value="${parseDate(value)}" ${required}>`;
                } else if (field.type === 'alias') {
                    html += `<div class="alias-wrapper">`;
                    html += `<input type="text" id="${fieldId}" name="${field.name}" value="${value}" class="alias-input" placeholder="Amazon alias" ${required}>`;
                    html += `<button type="button" class="lookup-btn" onclick="lookupAlias('${fieldId}')">Lookup</button>`;
                    html += `</div>`;
                } else {
                    html += `<input type="text" id="${fieldId}" name="${field.name}" value="${value}" ${required}>`;
                }
                
                html += `</div>`;
            });
            
            return html;
        }
        
        function openAddModal() {
            if (!userIsAdmin) { alert('Admin access required to add items'); return; }
            
            document.getElementById('modalTitle').textContent = 'Add New Item';
            document.getElementById('isNew').value = 'true';
            document.getElementById('rowIndex').value = '-1';
            document.getElementById('formFields').innerHTML = buildFormFields(null, true);
            
            // Auto-generate ID for action-plan
            if (currentDataset === 'action-plan') {
                let maxNum = 0;
                rowData.forEach(row => { 
                    const match = (row['Action ID'] || '').match(/AP-(\d+)/); 
                    if (match) maxNum = Math.max(maxNum, parseInt(match[1])); 
                });
                const idField = document.querySelector('[name="Action ID"]');
                if (idField) idField.value = `AP-${String(maxNum + 1).padStart(3, '0')}`;
            }
            
            document.getElementById('successMsg').style.display = 'none';
            document.getElementById('errorMsg').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }
        
        function openEditModal(index) {
            if (!userIsEditor) { openLoginModal(); return; }
            
            const row = rowData[index];
            document.getElementById('modalTitle').textContent = 'Edit Item';
            document.getElementById('isNew').value = 'false';
            document.getElementById('rowIndex').value = index;
            document.getElementById('formFields').innerHTML = buildFormFields(row, false);
            document.getElementById('successMsg').style.display = 'none';
            document.getElementById('errorMsg').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }
        
        function confirmDelete(index) {
            if (!userIsAdmin) { alert('Admin access required to delete items'); return; }
            const row = rowData[index];
            const itemName = row['Action ID'] || row['Stakeholder'] || row['Name'] || row[columns[0]] || `Item ${index + 1}`;
            if (confirm(`Are you sure you want to delete "${itemName}"?`)) deleteItem(index);
        }
        
        async function deleteItem(index) {
            try {
                const response = await fetch('/api/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dataset: currentDataset, rowIndex: index })
                });
                const result = await response.json();
                if (result.needsLogin) { openLoginModal(); return; }
                if (result.success) location.reload();
                else alert('Failed to delete: ' + (result.error || 'Unknown error'));
            } catch (err) { alert('Network error: ' + err.message); }
        }
        
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) { if (e.target === this) closeModal(this.id); });
        });
        
        // Login form
        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const alias = document.getElementById('loginAlias').value.trim();
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alias })
                });
                const result = await response.json();
                if (result.success) location.reload();
                else {
                    document.getElementById('loginErrorMsg').textContent = result.error || 'Login failed';
                    document.getElementById('loginErrorMsg').style.display = 'block';
                }
            } catch (err) {
                document.getElementById('loginErrorMsg').textContent = 'Network error';
                document.getElementById('loginErrorMsg').style.display = 'block';
            }
        });
        
        // Edit form
        document.getElementById('editForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const saveBtn = document.getElementById('saveBtn');
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            // Collect form data
            const formData = {
                dataset: currentDataset,
                rowIndex: parseInt(document.getElementById('rowIndex').value),
                isNew: document.getElementById('isNew').value === 'true',
                fields: {}
            };
            
            // Get all field values
            const fields = getFieldConfig();
            fields.forEach((field, idx) => {
                const fieldEl = document.getElementById(`field_${idx}`);
                if (fieldEl) {
                    let value = fieldEl.value;
                    if (field.type === 'date' && value) {
                        value = formatDate(value);
                    }
                    formData.fields[field.name] = value;
                    // Also set alt names
                    if (field.altNames) {
                        field.altNames.forEach(alt => formData.fields[alt] = value);
                    }
                }
            });
            
            try {
                const response = await fetch('/api/update-generic', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                const result = await response.json();
                if (result.needsLogin) { openLoginModal(); saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; return; }
                if (result.success) {
                    document.getElementById('successMsg').style.display = 'block';
                    setTimeout(() => { closeModal('editModal'); location.reload(); }, 1000);
                } else {
                    document.getElementById('errorMsg').textContent = result.error || 'Failed to save';
                    document.getElementById('errorMsg').style.display = 'block';
                }
            } catch (err) {
                document.getElementById('errorMsg').textContent = 'Network error: ' + err.message;
                document.getElementById('errorMsg').style.display = 'block';
            }
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Changes';
        });
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return view_dataset('action-plan')

@app.route('/<dataset>')
def view_dataset(dataset):
    if dataset not in DATASETS:
        return "Not found", 404
    
    result = load_from_s3(dataset)
    user = session.get('user')
    user_is_admin = is_admin()
    user_is_editor = is_editor()
    
    if isinstance(result, str):
        return render_template_string(HTML, 
            datasets=DATASETS, active=dataset, title=DATASETS[dataset], 
            error=result, columns=[], rows=[], stats=None,
            teams=TEAMS, phases=PHASES, workstreams=WORKSTREAMS,
            user=user, user_is_admin=user_is_admin, user_is_editor=user_is_editor,
            authorized_admins=', '.join([a for a in AUTHORIZED_ADMINS if a.strip()]),
            authorized_editors=', '.join([e for e in AUTHORIZED_EDITORS if e.strip()]))
    
    df = result
    stats = None
    if dataset == 'action-plan' and 'Status' in df.columns:
        stats = {
            'total': len(df),
            'active': len(df[df['Status'] == 'Active']),
            'progress': len(df[df['Status'] == 'In Progress']),
            'planned': len(df[df['Status'] == 'Planned'])
        }
    
    return render_template_string(HTML,
        datasets=DATASETS, active=dataset, title=DATASETS[dataset],
        error=None, columns=df.columns.tolist(), rows=df.to_dict('records'),
        stats=stats, teams=TEAMS, phases=PHASES, workstreams=WORKSTREAMS,
        user=user, user_is_admin=user_is_admin, user_is_editor=user_is_editor,
        authorized_admins=', '.join([a for a in AUTHORIZED_ADMINS if a.strip()]),
        authorized_editors=', '.join([e for e in AUTHORIZED_EDITORS if e.strip()]))

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    alias = data.get('alias', '').strip().lower()
    
    admins = [a.lower().strip() for a in AUTHORIZED_ADMINS if a.strip()]
    editors = [e.lower().strip() for e in AUTHORIZED_EDITORS if e.strip()]
    
    if alias in admins:
        session['user'] = alias
        return jsonify({'success': True, 'role': 'admin'})
    elif alias in editors:
        session['user'] = alias
        return jsonify({'success': True, 'role': 'editor'})
    else:
        return jsonify({'success': False, 'error': f'"{alias}" is not authorized. Contact an admin to get access.'})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/export/<dataset>/excel')
def export_excel(dataset):
    if dataset not in DATASETS:
        return "Not found", 404
    
    df = load_from_s3(dataset)
    if isinstance(df, str):
        return f"Error: {df}", 500
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=DATASETS[dataset][:31])
    output.seek(0)
    
    filename = f"MX_EFile_{dataset}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/export/<dataset>/csv')
def export_csv(dataset):
    if dataset not in DATASETS:
        return "Not found", 404
    
    df = load_from_s3(dataset)
    if isinstance(df, str):
        return f"Error: {df}", 500
    
    output = StringIO()
    df.to_csv(output, index=False)
    
    filename = f"MX_EFile_{dataset}_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/api/update-generic', methods=['POST'])
@login_required_editor
def update_generic():
    try:
        data = request.json
        dataset = data.get('dataset')
        row_index = data.get('rowIndex', -1)
        is_new = data.get('isNew', False)
        fields = data.get('fields', {})
        
        if dataset not in DATASETS:
            return jsonify({'success': False, 'error': 'Invalid dataset'})
        
        # Only admins can add new items
        if is_new and not is_admin():
            return jsonify({'success': False, 'error': 'Admin access required to add items'})
        
        df = load_from_s3(dataset)
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
        # Get old status for notification (action-plan only)
        old_status = ''
        if dataset == 'action-plan' and not is_new and row_index >= 0 and row_index < len(df):
            old_status = df.at[row_index, 'Status'] if 'Status' in df.columns else ''
        
        if is_new:
            new_row = {col: fields.get(col, '') for col in df.columns}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            if row_index < 0 or row_index >= len(df):
                return jsonify({'success': False, 'error': 'Invalid row index'})
            for col in df.columns:
                if col in fields:
                    df.at[row_index, col] = str(fields[col]) if fields[col] else ''
        
        result = save_to_s3(dataset, df)
        if result is True:
            # Send notification if status changed (action-plan only)
            if dataset == 'action-plan':
                new_status = fields.get('Status', '')
                if old_status and new_status and old_status != new_status:
                    send_notification(
                        fields.get('Action ID', ''),
                        fields.get('Action Item', ''),
                        old_status,
                        new_status,
                        session.get('user', 'unknown')
                    )
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete', methods=['POST'])
@login_required_admin
def delete_item():
    try:
        data = request.json
        dataset = data.get('dataset')
        row_index = data.get('rowIndex')
        
        if dataset not in DATASETS:
            return jsonify({'success': False, 'error': 'Invalid dataset'})
        
        df = load_from_s3(dataset)
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
        if row_index < 0 or row_index >= len(df):
            return jsonify({'success': False, 'error': 'Invalid row index'})
        
        df = df.drop(index=row_index).reset_index(drop=True)
        
        result = save_to_s3(dataset, df)
        if result is True:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
