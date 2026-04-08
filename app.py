"""
MX E-File Compliance Tracker - Debug Version
"""

import streamlit as st
import pandas as pd
import os

# Page config
st.set_page_config(
    page_title="MX E-File Tracker",
    page_icon="📋",
    layout="wide"
)

# Show environment variables for debugging
st.title("🇲🇽 MX E-File Tracker - Debug Mode")
st.markdown("---")

st.subheader("Environment Variables")
st.write(f"S3_BUCKET: `{os.environ.get('S3_BUCKET', 'NOT SET')}`")
st.write(f"AWS_REGION: `{os.environ.get('AWS_REGION', 'NOT SET')}`")
st.write(f"AWS_DEFAULT_REGION: `{os.environ.get('AWS_DEFAULT_REGION', 'NOT SET')}`")

st.markdown("---")
st.subheader("S3 Connection Test")

try:
    import boto3
    from botocore.config import Config
    
    st.write("✅ boto3 imported successfully")
    
    bucket = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    
    config = Config(connect_timeout=5, read_timeout=10)
    s3 = boto3.client('s3', region_name=region, config=config)
    
    st.write(f"✅ S3 client created for region: {region}")
    st.write(f"📦 Attempting to list bucket: {bucket}")
    
    # Try to list objects
    response = s3.list_objects_v2(Bucket=bucket, MaxKeys=5)
    
    st.write("✅ S3 connection successful!")
    st.write(f"Found {response.get('KeyCount', 0)} objects:")
    
    for obj in response.get('Contents', []):
        st.write(f"  - {obj['Key']}")
        
except Exception as e:
    st.error(f"❌ Error: {type(e).__name__}")
    st.error(f"Message: {str(e)}")

st.markdown("---")
st.write("If you see this page, Streamlit is working correctly.")

