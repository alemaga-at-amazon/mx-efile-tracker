from flask import Flask, render_template_string, jsonify
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

def load_from_s3(folder):
    """Load CSV from S3"""
    try:
        config = Config(connect_timeout=5, read_timeout=10)
        s3 = boto3.client('s3', region_name=S3_REGION, config=config)
        key = f"{folder}/data.csv"
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        csv_content = response['Body'].read().decode('utf-8')
        return pd.read_csv(StringIO(csv_content))
    except Exception as e:
        return None, str(e)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>MX E-File Tracker</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #003366; color: white; padding: 20px; margin: -20px -20px 20px -20px; }
        .header h1 { margin: 0; }
        .header p { margin: 5px 0 0 0; opacity: 0.8; }
        .nav { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .nav a { padding: 10px 20px; background: #003366; color: white; text-decoration: none; border-radius: 5px; }
        .nav a:hover { background: #004488; }
        .nav a.active { background: #0070c0; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #003366; color: white; padding: 12px 8px; text-align: left; position: sticky; top: 0; }
        td { padding: 10px 8px; border-bottom: 1px solid #eee; }
        tr:hover { background: #f8f9fa; }
        .status-active { background: #90EE90; padding: 3px 8px; border-radius: 3px; }
        .status-progress { background: #FFD700; padding: 3px 8px; border-radius: 3px; }
        .status-planned { background: #E0E0E0; padding: 3px 8px; border-radius: 3px; }
        .priority-p0 { background: #FF6B6B; color: white; padding: 3px 8px; border-radius: 3px; }
        .priority-p1 { background: #FFD700; padding: 3px 8px; border-radius: 3px; }
        .rag-green { background: #90EE90; padding: 3px 8px; border-radius: 3px; }
        .rag-amber { background: #FFD700; padding: 3px 8px; border-radius: 3px; }
        .rag-red { background: #FF6B6B; color: white; padding: 3px 8px; border-radius: 3px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-box { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; min-width: 120px; }
        .stat-box .number { font-size: 32px; font-weight: bold; color: #003366; }
        .stat-box .label { color: #666; margin-top: 5px; }
        .error { background: #fee; border: 1px solid #fcc; padding: 20px; border-radius: 8px; color: #c00; }
        .table-container { overflow-x: auto; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🇲🇽 MX E-File Compliance Tracker</h1>
        <p>Global Trade Services LATAM | Article 59 MX Customs Law</p>
    </div>
    
    <div class="nav">
        {% for key, name in datasets.items() %}
        <a href="/{{ key }}" class="{{ 'active' if active == key else '' }}">{{ name }}</a>
        {% endfor %}
    </div>
    
    {% if stats %}
    <div class="stats">
        <div class="stat-box"><div class="number">{{ stats.total }}</div><div class="label">Total Items</div></div>
        <div class="stat-box"><div class="number">{{ stats.active }}</div><div class="label">Active</div></div>
        <div class="stat-box"><div class="number">{{ stats.in_progress }}</div><div class="label">In Progress</div></div>
        <div class="stat-box"><div class="number">{{ stats.planned }}</div><div class="label">Planned</div></div>
    </div>
    {% endif %}
    
    <div class="card">
        <h2>{{ title }}</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% else %}
        <div class="table-container">
        <table>
            <thead>
                <tr>
                {% for col in columns %}
                    <th>{{ col }}</th>
                {% endfor %}
                </tr>
            </thead>
            <tbody>
            {% for row in rows %}
                <tr>
                {% for col in columns %}
                    <td>
                    {% if col == 'Status' %}
                        <span class="status-{{ row[col]|lower|replace(' ', '') if row[col] else '' }}">{{ row[col] or '' }}</span>
                    {% elif col == 'Priority' %}
                        <span class="priority-{{ row[col]|lower if row[col] else '' }}">{{ row[col] or '' }}</span>
                    {% elif col == 'RAG Status' %}
                        <span class="rag-{{ row[col]|lower if row[col] else '' }}">{{ row[col] or '' }}</span>
                    {% else %}
                        {{ row[col] or '' }}
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
    
    <p style="color: #999; text-align: center;">Data syncs weekly from SharePoint (Monday 6AM) | <a href="/health">Health Check</a></p>
</body>
</html>
'''

@app.route('/')
def home():
    return view_dataset('action-plan')

@app.route('/<dataset>')
def view_dataset(dataset):
    if dataset not in DATASETS:
        return "Dataset not found", 404
    
    result = load_from_s3(dataset)
    
    if isinstance(result, tuple):
        # Error occurred
        return render_template_string(HTML_TEMPLATE,
            datasets=DATASETS,
            active=dataset,
            title=DATASETS[dataset],
            error=result[1],
            columns=[],
            rows=[],
            stats=None
        )
    
    df = result
    columns = df.columns.tolist()
    rows = df.to_dict('records')
    
    # Calculate stats for action plan
    stats = None
    if dataset == 'action-plan' and 'Status' in df.columns:
        stats = {
            'total': len(df),
            'active': len(df[df['Status'] == 'Active']),
            'in_progress': len(df[df['Status'] == 'In Progress']),
            'planned': len(df[df['Status'] == 'Planned'])
        }
    
    return render_template_string(HTML_TEMPLATE,
        datasets=DATASETS,
        active=dataset,
        title=DATASETS[dataset],
        error=None,
        columns=columns,
        rows=rows,
        stats=stats
    )

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
