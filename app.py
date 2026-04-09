from flask import Flask, render_template_string, jsonify, request, Response, session, redirect, url_for
import pandas as pd
import boto3
from botocore.config import Config
from io import StringIO, BytesIO
import os
import json
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mx-efile-tracker-secret-2026')

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
S3_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
SES_SENDER = os.environ.get('SES_SENDER', 'noreply@amazon.com')

# Authorized editors (Amazon aliases)
AUTHORIZED_EDITORS = os.environ.get('AUTHORIZED_EDITORS', 'alemaga,admin').split(',')

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
    """Send email notification when status changes"""
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
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
    except Exception as e:
        print(f"Failed to send notification: {e}")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'success': False, 'error': 'Authentication required', 'needsLogin': True}), 401
        return f(*args, **kwargs)
    return decorated_function

def is_authorized_editor():
    user = session.get('user', '')
    return user.lower() in [e.lower().strip() for e in AUTHORIZED_EDITORS]

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>MX E-File Tracker</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #003366; color: white; padding: 20px; margin: -20px -20px 20px; display: flex; justify-content: space-between; align-items: center; }
        .header-left h1 { margin: 0; }
        .header-left p { margin: 5px 0 0; opacity: 0.8; }
        .header-right { display: flex; align-items: center; gap: 15px; }
        .user-info { color: white; font-size: 14px; }
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
            <span class="user-info">👤 {{ user }}{% if is_editor %} (Editor){% endif %}</span>
            <a href="/logout" class="logout-btn">Logout</a>
            {% else %}
            <button class="login-btn" onclick="openLoginModal()">Login to Edit</button>
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
                <a href="/export/{{ active }}/excel" class="export-btn">📥 Export Excel</a>
                <a href="/export/{{ active }}/csv" class="export-btn">📥 Export CSV</a>
                {% if editable and is_editor %}
                <button class="add-btn" onclick="openAddModal()">+ Add New Item</button>
                {% endif %}
            </div>
        </div>
        
        {% if editable and not is_editor %}
        <div class="read-only-notice">
            🔒 <strong>View Only</strong> - <a href="#" onclick="openLoginModal(); return false;">Login</a> with an authorized alias to edit items.
        </div>
        {% endif %}
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% else %}
        <div style="overflow-x:auto;">
        <table>
            <thead>
                <tr>
                    {% if editable and is_editor %}<th>Actions</th>{% endif %}
                    {% for c in columns %}<th>{{ c }}</th>{% endfor %}
                </tr>
            </thead>
            <tbody>
            {% for row in rows %}
                <tr>
                    {% if editable and is_editor %}
                    <td>
                        <button class="edit-btn" onclick="openEditModal({{ loop.index0 }})">Edit</button>
                        <button class="delete-btn" onclick="confirmDelete({{ loop.index0 }})">✕</button>
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
                        {% elif c == 'Owner' and row[c] %}
                            <a href="https://phonetool.amazon.com/users/{{ row[c] }}" target="_blank" class="owner-link">{{ row[c] }}</a>
                        {% elif c == 'POC' and row[c] %}
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
                <p style="font-size: 12px; color: #666; margin-top: -10px;">
                    Authorized editors: {{ authorized_editors }}
                </p>
                <button type="submit" class="save-btn">Login</button>
            </form>
        </div>
    </div>
    
    <!-- Edit Modal for Action Plan -->
    <div id="editModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modalTitle">Edit Action Item</h2>
                <button class="close-btn" onclick="closeModal('editModal')">&times;</button>
            </div>
            <div id="successMsg" class="success-msg">Changes saved successfully!</div>
            <div id="errorMsg" class="error-msg"></div>
            <form id="editForm">
                <input type="hidden" id="rowIndex" name="rowIndex" value="-1">
                <input type="hidden" id="dataset" name="dataset" value="{{ active }}">
                <input type="hidden" id="isNew" name="isNew" value="false">
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Action ID</label>
                        <input type="text" id="actionId" name="actionId">
                    </div>
                    <div class="form-group">
                        <label>Phase</label>
                        <select id="phase" name="phase">
                            {% for p in phases %}<option value="{{ p }}">{{ p }}</option>{% endfor %}
                        </select>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Workstream</label>
                        <select id="workstream" name="workstream">
                            {% for w in workstreams %}<option value="{{ w }}">{{ w }}</option>{% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Team</label>
                        <select id="team" name="team">
                            <option value="">-- Select Team --</option>
                            {% for t in teams %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Action Item</label>
                    <textarea id="actionItem" name="actionItem" required></textarea>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Owner (Amazon Alias)</label>
                        <div class="alias-wrapper">
                            <input type="text" id="owner" name="owner" class="alias-input" placeholder="e.g., johndoe">
                            <button type="button" class="lookup-btn" onclick="lookupAlias('owner')">Lookup</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Dependencies</label>
                        <input type="text" id="dependencies" name="dependencies" placeholder="e.g., AP-001, AP-002">
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>ETA</label>
                        <input type="date" id="eta" name="eta">
                    </div>
                    <div class="form-group">
                        <label>Status</label>
                        <select id="status" name="status">
                            <option value="Planned">Planned</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Active">Active</option>
                            <option value="Complete">Complete</option>
                            <option value="On Hold">On Hold</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>RAG Status</label>
                        <select id="ragStatus" name="ragStatus">
                            <option value="Green">Green</option>
                            <option value="Amber">Amber</option>
                            <option value="Red">Red</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Priority</label>
                        <select id="priority" name="priority">
                            <option value="P0">P0 - Critical</option>
                            <option value="P1">P1 - High</option>
                            <option value="P2">P2 - Medium</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Reason for R/A</label>
                    <textarea id="reasonRA" name="reasonRA" placeholder="Explain why status is Red or Amber..."></textarea>
                </div>
                
                <div class="form-group">
                    <label>Path to Green</label>
                    <textarea id="pathToGreen" name="pathToGreen" placeholder="What needs to happen to get back to Green..."></textarea>
                </div>
                
                <div class="form-group">
                    <label>Notes</label>
                    <textarea id="notes" name="notes"></textarea>
                </div>
                
                <button type="submit" class="save-btn" id="saveBtn">Save Changes</button>
            </form>
        </div>
    </div>
    
    <!-- Stakeholder Modal -->
    <div id="stakeholderModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="stakeholderModalTitle">Edit Stakeholder</h2>
                <button class="close-btn" onclick="closeModal('stakeholderModal')">&times;</button>
            </div>
            <div id="stakeholderSuccessMsg" class="success-msg">Changes saved successfully!</div>
            <div id="stakeholderErrorMsg" class="error-msg"></div>
            <form id="stakeholderForm">
                <input type="hidden" id="stakeholderRowIndex" name="rowIndex" value="-1">
                <input type="hidden" id="stakeholderIsNew" name="isNew" value="false">
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Stakeholder Name</label>
                        <input type="text" id="stakeholderName" name="stakeholderName" required>
                    </div>
                    <div class="form-group">
                        <label>Alias</label>
                        <div class="alias-wrapper">
                            <input type="text" id="stakeholderAlias" name="stakeholderAlias" class="alias-input" placeholder="Amazon alias">
                            <button type="button" class="lookup-btn" onclick="lookupAlias('stakeholderAlias')">Lookup</button>
                        </div>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Role/Title</label>
                        <input type="text" id="stakeholderRole" name="stakeholderRole">
                    </div>
                    <div class="form-group">
                        <label>Team/Organization</label>
                        <select id="stakeholderTeam" name="stakeholderTeam">
                            <option value="">-- Select Team --</option>
                            {% for t in teams %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
                        </select>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Involvement Level</label>
                        <select id="involvementLevel" name="involvementLevel">
                            <option value="High">High</option>
                            <option value="Medium">Medium</option>
                            <option value="Low">Low</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Communication Preference</label>
                        <select id="commPreference" name="commPreference">
                            <option value="Email">Email</option>
                            <option value="Chime">Chime</option>
                            <option value="Meetings">Meetings</option>
                            <option value="Slack">Slack</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Responsibilities</label>
                    <textarea id="responsibilities" name="responsibilities"></textarea>
                </div>
                
                <div class="form-group">
                    <label>Notes</label>
                    <textarea id="stakeholderNotes" name="stakeholderNotes"></textarea>
                </div>
                
                <button type="submit" class="save-btn" id="stakeholderSaveBtn">Save Stakeholder</button>
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
        const isEditor = {{ 'true' if is_editor else 'false' }};
        
        function parseDate(dateStr) {
            if (!dateStr || dateStr === 'nan' || dateStr === '') return '';
            const mmddyyyy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/;
            let match = dateStr.match(mmddyyyy);
            if (match) return `${match[3]}-${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}`;
            const quarter = /^Q(\d)\s*(\d{4})$/i;
            match = dateStr.match(quarter);
            if (match) return `${match[2]}-${String(parseInt(match[1]) * 3).padStart(2, '0')}-28`;
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
        
        function openAddModal() {
            if (!isEditor) { openLoginModal(); return; }
            
            if (currentDataset === 'action-plan') {
                document.getElementById('modalTitle').textContent = 'Add New Action Item';
                document.getElementById('isNew').value = 'true';
                document.getElementById('rowIndex').value = '-1';
                let maxNum = 0;
                rowData.forEach(row => { const match = (row['Action ID'] || '').match(/AP-(\d+)/); if (match) maxNum = Math.max(maxNum, parseInt(match[1])); });
                document.getElementById('actionId').value = `AP-${String(maxNum + 1).padStart(3, '0')}`;
                ['actionItem', 'owner', 'dependencies', 'eta', 'reasonRA', 'pathToGreen', 'notes'].forEach(f => document.getElementById(f).value = '');
                document.getElementById('phase').value = 'Short-Term';
                document.getElementById('workstream').value = 'Document Discovery';
                document.getElementById('team').value = '';
                document.getElementById('status').value = 'Planned';
                document.getElementById('ragStatus').value = 'Green';
                document.getElementById('priority').value = 'P1';
                document.getElementById('successMsg').style.display = 'none';
                document.getElementById('errorMsg').style.display = 'none';
                document.getElementById('editModal').classList.add('active');
            } else if (currentDataset === 'stakeholder-matrix') {
                document.getElementById('stakeholderModalTitle').textContent = 'Add New Stakeholder';
                document.getElementById('stakeholderIsNew').value = 'true';
                document.getElementById('stakeholderRowIndex').value = '-1';
                ['stakeholderName', 'stakeholderAlias', 'stakeholderRole', 'responsibilities', 'stakeholderNotes'].forEach(f => document.getElementById(f).value = '');
                document.getElementById('stakeholderTeam').value = '';
                document.getElementById('involvementLevel').value = 'Medium';
                document.getElementById('commPreference').value = 'Email';
                document.getElementById('stakeholderSuccessMsg').style.display = 'none';
                document.getElementById('stakeholderErrorMsg').style.display = 'none';
                document.getElementById('stakeholderModal').classList.add('active');
            }
        }
        
        function openEditModal(index) {
            if (!isEditor) { openLoginModal(); return; }
            const row = rowData[index];
            
            if (currentDataset === 'action-plan') {
                document.getElementById('modalTitle').textContent = 'Edit Action Item';
                document.getElementById('isNew').value = 'false';
                document.getElementById('rowIndex').value = index;
                document.getElementById('actionId').value = row['Action ID'] || '';
                document.getElementById('phase').value = row['Phase'] || 'Short-Term';
                document.getElementById('workstream').value = row['Workstream'] || '';
                document.getElementById('actionItem').value = row['Action Item'] || '';
                document.getElementById('team').value = row['Team'] || '';
                document.getElementById('owner').value = row['Owner'] || '';
                document.getElementById('dependencies').value = row['Dependencies'] || '';
                document.getElementById('eta').value = parseDate(row['ETA'] || row['Target Date'] || '');
                document.getElementById('status').value = row['Status'] || 'Planned';
                document.getElementById('ragStatus').value = row['RAG Status'] || 'Green';
                document.getElementById('priority').value = row['Priority'] || 'P1';
                document.getElementById('reasonRA').value = row['Reason for R/A'] || '';
                document.getElementById('pathToGreen').value = row['Path to Green'] || '';
                document.getElementById('notes').value = row['Notes'] || '';
                document.getElementById('successMsg').style.display = 'none';
                document.getElementById('errorMsg').style.display = 'none';
                document.getElementById('editModal').classList.add('active');
            } else if (currentDataset === 'stakeholder-matrix') {
                document.getElementById('stakeholderModalTitle').textContent = 'Edit Stakeholder';
                document.getElementById('stakeholderIsNew').value = 'false';
                document.getElementById('stakeholderRowIndex').value = index;
                document.getElementById('stakeholderName').value = row['Stakeholder'] || row['Name'] || '';
                document.getElementById('stakeholderAlias').value = row['Alias'] || row['POC'] || '';
                document.getElementById('stakeholderRole').value = row['Role'] || row['Title'] || '';
                document.getElementById('stakeholderTeam').value = row['Team'] || row['Organization'] || '';
                document.getElementById('involvementLevel').value = row['Involvement'] || row['Involvement Level'] || 'Medium';
                document.getElementById('commPreference').value = row['Communication'] || row['Comm Preference'] || 'Email';
                document.getElementById('responsibilities').value = row['Responsibilities'] || '';
                document.getElementById('stakeholderNotes').value = row['Notes'] || '';
                document.getElementById('stakeholderSuccessMsg').style.display = 'none';
                document.getElementById('stakeholderErrorMsg').style.display = 'none';
                document.getElementById('stakeholderModal').classList.add('active');
            }
        }
        
        function confirmDelete(index) {
            if (!isEditor) { openLoginModal(); return; }
            const row = rowData[index];
            const itemName = row['Action ID'] || row['Stakeholder'] || row['Name'] || `Item ${index + 1}`;
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
        
        // Action Plan form
        document.getElementById('editForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const saveBtn = document.getElementById('saveBtn');
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            const formData = {
                dataset: currentDataset,
                rowIndex: parseInt(document.getElementById('rowIndex').value),
                isNew: document.getElementById('isNew').value === 'true',
                actionId: document.getElementById('actionId').value,
                phase: document.getElementById('phase').value,
                workstream: document.getElementById('workstream').value,
                actionItem: document.getElementById('actionItem').value,
                team: document.getElementById('team').value,
                owner: document.getElementById('owner').value.trim(),
                dependencies: document.getElementById('dependencies').value,
                eta: formatDate(document.getElementById('eta').value),
                status: document.getElementById('status').value,
                ragStatus: document.getElementById('ragStatus').value,
                priority: document.getElementById('priority').value,
                reasonRA: document.getElementById('reasonRA').value,
                pathToGreen: document.getElementById('pathToGreen').value,
                notes: document.getElementById('notes').value
            };
            
            try {
                const response = await fetch('/api/update', {
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
        
        // Stakeholder form
        document.getElementById('stakeholderForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const saveBtn = document.getElementById('stakeholderSaveBtn');
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            const formData = {
                dataset: 'stakeholder-matrix',
                rowIndex: parseInt(document.getElementById('stakeholderRowIndex').value),
                isNew: document.getElementById('stakeholderIsNew').value === 'true',
                stakeholderName: document.getElementById('stakeholderName').value,
                alias: document.getElementById('stakeholderAlias').value.trim(),
                role: document.getElementById('stakeholderRole').value,
                team: document.getElementById('stakeholderTeam').value,
                involvementLevel: document.getElementById('involvementLevel').value,
                commPreference: document.getElementById('commPreference').value,
                responsibilities: document.getElementById('responsibilities').value,
                notes: document.getElementById('stakeholderNotes').value
            };
            
            try {
                const response = await fetch('/api/update-stakeholder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                const result = await response.json();
                if (result.needsLogin) { openLoginModal(); saveBtn.disabled = false; saveBtn.textContent = 'Save Stakeholder'; return; }
                if (result.success) {
                    document.getElementById('stakeholderSuccessMsg').style.display = 'block';
                    setTimeout(() => { closeModal('stakeholderModal'); location.reload(); }, 1000);
                } else {
                    document.getElementById('stakeholderErrorMsg').textContent = result.error || 'Failed to save';
                    document.getElementById('stakeholderErrorMsg').style.display = 'block';
                }
            } catch (err) {
                document.getElementById('stakeholderErrorMsg').textContent = 'Network error: ' + err.message;
                document.getElementById('stakeholderErrorMsg').style.display = 'block';
            }
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Stakeholder';
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
    is_editor = is_authorized_editor()
    
    if isinstance(result, str):
        return render_template_string(HTML, 
            datasets=DATASETS, active=dataset, title=DATASETS[dataset], 
            error=result, columns=[], rows=[], stats=None, editable=False, 
            teams=TEAMS, phases=PHASES, workstreams=WORKSTREAMS,
            user=user, is_editor=is_editor, authorized_editors=', '.join(AUTHORIZED_EDITORS))
    
    df = result
    stats = None
    if dataset == 'action-plan' and 'Status' in df.columns:
        stats = {
            'total': len(df),
            'active': len(df[df['Status'] == 'Active']),
            'progress': len(df[df['Status'] == 'In Progress']),
            'planned': len(df[df['Status'] == 'Planned'])
        }
    
    editable = dataset in ['action-plan', 'stakeholder-matrix']
    
    return render_template_string(HTML,
        datasets=DATASETS, active=dataset, title=DATASETS[dataset],
        error=None, columns=df.columns.tolist(), rows=df.to_dict('records'),
        stats=stats, editable=editable, teams=TEAMS, phases=PHASES, workstreams=WORKSTREAMS,
        user=user, is_editor=is_editor, authorized_editors=', '.join(AUTHORIZED_EDITORS))

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    alias = data.get('alias', '').strip().lower()
    
    if alias in [e.lower().strip() for e in AUTHORIZED_EDITORS]:
        session['user'] = alias
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': f'"{alias}" is not an authorized editor'})

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

@app.route('/api/update', methods=['POST'])
@login_required
def update_item():
    try:
        data = request.json
        dataset = data.get('dataset')
        row_index = data.get('rowIndex', -1)
        is_new = data.get('isNew', False)
        
        if dataset != 'action-plan':
            return jsonify({'success': False, 'error': 'Use /api/update-stakeholder for stakeholder matrix'})
        
        df = load_from_s3(dataset)
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
        # Get old status for notification
        old_status = ''
        if not is_new and row_index >= 0 and row_index < len(df):
            old_status = df.at[row_index, 'Status'] if 'Status' in df.columns else ''
        
        new_row = {
            'Action ID': data.get('actionId', ''),
            'Phase': data.get('phase', ''),
            'Workstream': data.get('workstream', ''),
            'Action Item': data.get('actionItem', ''),
            'Team': data.get('team', ''),
            'Owner': data.get('owner', ''),
            'Dependencies': data.get('dependencies', ''),
            'ETA': data.get('eta', ''),
            'Status': data.get('status', ''),
            'Priority': data.get('priority', ''),
            'Notes': data.get('notes', ''),
            'RAG Status': data.get('ragStatus', ''),
            'Reason for R/A': data.get('reasonRA', ''),
            'Path to Green': data.get('pathToGreen', '')
        }
        
        if is_new:
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            if row_index < 0 or row_index >= len(df):
                return jsonify({'success': False, 'error': 'Invalid row index'})
            for col, value in new_row.items():
                if col in df.columns:
                    df.at[row_index, col] = str(value) if value else ''
        
        result = save_to_s3(dataset, df)
        if result is True:
            # Send notification if status changed
            new_status = data.get('status', '')
            if old_status and new_status and old_status != new_status:
                send_notification(
                    data.get('actionId', ''),
                    data.get('actionItem', ''),
                    old_status,
                    new_status,
                    session.get('user', 'unknown')
                )
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-stakeholder', methods=['POST'])
@login_required
def update_stakeholder():
    try:
        data = request.json
        row_index = data.get('rowIndex', -1)
        is_new = data.get('isNew', False)
        
        df = load_from_s3('stakeholder-matrix')
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
        col_mappings = {
            'Stakeholder': data.get('stakeholderName', ''),
            'Name': data.get('stakeholderName', ''),
            'Alias': data.get('alias', ''),
            'POC': data.get('alias', ''),
            'Role': data.get('role', ''),
            'Title': data.get('role', ''),
            'Team': data.get('team', ''),
            'Organization': data.get('team', ''),
            'Involvement': data.get('involvementLevel', ''),
            'Involvement Level': data.get('involvementLevel', ''),
            'Communication': data.get('commPreference', ''),
            'Comm Preference': data.get('commPreference', ''),
            'Responsibilities': data.get('responsibilities', ''),
            'Notes': data.get('notes', '')
        }
        
        if is_new:
            new_row = {col: col_mappings.get(col, '') for col in df.columns}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            if row_index < 0 or row_index >= len(df):
                return jsonify({'success': False, 'error': 'Invalid row index'})
            for col in df.columns:
                if col in col_mappings:
                    df.at[row_index, col] = str(col_mappings[col]) if col_mappings[col] else ''
        
        result = save_to_s3('stakeholder-matrix', df)
        if result is True:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete', methods=['POST'])
@login_required
def delete_item():
    try:
        data = request.json
        dataset = data.get('dataset')
        row_index = data.get('rowIndex')
        
        if dataset not in ['action-plan', 'stakeholder-matrix']:
            return jsonify({'success': False, 'error': 'Dataset not editable'})
        
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
