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

def get_s3_client():
    config = Config(connect_timeout=5, read_timeout=10)
    return boto3.client('s3', region_name=S3_REGION, config=config)

def load_from_s3(folder):
    try:
        s3 = get_s3_client()
        key = f"{folder}/data.csv"
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        return pd.read_csv(StringIO(response['Body'].read().decode('utf-8')))
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
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { background: #003366; color: white; padding: 10px 6px; text-align: left; position: sticky; top: 0; }
        td { padding: 8px 6px; border-bottom: 1px solid #eee; vertical-align: top; }
        tr:hover { background: #f0f7ff; }
        .error { background: #fee; padding: 20px; border-radius: 8px; color: #c00; }
        .stats { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat { background: white; padding: 15px 25px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-num { font-size: 28px; font-weight: bold; color: #003366; }
        .status-active { background: #90EE90; padding: 2px 8px; border-radius: 3px; }
        .status-inprogress { background: #FFD700; padding: 2px 8px; border-radius: 3px; }
        .status-planned { background: #E0E0E0; padding: 2px 8px; border-radius: 3px; }
        .rag-green { background: #90EE90; padding: 2px 8px; border-radius: 3px; }
        .rag-amber { background: #FFD700; padding: 2px 8px; border-radius: 3px; }
        .rag-red { background: #FF6B6B; color: white; padding: 2px 8px; border-radius: 3px; }
        .priority-p0 { background: #FF6B6B; color: white; padding: 2px 8px; border-radius: 3px; font-weight: bold; }
        .priority-p1 { background: #FFD700; padding: 2px 8px; border-radius: 3px; }
        .priority-p2 { background: #90EE90; padding: 2px 8px; border-radius: 3px; }
        .edit-btn { background: #0070c0; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .edit-btn:hover { background: #005a9e; }
        
        /* Modal styles */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
        .modal.active { display: flex; align-items: center; justify-content: center; }
        .modal-content { background: white; padding: 30px; border-radius: 12px; width: 90%; max-width: 600px; max-height: 90vh; overflow-y: auto; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .modal-header h2 { margin: 0; color: #003366; }
        .close-btn { background: none; border: none; font-size: 24px; cursor: pointer; color: #666; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 600; color: #333; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
        .form-group textarea { min-height: 80px; resize: vertical; }
        .form-row { display: flex; gap: 15px; }
        .form-row .form-group { flex: 1; }
        .save-btn { background: #003366; color: white; border: none; padding: 12px 30px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; margin-top: 10px; }
        .save-btn:hover { background: #004488; }
        .save-btn:disabled { background: #ccc; cursor: not-allowed; }
        .success-msg { background: #d4edda; color: #155724; padding: 10px; border-radius: 6px; margin-bottom: 15px; display: none; }
        .error-msg { background: #f8d7da; color: #721c24; padding: 10px; border-radius: 6px; margin-bottom: 15px; display: none; }
        .readonly { background: #f5f5f5; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🇲🇽 MX E-File Compliance Tracker</h1>
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
                
                <div class="form-group">
                    <label>Action ID</label>
                    <input type="text" id="actionId" readonly class="readonly">
                </div>
                
                <div class="form-group">
                    <label>Action Item</label>
                    <textarea id="actionItem" readonly class="readonly"></textarea>
                </div>
                
                <div class="form-row">
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
                    <div class="form-group">
                        <label>RAG Status</label>
                        <select id="ragStatus" name="ragStatus">
                            <option value="Green">Green</option>
                            <option value="Amber">Amber</option>
                            <option value="Red">Red</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>Owner</label>
                        <input type="text" id="owner" name="owner">
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
        
        function openEditModal(index) {
            const row = rowData[index];
            document.getElementById('rowIndex').value = index;
            document.getElementById('actionId').value = row['Action ID'] || '';
            document.getElementById('actionItem').value = row['Action Item'] || '';
            document.getElementById('status').value = row['Status'] || 'Planned';
            document.getElementById('ragStatus').value = row['RAG Status'] || 'Green';
            document.getElementById('owner').value = row['Owner'] || '';
            document.getElementById('priority').value = row['Priority'] || 'P1';
            document.getElementById('reasonRA').value = row['Reason for R/A'] || '';
            document.getElementById('pathToGreen').value = row['Path to Green'] || '';
            document.getElementById('notes').value = row['Notes'] || '';
            
            document.getElementById('successMsg').style.display = 'none';
            document.getElementById('errorMsg').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('editModal').classList.remove('active');
        }
        
        // Close modal on outside click
        document.getElementById('editModal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });
        
        // Handle form submission
        document.getElementById('editForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const saveBtn = document.getElementById('saveBtn');
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            const formData = {
                dataset: document.getElementById('dataset').value,
                rowIndex: parseInt(document.getElementById('rowIndex').value),
                status: document.getElementById('status').value,
                ragStatus: document.getElementById('ragStatus').value,
                owner: document.getElementById('owner').value,
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
                
                if (result.success) {
                    document.getElementById('successMsg').style.display = 'block';
                    setTimeout(() => {
                        closeModal();
                        location.reload();
                    }, 1000);
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
    
    if isinstance(result, str):
        return render_template_string(HTML, 
            datasets=DATASETS, active=dataset, title=DATASETS[dataset], 
            error=result, columns=[], rows=[], stats=None, editable=False)
    
    df = result
    
    # Calculate stats for action plan
    stats = None
    if dataset == 'action-plan' and 'Status' in df.columns:
        stats = {
            'total': len(df),
            'active': len(df[df['Status'] == 'Active']),
            'progress': len(df[df['Status'] == 'In Progress']),
            'planned': len(df[df['Status'] == 'Planned'])
        }
    
    # Only action-plan is editable
    editable = (dataset == 'action-plan')
    
    return render_template_string(HTML,
        datasets=DATASETS, active=dataset, title=DATASETS[dataset],
        error=None, columns=df.columns.tolist(), rows=df.to_dict('records'),
        stats=stats, editable=editable)

@app.route('/api/update', methods=['POST'])
def update_item():
    try:
        data = request.json
        dataset = data.get('dataset')
        row_index = data.get('rowIndex')
        
        if dataset != 'action-plan':
            return jsonify({'success': False, 'error': 'Only Action Plan is editable'})
        
        # Load current data
        df = load_from_s3(dataset)
        if isinstance(df, str):
            return jsonify({'success': False, 'error': df})
        
        # Update the row
        if row_index < 0 or row_index >= len(df):
            return jsonify({'success': False, 'error': 'Invalid row index'})
        
        # Update editable fields
        df.at[row_index, 'Status'] = data.get('status', df.at[row_index, 'Status'])
        df.at[row_index, 'RAG Status'] = data.get('ragStatus', df.at[row_index, 'RAG Status'])
        df.at[row_index, 'Owner'] = data.get('owner', df.at[row_index, 'Owner'])
        df.at[row_index, 'Priority'] = data.get('priority', df.at[row_index, 'Priority'])
        df.at[row_index, 'Notes'] = data.get('notes', df.at[row_index, 'Notes'])
        
        # Update R/A fields if they exist
        if 'Reason for R/A' in df.columns:
            df.at[row_index, 'Reason for R/A'] = data.get('reasonRA', '')
        if 'Path to Green' in df.columns:
            df.at[row_index, 'Path to Green'] = data.get('pathToGreen', '')
        
        # Save back to S3
        result = save_to_s3(dataset, df)
        if result is True:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
