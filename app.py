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
    try:
        config = Config(connect_timeout=5, read_timeout=10)
        s3 = boto3.client('s3', region_name=S3_REGION, config=config)
        key = f"{folder}/data.csv"
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        return pd.read_csv(StringIO(response['Body'].read().decode('utf-8')))
    except Exception as e:
        return str(e)

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>MX E-File Tracker</title>
    <style>
        body { font-family: -apple-system, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #003366; color: white; padding: 20px; margin: -20px -20px 20px; }
        .nav { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .nav a { padding: 10px 20px; background: #003366; color: white; text-decoration: none; border-radius: 5px; }
        .nav a:hover, .nav a.active { background: #0070c0; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #003366; color: white; padding: 12px 8px; text-align: left; }
        td { padding: 10px 8px; border-bottom: 1px solid #eee; }
        tr:hover { background: #f8f9fa; }
        .error { background: #fee; padding: 20px; border-radius: 8px; color: #c00; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat { background: white; padding: 15px 25px; border-radius: 8px; text-align: center; }
        .stat-num { font-size: 28px; font-weight: bold; color: #003366; }
    </style>
</head>
<body>
    <div class="header"><h1>🇲🇽 MX Customs E-File Compliance Tracker</h1><p>GTS LATAM | Article 59 MX Customs Law</p></div>
    <div class="nav">
        {% for key, name in datasets.items() %}<a href="/{{ key }}" class="{{ 'active' if active == key }}">{{ name }}</a>{% endfor %}
    </div>
    {% if stats %}<div class="stats">
        <div class="stat"><div class="stat-num">{{ stats.total }}</div><div>Total</div></div>
        <div class="stat"><div class="stat-num">{{ stats.active }}</div><div>Active</div></div>
        <div class="stat"><div class="stat-num">{{ stats.progress }}</div><div>In Progress</div></div>
    </div>{% endif %}
    <div class="card">
        <h2>{{ title }}</h2>
        {% if error %}<div class="error">{{ error }}</div>{% else %}
        <div style="overflow-x:auto;"><table><thead><tr>{% for c in columns %}<th>{{ c }}</th>{% endfor %}</tr></thead>
        <tbody>{% for row in rows %}<tr>{% for c in columns %}<td>{{ row[c] or '' }}</td>{% endfor %}</tr>{% endfor %}</tbody></table></div>
        {% endif %}
    </div>
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
        return render_template_string(HTML, datasets=DATASETS, active=dataset, title=DATASETS[dataset], error=result, columns=[], rows=[], stats=None)
    df = result
    stats = None
    if dataset == 'action-plan' and 'Status' in df.columns:
        stats = {'total': len(df), 'active': len(df[df['Status']=='Active']), 'progress': len(df[df['Status']=='In Progress'])}
    return render_template_string(HTML, datasets=DATASETS, active=dataset, title=DATASETS[dataset], error=None, columns=df.columns.tolist(), rows=df.to_dict('records'), stats=stats)

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
