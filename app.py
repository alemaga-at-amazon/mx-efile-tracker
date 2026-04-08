"""
MX E-File Compliance Tracker
Web Dashboard for GTS LATAM Team
Deployed on AWS App Runner
"""

import streamlit as st
import pandas as pd
import boto3
from io import StringIO
import os

# Page config
st.set_page_config(
    page_title="MX E-File Tracker",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# S3 Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'gts-latam-efile-tracker')
S3_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Dataset mapping
DATASETS = {
    'Action Plan': 'action-plan/data.csv',
    'Business Requirements': 'business-requirements/data.csv',
    'Doc Checklist': 'doc-checklist/data.csv',
    'Stakeholder Matrix': 'stakeholder-matrix/data.csv',
    'Risk and Penalties': 'risk-penalties/data.csv',
    'Operational Volume': 'operational-volume/data.csv'
}

@st.cache_data(ttl=300)
def load_data_from_s3(key):
    """Load CSV from S3 bucket"""
    try:
        from botocore.config import Config
        config = Config(connect_timeout=5, read_timeout=10)
        s3 = boto3.client('s3', region_name=S3_REGION, config=config)
        
        st.sidebar.text(f"Loading: {key}")  # Debug
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        csv_content = response['Body'].read().decode('utf-8')
        return pd.read_csv(StringIO(csv_content))
    except Exception as e:
        st.error(f"S3 Error: {type(e).__name__}: {e}")
        st.error(f"Bucket: {S3_BUCKET}, Key: {key}, Region: {S3_REGION}")
        return None


def style_rag_status(val):
    """Color code RAG status"""
    if val == 'Green':
        return 'background-color: #90EE90'
    elif val == 'Amber':
        return 'background-color: #FFD700'
    elif val == 'Red':
        return 'background-color: #FF6B6B'
    return ''

def style_priority(val):
    """Color code priority"""
    if val == 'P0':
        return 'background-color: #FF6B6B; color: white'
    elif val == 'P1':
        return 'background-color: #FFD700'
    elif val == 'P2':
        return 'background-color: #90EE90'
    return ''

def style_status(val):
    """Color code status"""
    if val == 'Active':
        return 'background-color: #90EE90'
    elif val == 'In Progress':
        return 'background-color: #FFD700'
    elif val == 'Planned':
        return 'background-color: #E0E0E0'
    return ''

# Header
st.title("🇲🇽 MX E-File Compliance Tracker")
st.markdown("**Global Trade Services LATAM** | Article 59 MX Customs Law Compliance")
st.markdown("---")

# Sidebar
st.sidebar.title("Navigation")
dataset_choice = st.sidebar.selectbox("Select Dataset", list(DATASETS.keys()))

st.sidebar.markdown("---")
st.sidebar.markdown("### Quick Stats")

# Load Action Plan for stats
action_plan = load_data_from_s3(DATASETS['Action Plan'])
if action_plan is not None:
    total_actions = len(action_plan)
    active = len(action_plan[action_plan['Status'] == 'Active']) if 'Status' in action_plan.columns else 0
    in_progress = len(action_plan[action_plan['Status'] == 'In Progress']) if 'Status' in action_plan.columns else 0
    
    st.sidebar.metric("Total Action Items", total_actions)
    st.sidebar.metric("Active", active)
    st.sidebar.metric("In Progress", in_progress)

st.sidebar.markdown("---")
st.sidebar.markdown("### Data Refresh")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("*Data syncs from SharePoint weekly (Monday 6AM)*")

# Main content
st.header(f"📊 {dataset_choice}")

# Load selected dataset
df = load_data_from_s3(DATASETS[dataset_choice])

if df is not None:
    # Filters for Action Plan
    if dataset_choice == 'Action Plan':
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            phases = ['All'] + list(df['Phase'].unique()) if 'Phase' in df.columns else ['All']
            phase_filter = st.selectbox("Phase", phases)
        
        with col2:
            statuses = ['All'] + list(df['Status'].unique()) if 'Status' in df.columns else ['All']
            status_filter = st.selectbox("Status", statuses)
        
        with col3:
            priorities = ['All'] + list(df['Priority'].dropna().unique()) if 'Priority' in df.columns else ['All']
            priority_filter = st.selectbox("Priority", priorities)
        
        with col4:
            owners = ['All'] + list(df['Owner'].dropna().unique()) if 'Owner' in df.columns else ['All']
            owner_filter = st.selectbox("Owner", owners)
        
        # Apply filters
        filtered_df = df.copy()
        if phase_filter != 'All':
            filtered_df = filtered_df[filtered_df['Phase'] == phase_filter]
        if status_filter != 'All':
            filtered_df = filtered_df[filtered_df['Status'] == status_filter]
        if priority_filter != 'All':
            filtered_df = filtered_df[filtered_df['Priority'] == priority_filter]
        if owner_filter != 'All':
            filtered_df = filtered_df[filtered_df['Owner'] == owner_filter]
        
        st.markdown(f"*Showing {len(filtered_df)} of {len(df)} items*")
        
        # Style the dataframe
        styled_df = filtered_df.style
        if 'RAG Status' in filtered_df.columns:
            styled_df = styled_df.applymap(style_rag_status, subset=['RAG Status'])
        if 'Priority' in filtered_df.columns:
            styled_df = styled_df.applymap(style_priority, subset=['Priority'])
        if 'Status' in filtered_df.columns:
            styled_df = styled_df.applymap(style_status, subset=['Status'])
        
        st.dataframe(styled_df, use_container_width=True, height=500)
        
        # Summary by Phase
        st.markdown("---")
        st.subheader("📈 Summary by Phase")
        
        if 'Phase' in df.columns and 'Status' in df.columns:
            summary = df.groupby(['Phase', 'Status']).size().unstack(fill_value=0)
            st.dataframe(summary, use_container_width=True)
    
    else:
        # Generic display for other datasets
        st.dataframe(df, use_container_width=True, height=500)

    # Download button
    st.markdown("---")
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"{dataset_choice.lower().replace(' ', '_')}.csv",
        mime="text/csv"
    )

else:
    st.error("Failed to load data. Please check S3 connection.")

# Footer
st.markdown("---")
st.markdown("*MX E-File Compliance Tracker | GTS LATAM | © 2026*")
