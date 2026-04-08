from flask import Flask, render_template_string, jsonify, request
import pandas as pd
import boto3
from botocore.config import Config
from io import StringIO
import os

app = Flask(__name__)

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
S3_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

DATASETS = {
    'action-plan': 'Action Plan',
    'business-requirements': 'Business Requirements',
    'doc-checklist': 'Doc Checklist',
    'stakeholder-matrix': 'Stakeholder Matrix',
    'risk-penalties': 'Risk and Penalties',
    'operational-volume': 'Operational Volume'
}

# Team options
TEAMS = [
    'GTS',
    'AP/FinOps',
    'Supply Chain',
    'InTech',
    'Legal',
    'HR/Payroll',
    'Accounting',
    'Retail',
    'GREF',
    'Customs Broker'
]

def get_s3_client():
    config = Config(connect_timeout=5, read_timeout=10)
    return boto3.client('s3', region_name=S3_REGION, config=config)

def load_from_s3(folder):
    try:
        s3 = get_s3_client()
        key = f"{folder}/data.csv"
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        df = pd.read_csv(StringIO(response['Body'].read().decode('utf-8')))
        # Convert all columns to string to avoid dtype issues
        df = df.fillna('')
        for col in df.columns:
            df[col] = df[col].astype(str)
            # Clean up 'nan' strings
            df[col] = df[col].replace('nan', '')
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

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>MX E-File Tracker</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #003366; color: white; padding: 20px; margin: -20px -20px 20px; }
        .header h1 { margin: 0; }
        .header p { margin: 5px 0 0; opacity: 0.8; }
        .nav { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .nav a { padding: 10px 20px; background: #003366; color: white; text-decoration: none; border-radius: 5px; }
        .nav a:hover, .nav a.active { background: #0070c0; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
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
        .owner-link { color: #0070c0; text-decoration: none; }
        .owner-link:hover { text-decoration: underline; }
        
        /* Modal styles */
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
        .alias-info { font-size: 12px; color: #666; margin-top: 5px; }
        .date-input { cursor: pointer; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🇲🇽 MX Customs E-File Compliance Tracker</h1>
        <p>GTS LATAM | Article 59 MX Customs Law</p>
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
        <h2>{{ title }}</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% else %}
        <div style="overflow-x:auto;">
        <table>
            <thead>
                <tr>
                    {% if editable %}<th>Edit</th>{% endif %}
                    {% for c in columns %}<th>{{ c }}</th>{% endfor %}
                </tr>
            </thead>
            <tbody>
            {% for row in rows %}
                <tr>
                    {% if editable %}
                    <td><button class="edit-btn" onclick="openEditModal({{ loop.index0 }})">Edit</button></td>
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
    
    <!-- Edit Modal -->
    <div id="editModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Edit Action Item</h2>
                <button class="close-btn" onclick="closeModal()">&times;</button>
            </div>
            <div id="successMsg" class="success-msg">Changes saved successfully!</div>
            <div id="errorMsg" class="error-msg"></div>
            <form id="editForm">
                <input type="hidden" id="rowIndex" name="rowIndex">
                <input type="hidden" id="dataset" name="dataset" value="{{ active }}">
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Action ID</label>
                        <input type="text" id="actionId" readonly class="readonly">
                    </div>
                    <div class="form-group">
                        <label>Phase</label>
                        <input type="text" id="phase" readonly class="readonly">
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Action Item</label>
                    <textarea id="actionItem" readonly class="readonly"></textarea>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Team</label>
                        <select id="team" name="team">
                            <option value="">-- Select Team --</option>
                            {% for t in teams %}
                            <option value="{{ t }}">{{ t }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Owner (Amazon Alias)</label>
                        <div class="alias-wrapper">
                            <input type="text" id="owner" name="owner" class="alias-input" placeholder="e.g., johndoe">
                            <button type="button" class="lookup-btn" onclick="lookupAlias()">Lookup</button>
                        </div>
                        <div id="aliasInfo" class="alias-info"></div>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>ETA</label>
                        <input type="date" id="eta" name="eta" class="date-input">
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
    
    <p style="color: #999; text-align: center; margin-top: 30px;">
        MX E-File Compliance Tracker | GTS LATAM | 
        <a href="/health">Health</a>
    </p>
    
    <script>
        // Store row data for editing
        const rowData = {{ rows | tojson | safe }};
        const columns = {{ columns | tojson | safe }};
        
        // Convert date from various formats to YYYY-MM-DD for input
        function parseDate(dateStr) {
            if (!dateStr || dateStr === 'nan' || dateStr === '') return '';
            
            // Try MM/DD/YYYY format
            const mmddyyyy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/;
            let match = dateStr.match(mmddyyyy);
            if (match) {
                const mm = match[1].padStart(2, '0');
                const dd = match[2].padStart(2, '0');
                return `${match[3]}-${mm}-${dd}`;
            }
            
            // Try Q1 2026 format - convert to end of quarter
            const quarter = /^Q(\d)\s*(\d{4})$/i;
            match = dateStr.match(quarter);
            if (match) {
                const q = parseInt(match[1]);
                const year = match[2];
                const monthEnd = q * 3;
                return `${year}-${String(monthEnd).padStart(2, '0')}-28`;
            }
            
            // Try to parse as date
            try {
                const d = new Date(dateStr);
                if (!isNaN(d.getTime())) {
                    return d.toISOString().split('T')[0];
                }
            } catch (e) {}
            
            return '';
        }
        
        // Convert date from YYYY-MM-DD to MM/DD/YYYY for display/saving
        function formatDate(dateStr) {
            if (!dateStr) return '';
            const parts = dateStr.split('-');
            if (parts.length === 3) {
                return `${parts[1]}/${parts[2]}/${parts[0]}`;
            }
            return dateStr;
        }
        
        function openEditModal(index) {
            const row = rowData[index];
            document.getElementById('rowIndex').value = index;
            document.getElementById('actionId').value = row['Action ID'] || '';
            document.getElementById('phase').value = row['Phase'] || '';
            document.getElementById('actionItem').value = row['Action Item'] || '';
            document.getElementById('team').value = row['Team'] || '';
            document.getElementById('owner').value = row['Owner'] || '';
            
            // Handle ETA/Target Date field
            const etaValue = row['ETA'] || row['Target Date'] || '';
            document.getElementById('eta').value = parseDate(etaValue);
            
            document.getElementById('status').value = row['Status'] || 'Planned';
            document.getElementById('ragStatus').value = row['RAG Status'] || 'Green';
            document.getElementById('priority').value = row['Priority'] || 'P1';
            document.getElementById('reasonRA').value = row['Reason for R/A'] || '';
            document.getElementById('pathToGreen').value = row['Path to Green'] || '';
            document.getElementById('notes').value = row['Notes'] || '';
            
            document.getElementById('aliasInfo').innerHTML = '';
            document.getElementById('successMsg').style.display = 'none';
            document.getElementById('errorMsg').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('editModal').classList.remove('active');
        }
        
        // Lookup Amazon alias in Phonetool
        function lookupAlias() {
            const alias = document.getElementById('owner').value.trim();
            if (!alias) {
                document.getElementById('aliasInfo').innerHTML = '<span style="color: #c00;">Please enter an alias</span>';
                return;
            }
            
            // Open Phonetool in new tab for verification
            window.open(`https://phonetool.amazon.com/users/${alias}`, '_blank');
            document.getElementBy
