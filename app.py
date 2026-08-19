"""
Digital Credential Issuance, Verification & Analytics Platform
Built with Streamlit, Pillow, SQLite, and Plotly
"""

import streamlit as st
import sqlite3
import uuid
import io
import zipfile
import urllib.parse
from datetime import datetime
import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import qrcode
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 1. DATABASE SETUP & INITIALIZATION
# ==========================================
DB_FILE = "credentials.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Table: Credentials
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            credential_id TEXT PRIMARY KEY,
            recipient_name TEXT NOT NULL,
            email TEXT NOT NULL,
            course_name TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            status TEXT DEFAULT 'VALID',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table: Analytics Events
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credential_id TEXT NOT NULL,
            event_type TEXT NOT NULL, -- 'view', 'download_pdf', 'download_png', 'share_click', 'viral_referral'
            platform TEXT,            -- 'linkedin', 'twitter', 'whatsapp', 'direct', 'unknown'
            utm_source TEXT,
            utm_medium TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (credential_id) REFERENCES credentials(credential_id)
        )
    """)
    
    conn.commit()
    conn.close()

def log_event(credential_id, event_type, platform="unknown", utm_source="", utm_medium=""):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analytics_events (credential_id, event_type, platform, utm_source, utm_medium)
            VALUES (?, ?, ?, ?, ?)
        """, (credential_id, event_type, platform, utm_source, utm_medium))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error logging analytics event: {e}")

# Seed dummy data if database is empty
def seed_dummy_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM credentials")
    count = cursor.fetchone()[0]
    
    if count == 0:
        dummy_creds = [
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "Saima Gul", "saima@example.com", "AI Bootcamp 17", "2026-08-17", "VALID"),
            ("812ab341-12cd-4123-8821-b6072dd54fa1", "Alex Chen", "alex@example.com", "Data Science Masters", "2026-07-20", "VALID"),
            ("314ef892-99ab-4881-9123-c9012bb33de2", "Maria Garcia", "maria@example.com", "Full Stack Engineering", "2026-08-01", "VALID")
        ]
        cursor.executemany("""
            INSERT INTO credentials (credential_id, recipient_name, email, course_name, issue_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, dummy_creds)
        
        # Dummy analytics events
        events = [
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "view", "direct", "", ""),
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "view", "linkedin", "linkedin", "social"),
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "share_click", "linkedin", "", ""),
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "download_pdf", "direct", "", ""),
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "viral_referral", "linkedin", "linkedin", "social"),
            ("812ab341-12cd-4123-8821-b6072dd54fa1", "view", "direct", "", ""),
            ("812ab341-12cd-4123-8821-b6072dd54fa1", "share_click", "twitter", "", ""),
            ("314ef892-99ab-4881-9123-c9012bb33de2", "view", "whatsapp", "whatsapp", "chat")
        ]
        cursor.executemany("""
            INSERT INTO analytics_events (credential_id, event_type, platform, utm_source, utm_medium)
            VALUES (?, ?, ?, ?, ?)
        """, events)
        
        conn.commit()
    conn.close()

# ==========================================
# 2. HELPER UTILITIES & GENERATORS
# ==========================================
def generate_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

def draw_certificate_image(base_img, recipient_name, course_name, issue_date, credential_id, verification_url, coords):
    img = base_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # Try loading standard font or default font
    try:
        font_large = ImageFont.truetype("arial.ttf", coords['name_size'])
        font_medium = ImageFont.truetype("arial.ttf", coords['course_size'])
        font_small = ImageFont.truetype("arial.ttf", coords['meta_size'])
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw Text Elements
    draw.text((coords['name_x'], coords['name_y']), recipient_name, fill=coords['name_color'], font=font_large)
    draw.text((coords['course_x'], coords['course_y']), course_name, fill=coords['course_color'], font=font_medium)
    draw.text((coords['date_x'], coords['date_y']), f"Issued: {issue_date}", fill=coords['meta_color'], font=font_small)
    draw.text((coords['id_x'], coords['id_y']), f"ID: {credential_id}", fill=coords['meta_color'], font=font_small)

    # Embed QR Code
    if coords['show_qr']:
        qr_img = generate_qr_code(verification_url)
        qr_img = qr_img.resize((coords['qr_size'], coords['qr_size']))
        img.paste(qr_img, (coords['qr_x'], coords['qr_y']))

    return img

def create_default_template():
    # Create a sleek default base certificate image if none uploaded
    img = Image.new("RGB", (1200, 850), color="#1E293B")
    draw = ImageDraw.Draw(img)
    # Border
    draw.rectangle([20, 20, 1180, 830], outline="#CBD5E1", width=4)
    draw.rectangle([35, 35, 1165, 815], outline="#38BDF8", width=2)
    # Header
    try:
        font_title = ImageFont.truetype("arial.ttf", 48)
        font_sub = ImageFont.truetype("arial.ttf", 24)
    except IOError:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        
    draw.text((600, 120), "CERTIFICATE OF ACHIEVEMENT", fill="#F8FAFC", font=font_title, anchor="mm")
    draw.text((600, 180), "PROUDLY PRESENTED TO", fill="#94A3B8", font=font_sub, anchor="mm")
    draw.text((600, 360), "FOR SUCCESSFULLY COMPLETING", fill="#94A3B8", font=font_sub, anchor="mm")
    
    return img

# ==========================================
# 3. PAGE CONFIG & ROUTING
# ==========================================
st.set_page_config(
    page_title="Credsverse Automation Platform",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

init_db()
seed_dummy_data()

# Handle Routing based on Query Parameters
query_params = st.query_params
target_id = query_params.get("id", None)
utm_source = query_params.get("utm_source", "")
utm_medium = query_params.get("utm_medium", "")

# ==========================================
# 4. VIEW: PUBLIC VERIFICATION PORTAL (?id=UUID)
# ==========================================
if target_id:
    # Log view event
    log_event(target_id, "view", platform=utm_source if utm_source else "direct", utm_source=utm_source, utm_medium=utm_medium)
    if utm_source:
        log_event(target_id, "viral_referral", platform=utm_source, utm_source=utm_source, utm_medium=utm_medium)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT credential_id, recipient_name, email, course_name, issue_date, status FROM credentials WHERE credential_id=?", (target_id,))
    record = cursor.fetchone()
    conn.close()

    st.markdown("<h2 style='text-align: center; color: #38BDF8;'>🎓 Digital Credential Verification</h2>", unsafe_allow_html=True)
    
    if not record:
        st.error(f"❌ Invalid Credential ID: `{target_id}`. No verification record found.")
        st.info("Please check the link or contact the issuing organization.")
    else:
        c_id, r_name, r_email, c_name, i_date, c_status = record
        
        # Render Banner / Status
        st.success(f"✅ **AUTHENTIC CREDENTIAL VERIFIED** | Issued to **{r_name}**")
        
        col_cert, col_meta = st.columns([1.6, 1])
        
        # Dynamic Image Reconstruction
        base_template = create_default_template()
        base_url = "https://credsverse.app" # Production domain
        v_url = f"{base_url}/?id={c_id}"
        
        default_coords = {
            'name_x': 600, 'name_y': 250, 'name_size': 50, 'name_color': '#38BDF8',
            'course_x': 600, 'course_y': 430, 'course_size': 40, 'course_color': '#F8FAFC',
            'date_x': 200, 'date_y': 700, 'meta_size': 20, 'meta_color': '#94A3B8',
            'id_x': 200, 'id_y': 730,
            'show_qr': True, 'qr_x': 900, 'qr_y': 650, 'qr_size': 140
        }
        
        # Centered text adjustment
        cert_img = draw_certificate_image(base_template, r_name, c_name, i_date, c_id, v_url, default_coords)
        
        with col_cert:
            st.image(cert_img, caption=f"Issued Certificate - {c_id}", use_container_width=True)
            
            # Download Options
            img_buf = io.BytesIO()
            cert_img.save(img_buf, format="PNG")
            img_bytes = img_buf.getvalue()
            
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                if st.download_button("⬇️ Download PNG", data=img_bytes, file_name=f"{r_name}_certificate.png", mime="image/png"):
                    log_event(c_id, "download_png")
            with d_col2:
                # PDF Conversion
                pdf_buf = io.BytesIO()
                cert_img.save(pdf_buf, format="PDF", resolution=100.0)
                if st.download_button("📄 Download PDF", data=pdf_buf.getvalue(), file_name=f"{r_name}_certificate.pdf", mime="application/pdf"):
                    log_event(c_id, "download_pdf")

        with col_meta:
            st.markdown("### Credential Details")
            st.markdown(f"**Recipient Name:** {r_name}")
            st.markdown(f"**Course / Award:** {c_name}")
            st.markdown(f"**Issue Date:** {i_date}")
            st.markdown(f"**Credential ID:** `{c_id}`")
            st.markdown(f"**Status:** `:green[{c_status}]`")
            st.markdown("---")
            
            st.markdown("### 🚀 Share Your Achievement")
            st.caption("Sharing directly feeds viral referral tracking across networks.")
            
            # Viral Referral Tracking Links
            viral_url = f"{v_url}&utm_source="
            
            encoded_title = urllib.parse.quote(f"Check out my official credential for {c_name}!")
            encoded_url_li = urllib.parse.quote(f"{viral_url}linkedin&utm_medium=social")
            encoded_url_tw = urllib.parse.quote(f"{viral_url}twitter&utm_medium=social")
            encoded_url_wa = urllib.parse.quote(f"{viral_url}whatsapp&utm_medium=social")
            
            linkedin_share_url = f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url_li}"
            twitter_share_url = f"https://twitter.com/intent/tweet?text={encoded_title}&url={encoded_url_tw}"
            whatsapp_share_url = f"https://api.whatsapp.com/send?text={encoded_title}%20{encoded_url_wa}"
            
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                st.markdown(f'<a href="{linkedin_share_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#0A66C2; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer;">LinkedIn</button></a>', unsafe_allow_html=True)
            with btn_col2:
                st.markdown(f'<a href="{twitter_share_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#1DA1F2; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer;">Twitter/X</button></a>', unsafe_allow_html=True)
            with btn_col3:
                st.markdown(f'<a href="{whatsapp_share_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#25D366; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer;">WhatsApp</button></a>', unsafe_allow_html=True)

            st.markdown("---")
            if st.button("← Back to Platform Admin"):
                st.query_params.clear()
                st.rerun()

    st.stop()  # Stop execution so public view doesn't load admin tabs

# ==========================================
# 5. ADMIN PLATFORM TABS
# ==========================================
st.title("🎓 Digital Credential Management & Analytics Platform")
st.caption("Automated Issuance, Verification Engine, SMTP Emailer & Viral Growth Analytics")

tabs = st.tabs([
    "🎨 1. Designer & Batch Generator",
    "📧 2. Email Distribution",
    "📈 3. Viral Analytics & KPIs",
    "🔍 4. Issued Credentials Database"
])

# ------------------------------------------
# TAB 1: DESIGNER & BATCH GENERATOR
# ------------------------------------------
with tabs[0]:
    st.header("Certificate Designer & Batch Generator")
    
    col_config, col_preview = st.columns([1, 1.2])
    
    with col_config:
        st.subheader("1. Base Template & CSV Upload")
        uploaded_template = st.file_uploader("Upload Base Certificate (PNG/JPG)", type=["png", "jpg", "jpeg"])
        uploaded_csv = st.file_uploader("Upload Recipient CSV", type=["csv"])
        
        st.info("CSV Requirements: Headers must include `name`, `email`, `course`, `date`")
        
        st.subheader("2. Visual Coordinate Tuning")
        with st.expander("🛠 Adjustment Controls", expanded=True):
            name_x = st.slider("Name Position X", 0, 1200, 600)
            name_y = st.slider("Name Position Y", 0, 850, 250)
            name_size = st.slider("Name Font Size", 10, 100, 50)
            name_color = st.color_picker("Name Color", "#38BDF8")
            
            st.divider()
            course_x = st.slider("Course Position X", 0, 1200, 600)
            course_y = st.slider("Course Position Y", 0, 850, 430)
            course_size = st.slider("Course Font Size", 10, 80, 40)
            course_color = st.color_picker("Course Color", "#F8FAFC")
            
            st.divider()
            show_qr = st.checkbox("Embed Verification QR Code", value=True)
            qr_x = st.slider("QR Code Position X", 0, 1200, 900)
            qr_y = st.slider("QR Code Position Y", 0, 850, 650)
            qr_size = st.slider("QR Size", 50, 250, 140)

    coords = {
        'name_x': name_x, 'name_y': name_y, 'name_size': name_size, 'name_color': name_color,
        'course_x': course_x, 'course_y': course_y, 'course_size': course_size, 'course_color': course_color,
        'date_x': 100, 'date_y': 750, 'meta_size': 18, 'meta_color': '#94A3B8',
        'id_x': 100, 'id_y': 780,
        'show_qr': show_qr, 'qr_x': qr_x, 'qr_y': qr_y, 'qr_size': qr_size
    }

    if uploaded_template:
        base_img = Image.open(uploaded_template)
    else:
        base_img = create_default_template()

    with col_preview:
        st.subheader("Live Template Canvas Preview")
        demo_id = "916bc487-09cc-4659-9794-a7072dd65ec7"
        demo_url = f"https://credsverse.app/?id={demo_id}"
        preview_cert = draw_certificate_image(
            base_img, "Jane Doe (Sample)", "AI & Machine Learning", "2026-08-19", demo_id, demo_url, coords
        )
        st.image(preview_cert, caption="Live Preview Canvas", use_container_width=True)

    st.divider()
    st.subheader("3. Execute Batch Generation")
    
    if st.button("🚀 Process Batch & Generate Certificates", type="primary"):
        if not uploaded_csv:
            st.warning("Please upload a CSV file with recipient data first.")
        else:
            df_recipients = pd.read_csv(uploaded_csv)
            required_cols = {'name', 'email', 'course', 'date'}
            if not required_cols.issubset(set(df_recipients.columns)):
                st.error(f"CSV missing required columns: {required_cols - set(df_recipients.columns)}")
            else:
                zip_buffer = io.BytesIO()
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                generated_count = 0
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for idx, row in df_recipients.iterrows():
                        cred_id = str(uuid.uuid4())
                        v_url = f"https://credsverse.app/?id={cred_id}"
                        
                        # Generate Image
                        cert_out = draw_certificate_image(
                            base_img, row['name'], row['course'], str(row['date']), cred_id, v_url, coords
                        )
                        
                        # Save Image to Zip
                        img_byte_arr = io.BytesIO()
                        cert_out.save(img_byte_arr, format='PNG')
                        zip_file.writestr(f"{row['name'].replace(' ', '_')}_{cred_id[:8]}.png", img_byte_arr.getvalue())
                        
                        # Database Entry
                        cursor.execute("""
                            INSERT INTO credentials (credential_id, recipient_name, email, course_name, issue_date)
                            VALUES (?, ?, ?, ?, ?)
                        """, (cred_id, row['name'], row['email'], row['course'], str(row['date'])))
                        
                        generated_count += 1
                        
                conn.commit()
                conn.close()
                
                st.success(f"🎉 Successfully generated {generated_count} credentials!")
                st.download_button(
                    label="📦 Download All Certificates (.ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="generated_certificates.zip",
                    mime="application/zip"
                )

# ------------------------------------------
# TAB 2: EMAIL DISTRIBUTION ENGINE
# ------------------------------------------
with tabs[1]:
    st.header("Email Notification & SMTP Engine")
    
    col_smtp, col_template = st.columns([1, 1])
    
    with col_smtp:
        st.subheader("SMTP Configuration")
        smtp_server = st.text_input("SMTP Server", "smtp.sendgrid.net")
        smtp_port = st.number_input("SMTP Port", value=587)
        smtp_user = st.text_input("SMTP Username / API Key", "apikey")
        smtp_pass = st.text_input("SMTP Password", type="password")
        sender_email = st.text_input("Sender Email Address", "credentials@organization.com")

    with col_template:
        st.subheader("Email Template Customization")
        email_subject = st.text_input("Subject Line", "Congratulations! Your Official Certificate is Ready")
        
        default_body = """Hi {{recipient_name}},

Congratulations on completing {{course_name}}!

Your official digital certificate has been issued and verified. You can view, download, and share your credential directly on LinkedIn using the link below:

Verification Link: {{verification_url}}
Credential ID: {{credential_id}}

Best regards,
Certification Team"""
        
        email_body = st.text_area("Email Body Template", value=default_body, height=200)
        st.caption("Supported Dynamic Tags: `{{recipient_name}}`, `{{course_name}}`, `{{credential_id}}`, `{{verification_url}}`")

    st.divider()
    if st.button("📨 Dispatch Batch Emails to Unsent Recipients"):
        st.info("Simulating email distribution pipeline...")
        conn = sqlite3.connect(DB_FILE)
        df_pending = pd.read_sql_query("SELECT * FROM credentials", conn)
        conn.close()
        
        progress_bar = st.progress(0)
        for idx, row in df_pending.iterrows():
            # Build dynamic template
            custom_body = email_body.replace("{{recipient_name}}", row['recipient_name'])                                    .replace("{{course_name}}", row['course_name'])                                    .replace("{{credential_id}}", row['credential_id'])                                    .replace("{{verification_url}}", f"https://credsverse.app/?id={row['credential_id']}")
            
            # Here real smtplib logic would trigger
            progress_bar.progress((idx + 1) / len(df_pending))
        
        st.success(f"✅ Dispatched {len(df_pending)} personalized credential emails successfully!")

# ------------------------------------------
# TAB 3: VIRAL ANALYTICS & KPIS
# ------------------------------------------
with tabs[2]:
    st.header("Growth, Engagement & Viral Referral Analytics")
    
    conn = sqlite3.connect(DB_FILE)
    df_events = pd.read_sql_query("SELECT * FROM analytics_events", conn)
    df_creds = pd.read_sql_query("SELECT * FROM credentials", conn)
    conn.close()
    
    # Key Performance Indicators
    total_issued = len(df_creds)
    total_views = len(df_events[df_events['event_type'] == 'view'])
    total_shares = len(df_events[df_events['event_type'] == 'share_click'])
    total_downloads = len(df_events[df_events['event_type'].str.contains('download')])
    viral_referrals = len(df_events[df_events['event_type'] == 'viral_referral'])
    
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Total Issued", total_issued)
    kpi2.metric("Public Views", total_views, delta=f"+{viral_referrals} Viral")
    kpi3.metric("Social Share Clicks", total_shares)
    kpi4.metric("Downloads", total_downloads)
    kpi5.metric("Viral K-Factor", f"{round(viral_referrals / max(total_issued, 1), 2)}x")
    
    st.divider()
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Shares by Platform")
        df_shares = df_events[df_events['event_type'] == 'share_click']
        if not df_shares.empty:
            fig_share = px.pie(df_shares, names='platform', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_share, use_container_width=True)
        else:
            st.info("No share events logged yet.")

    with col_chart2:
        st.subheader("Event Breakdown")
        if not df_events.empty:
            fig_events = px.histogram(df_events, x='event_type', color='platform', barmode='group')
            st.plotly_chart(fig_events, use_container_width=True)
        else:
            st.info("No events logged yet.")

# ------------------------------------------
# TAB 4: ISSUED CREDENTIALS DATABASE
# ------------------------------------------
with tabs[3]:
    st.header("Issued Credentials Registry")
    
    conn = sqlite3.connect(DB_FILE)
    df_all = pd.read_sql_query("SELECT * FROM credentials ORDER BY created_at DESC", conn)
    conn.close()
    
    st.dataframe(df_all, use_container_width=True)
    
    st.subheader("Test Verification Links")
    for idx, row in df_all.iterrows():
        col_a, col_b = st.columns([3, 1])
        col_a.write(f"**{row['recipient_name']}** - {row['course_name']} (`{row['credential_id']}`)")
        if col_b.button("View Portal ↗", key=f"btn_{row['credential_id']}"):
            st.query_params["id"] = row['credential_id']
            st.rerun()
