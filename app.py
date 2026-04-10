from flask import Flask, render_template_string, jsonify, request, Response, session, redirect
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

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
S3_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

# Hardcoded Admins (only these can add/delete)
HARDCODED_ADMINS = ['alemaga', 'soemilio', 'gregonz']

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
STATUSES = ['Planned', 'In Progress', 'Active', 'Complete', 'On Hold']
RAG_STATUSES = ['Green', 'Amber', 'Red']

def get_s3_client():
    config = Config(connect_timeout=5, read_timeout=10)
    return boto3.client('s3', region_name=S3_REGION, config=config)

def load_registered_editors():
    """Load registered editors from S3"""
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key='config/editors.json')
        data = json.loads(response['Body'].read().decode('utf-8'))
        return data.get('editors', [])
    except Exception as e:
        print(f"Error loading editors: {e}")
        return []

def save_registered_editors(editors):
    """Save registered editors to S3"""
    try:
        s3 = get_s3_client()
        data = {
            "editors": editors,
            "updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        s3.put_object(Bucket=S3_BUCKET, Key='config/editors.json', 
                      Body=json.dumps(data, indent=2), ContentType='application/json')
        return True
    except Exception as e:
        print(f"Error saving editors: {e}")
        return False

def load_from_s3(folder):
    try:
        s3 = get_s3_client()
        key = f"{folder}/data.csv"
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
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
        key = f"{folder}/data.csv"
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=csv_buffer.getvalue(), ContentType='text/csv')
        return True
    except Exception as e:
        return str(e)

def is_admin():
    user = session.get('user', '').lower()
    return user in [a.lower() for a in HARDCODED_ADMINS]

def is_editor():
    user = session.get('user', '').lower()
    if not user:
        return False
    if user in [a.lower() for a in HARDCODED_ADMINS]:
        return True
    editors = load_registered_editors()
    return user in [e.lower() for e in editors]

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

def parse_date_to_input(date_str):
    """Convert date string to YYYY-MM-DD format for HTML date input"""
    if not date_str or date_str == 'nan' or str(date_str).strip() == '':
        return ''
    date_str = str(date_str).strip()
    # Try MM/DD/YYYY format
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', date_str)
    if match:
        return f"{match.group(3)}-{match.group(1).zfill(2)}-{match.group(2).zfill(2)}"
    # Try YYYY-MM-DD format (already correct)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    return ''

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>MX Customs E-File Tracker</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #003366; color: white; padding: 20px; margin: -20px -20px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .header-left h1 { margin: 0; font-size: 24px; }
        .header-left p { margin: 5px 0 0; opacity: 0.8; font-size: 14px; }
        .header-right { display: flex; align-items: center; gap: 15px; }
        .user-info { color: white; font-size: 14px; }
        .user-role { background: #0070c0; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 5px; }
        .user-role.admin { background: #28a745; }
        .user-role.editor { background: #ffc107; color: #333; }
        .login-btn, .logout-btn { background: #0070c0; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; text-decoration: none; font-size: 14px; }
        .login-btn:hover, .logout-btn:hover { background: #005a9e; }
        .nav { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .nav a { padding: 10px 20px; background: #003366; color: white; text-decoration: none; border-radius: 5px; font-size: 14px; }
        .nav a:hover, .nav a.active { background: #0070c0; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
        .card-header h2 { margin: 0; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th { background: #003366; color: white; padding: 8px 5px; text-align: left; position: sticky; top: 0; white-space: nowrap; }
        td { padding: 6px 5px; border-bottom: 1px solid #eee; vertical-align: middle; }
        tr:hover { background: #f0f7ff; }
        .error { background: #fee; padding: 20px; border-radius: 8px; color: #c00; }
        .stats { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat { background: white; padding: 15px 25px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-num { font-size: 28px; font-weight: bold; color: #003366; }
        .status-active { background: #90EE90; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-inprogress { background: #FFD700; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-planned { background: #E0E0E0; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-complete { background: #4CAF50; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
        .status-onhold { background: #999; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
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
        .inline-select { padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; cursor: pointer; min-width: 90px; }
        .inline-select:hover { border-color: #0070c0; }
        .inline-date { padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; cursor: pointer; width: 120px; }
        .inline-date:hover { border-color: #0070c0; }
        .saving { opacity: 0.5; pointer-events: none; }
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
        .alias-wrapper { position: relative; }
        .alias-input { padding-right: 80px !important; }
        .lookup-btn { position: absolute; right: 5px; top: 50%; transform: translateY(-50%); background: #0070c0; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .lookup-btn:hover { background: #005a9e; }
        .read-only-notice { background: #fff3cd; color: #856404; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
        .editor-notice { background: #d1ecf1; color: #0c5460; padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
        .link-btn { background: none; border: none; color: #0070c0; cursor: pointer; text-decoration: underline; font-size: 14px; }
        .link-btn:hover { color: #005a9e; }
        .signup-success { background: #d4edda; color: #155724; padding: 15px; border-radius: 6px; margin-bottom: 15px; text-align: center; }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>🇲🇽 MX Customs E-File Compliance Tracker</h1>
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
        <a href="/{{ key }}" class="{{ 'active' if active == key else '' }}">{{ name }}</a>
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
            🔒 <strong>View Only</strong> - <a href="#" onclick="openLoginModal(); return false;">Login</a> or <a href="#" onclick="openSignupModal(); return false;">Sign up</a> to edit items.
        </div>
        {% elif user_is_editor and not user_is_admin %}
        <div class="editor-notice">
            ✏️ <strong>Editor Mode</strong> - You can edit existing items using the inline dropdowns or Edit button.
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
                <tr data-index="{{ loop.index0 }}">
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
                        {% set row_idx = loop.parent.loop.index0 %}
                        {% set col_val = row.get(c, '') %}
                        {% if active == 'action-plan' and c == 'ETA' and user_is_editor %}
                            <input type="date" class="inline-date" 
                                   data-row="{{ row_idx }}" data-col="ETA"
                                   value="{{ col_val|parse_date_filter }}" 
                                   onchange="inlineUpdate(this)">
                        {% elif active == 'action-plan' and c == 'Status' and user_is_editor %}
                            <select class="inline-select" data-row="{{ row_idx }}" data-col="Status" onchange="inlineUpdate(this)">
                                {% for s in statuses %}
                                <option value="{{ s }}" {{ 'selected' if col_val == s else '' }}>{{ s }}</option>
                                {% endfor %}
                            </select>
                        {% elif active == 'action-plan' and c == 'RAG Status' and user_is_editor %}
                            <select class="inline-select" data-row="{{ row_idx }}" data-col="RAG Status" onchange="inlineUpdate(this)">
                                {% for r in rag_statuses %}
                                <option value="{{ r }}" {{ 'selected' if col_val == r else '' }}>{{ r }}</option>
                                {% endfor %}
                            </select>
                        {% elif c == 'Status' %}
                            <span class="status-{{ col_val|lower|replace(' ', '') }}">{{ col_val }}</span>
                        {% elif c == 'RAG Status' %}
                            <span class="rag-{{ col_val|lower }}">{{ col_val }}</span>
                        {% elif c == 'Priority' %}
                            <span class="priority-{{ col_val|lower }}">{{ col_val }}</span>
                        {% elif (c == 'Owner' or c == 'Stakeholder' or c == 'Alias' or c == 'POC') and col_val %}
                            <a href="https://phonetool.amazon.com/users/{{ col_val }}" target="_blank" class="owner-link">{{ col_val }}</a>
                        {% else %}
                            {{ col_val }}
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
                <button type="submit" class="save-btn">Login</button>
            </form>
            <p style="text-align: center; margin-top: 15px;">
                New user? <button type="button" class="link-btn" onclick="closeModal('loginModal'); openSignupModal();">Sign up as Editor</button>
            </p>
        </div>
    </div>
    
    <!-- Signup Modal -->
    <div id="signupModal" class="modal">
        <div class="modal-content" style="max-width: 400px;">
            <div class="modal-header">
                <h2>Sign Up as Editor</h2>
                <button class="close-btn" onclick="closeModal('signupModal')">&times;</button>
            </div>
            <div id="signupSuccessMsg" class="signup-success" style="display: none;"></div>
            <div id="signupErrorMsg" class="error-msg"></div>
            <form id="signupForm">
                <div class="form-group">
                    <label>Amazon Alias</label>
                    <input type="text" id="signupAlias" name="alias" placeholder="Enter your Amazon alias" required>
                </div>
                <p style="font-size: 12px; color: #666;">
                    As an Editor, you can edit existing items across all sections.
                    Only Admins can add or delete items.
                </p>
                <button type="submit" class="save-btn">Register as Editor</button>
            </form>
            <p style="text-align: center; margin-top: 15px;">
                Already registered? <button type="button" class="link-btn" onclick="closeModal('signupModal'); openLoginModal();">Login</button>
            </p>
        </div>
    </div>
    
    <!-- Edit Modal -->
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
        MX Customs E-File Compliance Tracker | GTS LATAM | <a href="/health">Health</a>
    </p>
    
    <script>
        const rowData = {{ rows_json | safe }};
        const columns = {{ columns_json | safe }};
        const currentDataset = "{{ active }}";
        const userIsEditor = {{ 'true' if user_is_editor else 'false' }};
        const userIsAdmin = {{ 'true' if user_is_admin else 'false' }};
        
        const teams = {{ teams_json | safe }};
        const phases = {{ phases_json | safe }};
        const workstreams = {{ workstreams_json | safe }};
        const statuses = {{ statuses_json | safe }};
        const ragStatuses = {{ rag_statuses_json | safe }};
        
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
                {name: 'Status', type: 'select', options: statuses},
                {name: 'Priority', type: 'select', options: ['P0', 'P1', 'P2']},
                {name: 'RAG Status', type: 'select', options: ragStatuses},
                {name: 'Reason for R/A', type: 'textarea'},
                {name: 'Path to Green', type: 'textarea'},
                {name: 'Notes', type: 'textarea'}
            ],
            'stakeholder-matrix': [
                {name: 'Team', type: 'select', options: ['', ...teams]},
                {name: 'Stakeholder', type: 'alias'},
                {name: 'Role', type: 'text'},
                {name: 'Involvement', type: 'select', options: ['High', 'Medium', 'Low']},
                {name: 'Communication', type: 'select', options: ['Email', 'Chime', 'Meetings', 'Slack']},
                {name: 'Responsibilities', type: 'textarea'},
                {name: 'Notes', type: 'textarea'}
            ],
            'default': []
        };
        
        function parseDate(dateStr) {
            if (!dateStr || dateStr === 'nan' || dateStr === '') return '';
            const match = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
            if (match) return match[3] + '-' + match[1].padStart(2, '0') + '-' + match[2].padStart(2, '0');
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return dateStr;
            return '';
        }
        
        function formatDateForSave(dateStr) {
            if (!dateStr) return '';
            const parts = dateStr.split('-');
            return parts.length === 3 ? parts[1] + '/' + parts[2] + '/' + parts[0] : dateStr;
        }
        
        function lookupAlias(fieldId) {
            const alias = document.getElementById(fieldId).value.trim();
            if (!alias) { alert('Please enter an alias'); return; }
            window.open('https://phonetool.amazon.com/users/' + alias, '_blank');
        }
        
        function closeModal(modalId) { document.getElementById(modalId).classList.remove('active'); }
        function openLoginModal() {
            document.getElementById('loginErrorMsg').style.display = 'none';
            document.getElementById('loginAlias').value = '';
            document.getElementById('loginModal').classList.add('active');
        }
        function openSignupModal() {
            document.getElementById('signupErrorMsg').style.display = 'none';
            document.getElementById('signupSuccessMsg').style.display = 'none';
            document.getElementById('signupForm').style.display = 'block';
            document.getElementById('signupAlias').value = '';
            document.getElementById('signupModal').classList.add('active');
        }
        
        async function inlineUpdate(el) {
            if (!userIsEditor) { openLoginModal(); return; }
            
            const rowIndex = parseInt(el.dataset.row);
            const column = el.dataset.col;
            let value = el.value;
            
            if (el.type === 'date' && value) {
                value = formatDateForSave(value);
            }
            
            const row = el.closest('tr');
            row.classList.add('saving');
            
            try {
                const response = await fetch('/api/inline-update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dataset: currentDataset, rowIndex: rowIndex, column: column, value: value })
                });
                const result = await response.json();
                row.classList.remove('saving');
                
                if (result.needsLogin) { openLoginModal(); return; }
                if (!result.success) {
                    alert('Failed to save: ' + (result.error || 'Unknown error'));
                    location.reload();
                }
            } catch (err) {
                row.classList.remove('saving');
                alert('Network error: ' + err.message);
            }
        }
        
        function getFieldConfig() {
            return datasetFields[currentDataset] || datasetFields['default'] || columns.map(c => ({name: c, type: 'text'}));
        }
        
        function buildFormFields(row, isNew) {
            const fields = getFieldConfig();
            if (fields.length === 0) {
                return columns.map((col, idx) => {
                    const val = row ? (row[col] || '') : '';
                    return '<div class="form-group"><label>' + col + '</label><input type="text" id="field_' + idx + '" name="' + col + '" value="' + val + '"></div>';
                }).join('');
            }
            
            return fields.map((field, idx) => {
                const value = row ? (row[field.name] || '') : '';
                const fieldId = 'field_' + idx;
                const req = field.required ? 'required' : '';
                let html = '<div class="form-group"><label>' + field.name + (field.required ? ' *' : '') + '</label>';
                
                if (field.type === 'select') {
                    html += '<select id="' + fieldId + '" name="' + field.name + '" ' + req + '>';
                    (field.options || []).forEach(opt => {
                        const sel = value === opt ? 'selected' : '';
                        html += '<option value="' + opt + '" ' + sel + '>' + (opt || '-- Select --') + '</option>';
                    });
                    html += '</select>';
                } else if (field.type === 'textarea') {
                    html += '<textarea id="' + fieldId + '" name="' + field.name + '" ' + req + '>' + value + '</textarea>';
                } else if (field.type === 'date') {
                    html += '<input type="date" id="' + fieldId + '" name="' + field.name + '" value="' + parseDate(value) + '" ' + req + '>';
                } else if (field.type === 'alias') {
                    html += '<div class="alias-wrapper"><input type="text" id="' + fieldId + '" name="' + field.name + '" value="' + value + '" class="alias-input" placeholder="Amazon alias" ' + req + '>';
                    html += '<button type="button" class="lookup-btn" onclick="lookupAlias(\'' + fieldId + '\')">Lookup</button></div>';
                } else {
                    html += '<input type="text" id="' + fieldId + '" name="' + field.name + '" value="' + value + '" ' + req + '>';
                }
                html += '</div>';
                return html;
            }).join('');
        }
        
        function openAddModal() {
            if (!userIsAdmin) { alert('Admin access required to add items'); return; }
            document.getElementById('modalTitle').textContent = 'Add New Item';
            document.getElementById('isNew').value = 'true';
            document.getElementById('rowIndex').value = '-1';
            document.getElementById('formFields').innerHTML = buildFormFields(null, true);
            
            if (currentDataset === 'action-plan') {
                let maxNum = 0;
                rowData.forEach(row => { 
                    const match = (row['Action ID'] || '').match(/AP-(\d+)/); 
                    if (match) maxNum = Math.max(maxNum, parseInt(match[1])); 
                });
                const idField = document.querySelector('[name="Action ID"]');
                if (idField) idField.value = 'AP-' + String(maxNum + 1).padStart(3, '0');
            }
            
            document.getElementById('successMsg').style.display = 'none';
            document.getElementById('errorMsg').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }
        
        function openEditModal(index) {
            if (!userIsEditor) { openLoginModal(); return; }
            document.getElementById('modalTitle').textContent = 'Edit Item';
            document.getElementById('isNew').value = 'false';
            document.getElementById('rowIndex').value = index;
            document.getElementById('formFields').innerHTML = buildFormFields(rowData[index], false);
            document.getElementById('successMsg').style.display = 'none';
            document.getElementById('errorMsg').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }
        
        function confirmDelete(index) {
            if (!userIsAdmin) { alert('Admin access required to delete items'); return; }
            const row = rowData[index];
            const itemName = row['Action ID'] || row['Team'] || row[columns[0]] || ('Item ' + (index + 1));
            if (confirm('Are you sure you want to delete "' + itemName + '"?')) deleteItem(index);
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
        
        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const alias = document.getElementById('loginAlias').value.trim().toLowerCase();
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alias: alias })
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
        
        document.getElementById('signupForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const alias = document.getElementById('signupAlias').value.trim().toLowerCase();
            try {
                const response = await fetch('/api/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alias: alias })
                });
                const result = await response.json();
                if (result.success) {
                    document.getElementById('signupSuccessMsg').innerHTML = '✓ Welcome, <strong>' + alias + '</strong>! You are now registered as an Editor.';
                    document.getElementById('signupSuccessMsg').style.display = 'block';
                    document.getElementById('signupForm').style.display = 'none';
                    setTimeout(function() { location.reload(); }, 1500);
                } else {
                    document.getElementById('signupErrorMsg').textContent = result.error || 'Registration failed';
                    document.getElementById('signupErrorMsg').style.display = 'block';
                }
            } catch (err) {
                document.getElementById('signupErrorMsg').textContent = 'Network error';
                document.getElementById('signupErrorMsg').style.display = 'block';
            }
        });
        
        document.getElementById('editForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const saveBtn = document.getElementById('saveBtn');
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            const fields = getFieldConfig();
            const formData = {
                dataset: currentDataset,
                rowIndex: parseInt(document.getElementById('rowIndex').value),
                isNew: document.getElementById('isNew').value === 'true',
                fields: {}
            };
            
            if (fields.length === 0) {
                columns.forEach((col, idx) => {
                    const el = document.getElementById('field_' + idx);
                    if (el) formData.fields[col] = el.value;
                });
            } else {
                fields.forEach((field, idx) => {
                    const el = document.getElementById('field_' + idx);
                    if (el) {
                        let val = el.value;
                        if (field.type === 'date' && val) val = formatDateForSave(val);
                        formData.fields[field.name] = val;
                    }
                });
            }
            
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
                    setTimeout(function() { closeModal('editModal'); location.reload(); }, 1000);
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

@app.template_filter('parse_date_filter')
def parse_date_filter(date_str):
    return parse_date_to_input(date_str)

@app.route('/')
def home():
    return view_dataset('action-plan')

@app.route('/<dataset>')
def view_dataset(dataset):
    if dataset not in DATASETS:
        return "Not found", 404
    
    try:
        result = load_from_s3(dataset)
        user = session.get('user')
        user_is_admin = is_admin()
        user_is_editor = is_editor()
        
        if isinstance(result, str):
            return render_template_string(HTML, 
                datasets=DATASETS, active=dataset, title=DATASETS[dataset], 
                error=result, columns=[], rows=[],
                rows_json='[]', columns_json='[]',
                teams_json=json.dumps(TEAMS), phases_json=json.dumps(PHASES),
                workstreams_json=json.dumps(WORKSTREAMS), statuses_json=json.dumps(STATUSES),
                rag_statuses_json=json.dumps(RAG_STATUSES), statuses=STATUSES, rag_statuses=RAG_STATUSES,
                stats=None, user=user, user_is_admin=user_is_admin, user_is_editor=user_is_editor)
        
        df = result
        stats = None
        if dataset == 'action-plan' and 'Status' in df.columns:
            stats = {
                'total': len(df),
                'active': len(df[df['Status'] == 'Active']),
                'progress': len(df[df['Status'] == 'In Progress']),
                'planned': len(df[df['Status'] == 'Planned'])
            }
        
        rows = df.to_dict('records')
        columns = df.columns.tolist()
        
        return render_template_string(HTML,
            datasets=DATASETS, active=dataset, title=DATASETS[dataset],
            error=None, columns=columns, rows=rows,
            rows_json=json.dumps(rows), columns_json=json.dumps(columns),
            teams_json=json.dumps(TEAMS), phases_json=json.dumps(PHASES),
            workstreams_json=json.dumps(WORKSTREAMS), statuses_json=json.dumps(STATUSES),
            rag_statuses_json=json.dumps(RAG_STATUSES), statuses=STATUSES, rag_statuses=RAG_STATUSES,
            stats=stats, user=user, user_is_admin=user_is_admin, user_is_editor=user_is_editor)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        alias = data.get('alias', '').strip().lower()
        
        if not alias:
            return jsonify({'success': False, 'error': 'Please enter an alias'})
        
        if alias in [a.lower() for a in HARDCODED_ADMINS]:
            session['user'] = alias
            return jsonify({'success': True, 'role': 'admin'})
        
        editors = load_registered_editors()
        if alias in [e.lower() for e in editors]:
            session['user'] = alias
            return jsonify({'success': True, 'role': 'editor'})
        
        return jsonify({'success': False, 'error': f'"{alias}" is not registered. Please sign up first.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        alias = data.get('alias', '').strip().lower()
        
        if not alias:
            return jsonify({'success': False, 'error': 'Please enter an alias'})
        
        if not alias.replace('-', '').replace('_', '').isalnum():
            return jsonify({'success': False, 'error': 'Invalid alias format'})
        
        if alias in [a.lower() for a in HARDCODED_ADMINS]:
            session['user'] = alias
            return jsonify({'success': True, 'role': 'admin'})
        
        editors = load_registered_editors()
        if alias in [e.lower() for e in editors]:
            session['user'] = alias
            return jsonify({'success': True, 'role': 'editor'})
        
        editors.append(alias)
        if save_registered_editors(editors):
            session['user'] = alias
            return jsonify({'success': True, 'role': 'editor'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save registration'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
    return Response(output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'})

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
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'})

@app.route('/api/inline-update', methods=['POST'])
@login_required_editor
def inline_update():
    try:
        data = request.json
        dataset = data.get('dataset')
        row_index = data.get('rowIndex')
        column = data.get('column')
        value = data.get('value', '')
        
        if dataset not in DATASETS:
            return jsonify({'success': False, 'error': 'Invalid dataset'})
        
        df = load_from_s3(dataset)
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
        if row_index < 0 or row_index >= len(df):
            return jsonify({'success': False, 'error': 'Invalid row index'})
        
        if column not in df.columns:
            return jsonify({'success': False, 'error': f'Column "{column}" not found'})
        
        df.at[row_index, column] = str(value) if value else ''
        
        result = save_to_s3(dataset, df)
        if result is True:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': str(result)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
        
        if is_new and not is_admin():
            return jsonify({'success': False, 'error': 'Admin access required to add items'})
        
        df = load_from_s3(dataset)
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
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
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': str(result)})
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
        return jsonify({'success': False, 'error': str(result)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
