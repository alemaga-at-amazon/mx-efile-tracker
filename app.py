from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return '''
    <html>
    <head><title>MX E-File Tracker</title></head>
    <body style="font-family: Arial; padding: 40px;">
        <h1>🇲🇽 MX E-File Tracker</h1>
        <p>✅ Flask is working!</p>
        <p>Next: Add S3 data connection</p>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    return 'ok'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
