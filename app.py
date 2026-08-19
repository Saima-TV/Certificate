"""
Digital Credential Issuance, Verification & Analytics Platform
Built with Streamlit, Pillow, SQLite, and Plotly
Fully Editable Certificate Elements Engine
"""

import streamlit as st
import sqlite3
import uuid
import io
import zipfile
import urllib.parse
import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import qrcode
import plotly.express as px

# ==========================================
# 1. DATABASE SETUP & INITIALIZATION
# ==========================================
DB_FILE = "credentials.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credential_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            platform TEXT,
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

def seed_dummy_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM credentials")
    count = cursor.fetchone()[0]
    
    if count == 0:
        dummy_creds = [
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "Saima Gul", "saima@example.com", "AI Bootcamp 17", "2026-08-17", "VALID"),
            ("812ab341-12cd-4123-8821-b6072dd54fa1", "Alex Chen", "alex@example.com", "Data Science Masters", "2026-07-20", "VALID")
        ]
        cursor.executemany("""
            INSERT INTO credentials (credential_id, recipient_name, email, course_name, issue_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, dummy_creds)
        
        events = [
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "view", "direct", "", ""),
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "share_click", "linkedin", "", ""),
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "download_pdf", "direct", "", "")
        ]
        cursor.executemany("""
            INSERT INTO analytics_events (credential_id, event_type, platform, utm_source, utm_medium)
            VALUES (?, ?, ?, ?, ?)
        """, events)
        
        conn.commit()
    conn.close()

# ==========================================
# 2. HELPER UTILITIES & DRAWING ENGINE
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
    return qr.make_image(fill_color="black", back_color="white")

def create_default_template():
    img = Image.new("RGB", (1200, 850), color="#0F172A")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 1180, 830], outline="#CBD5E1", width=4)
    draw.rectangle([35, 35, 1165, 815], outline="#38BDF8", width=2)
    return img

def render_dynamic_certificate(base_img, r_name, c_name, i_date, c_id, v_url, elem_cfg):
    """
    Renders fully customizable certificate elements based on user coordinates and configs.
    """
    img = base_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)

    def get_font(size):
        try:
            return ImageFont.truetype("arial.ttf", size)
        except IOError:
            return ImageFont.load_default()

    # Render Title / Header
    if elem_cfg['title']['show']:
        font = get_font(elem_cfg['title']['size'])
        draw.text(
            (elem_cfg['title']['x'], elem_cfg['title']['y']),
            elem_cfg['title']['text'],
            fill=elem_cfg['title']['color'],
            font=font
        )

    # Render Recipient Name
    if elem_cfg['name']['show']:
        font = get_font(elem_cfg['name']['size'])
        draw.text(
            (elem_cfg['name']['x'], elem_cfg['name']['y']),
            r_name,
            fill=elem_cfg['name']['color'],
            font=font
        )

    # Render Course Title
    if elem_cfg['course']['show']:
        font = get_font(elem_cfg['course']['size'])
        draw.text(
            (elem_cfg['course']['x'], elem_cfg['course']['y']),
            f"{elem_cfg['course']['prefix']} {c_name}",
            fill=elem_cfg['course']['color'],
            font=font
        )

    # Render Issue Date
    if elem_cfg['date']['show']:
        font = get_font(elem_cfg['date']['size'])
        draw.text(
            (elem_cfg['date']['x'], elem_cfg['date']['y']),
            f"{elem_cfg['date']['prefix']} {i_date}",
            fill=elem_cfg['date']['color'],
            font=font
        )

    # Render Credential ID
    if elem_cfg['id']['show']:
        font = get_font(elem_cfg['id']['size'])
        draw.text(
            (elem_cfg['id']['x'], elem_cfg['id']['y']),
            f"{elem_cfg['id']['prefix']} {c_id}",
            fill=elem_cfg['id']['color'],
            font=font
        )

    # Render QR Code
    if elem_cfg['qr']['show']:
        qr_img = generate_qr_code(v_url)
        qr_img = qr_img.resize((elem_cfg['qr']['size'], elem_cfg['qr']['size']))
        img.paste(qr_img, (elem_cfg['qr']['x'], elem_cfg['qr']['y']))

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

query_params = st.query_params
target_id = query_params.get("id", None)
utm_source = query_params.get("utm_source", "")
utm_medium = query_params.get("utm_medium", "")

# ==========================================
# 4. PUBLIC VERIFICATION PORTAL (?id=UUID)
# ==========================================
if target_id:
    log_event(target_id, "view", platform=utm_source if utm_source else "direct", utm_source=utm_source, utm_medium=utm_medium)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT credential_id, recipient_name, email, course_name, issue_date, status FROM credentials WHERE credential_id=?", (target_id,))
    record = cursor.fetchone()
    conn.close()

    st.markdown("<h2 style='text-align: center; color: #38BDF8;'>🎓 Digital Credential Verification</h2>", unsafe_allow_html=True)
    
    if not record:
        st.error(f"❌ Invalid Credential ID: `{target_id}`. No verification record found.")
    else:
        c_id, r_name, r_email, c_name, i_date, c_status = record
        st.success(f"✅ **AUTHENTIC CREDENTIAL VERIFIED** | Issued to **{r_name}**")
        
        col_cert, col_meta = st.columns([1.6, 1])
        
        base_template = create_default_template()
        v_url = f"https://credsverse.app/?id={c_id}"
        
        # Default fallback view specs
        default_cfg = {
            'title': {'show': True, 'text': 'CERTIFICATE OF ACHIEVEMENT', 'x': 320, 'y': 100, 'size': 40, 'color': '#F8FAFC'},
            'name': {'show': True, 'x': 450, 'y': 280, 'size': 50, 'color': '#38BDF8'},
            'course': {'show': True, 'prefix': 'For completing:', 'x': 420, 'y': 420, 'size': 35, 'color': '#F8FAFC'},
            'date': {'show': True, 'prefix': 'Issued Date:', 'x': 100, 'y': 720, 'size': 18, 'color': '#94A3B8'},
            'id': {'show': True, 'prefix': 'Credential ID:', 'x': 100, 'y': 750, 'size': 18, 'color': '#94A3B8'},
            'qr': {'show': True, 'x': 950, 'y': 640, 'size': 140}
        }
        
        cert_img = render_dynamic_certificate(base_template, r_name, c_name, i_date, c_id, v_url, default_cfg)
        
        with col_cert:
            st.image(cert_img, caption=f"Verified Certificate - {c_id}", use_container_width=True)
            
            img_buf = io.BytesIO()
            cert_img.save(img_buf, format="PNG")
            
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                if st.download_button("⬇️ Download PNG", data=img_buf.getvalue(), file_name=f"{r_name}_certificate.png", mime="image/png"):
                    log_event(c_id, "download_png")
            with d_col2:
                pdf_buf = io.BytesIO()
                cert_img.save(pdf_buf, format="PDF", resolution=100.0)
                if st.download_button("📄 Download PDF", data=pdf_buf.getvalue(), file_name=f"{r_name}_certificate.pdf", mime="application/pdf"):
                    log_event(c_id, "download_pdf")

        with col_meta:
            st.markdown("### Credential Metadata")
            st.markdown(f"**Recipient Name:** {r_name}")
            st.markdown(f"**Course / Award:** {c_name}")
            st.markdown(f"**Issue Date:** {i_date}")
            st.markdown(f"**Credential ID:** `{c_id}`")
            st.markdown(f"**Status:** `:green[{c_status}]`")
            st.markdown("---")
            
            st.markdown("### 🚀 Share Your Achievement")
            viral_url = f"{v_url}&utm_source="
            encoded_title = urllib.parse.quote(f"Check out my official credential for {c_name}!")
            encoded_url_li = urllib.parse.quote(f"{viral_url}linkedin&utm_medium=social")
            
            linkedin_share_url = f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url_li}"
            st.markdown(f'<a href="{linkedin_share_url}" target="_blank"><button style="width:100%; background-color:#0A66C2; color:white; border:none; padding:10px; border-radius:5px; cursor:pointer;">Share on LinkedIn</button></a>', unsafe_allow_html=True)

            st.markdown("---")
            if st.button("← Back to Admin Panel"):
                st.query_params.clear()
                st.rerun()

    st.stop()

# ==========================================
# 5. ADMIN PLATFORM ENGINE
# ==========================================
st.title("🎓 Digital Credential Management Engine")

tabs = st.tabs([
    "🎨 1. Fully Editable Designer & Generator",
    "📧 2. Email Distribution",
    "📈 3. Analytics Dashboard",
    "🔍 4. Credentials Registry"
])

# ------------------------------------------
# TAB 1: FULLY EDITABLE DESIGNER
# ------------------------------------------
with tabs[0]:
    st.header("Fully Editable Certificate Designer")
    st.caption("Upload a template or use default. Toggle, re-position, resize, and edit text for every element independently.")
    
    col_controls, col_canvas = st.columns([1.1, 1.3])
    
    with col_controls:
        st.subheader("1. Template & Data Source")
        uploaded_template = st.file_uploader("Upload Certificate Base (PNG/JPG)", type=["png", "jpg", "jpeg"])
        uploaded_csv = st.file_uploader("Upload Recipient CSV", type=["csv"])
        st.info("CSV header requirement: `name`, `email`, `course`, `date`")
        
        st.subheader("2. Element Editing Controls")
        
        # Header / Title Element Controls
        with st.expander("📝 1. Certificate Title / Header", expanded=False):
            title_show = st.checkbox("Show Header", value=True)
            title_text = st.text_input("Header Text", value="CERTIFICATE OF ACHIEVEMENT")
            title_x = st.slider("Header X Position", 0, 1200, 320, key="tx")
            title_y = st.slider("Header Y Position", 0, 850, 100, key="ty")
            title_size = st.slider("Header Font Size", 10, 80, 40, key="ts")
            title_color = st.color_picker("Header Color", "#F8FAFC", key="tc")

        # Name Element Controls
        with st.expander("👤 2. Recipient Name", expanded=True):
            name_show = st.checkbox("Show Name", value=True)
            name_x = st.slider("Name X Position", 0, 1200, 450, key="nx")
            name_y = st.slider("Name Y Position", 0, 850, 280, key="ny")
            name_size = st.slider("Name Font Size", 10, 100, 50, key="ns")
            name_color = st.color_picker("Name Color", "#38BDF8", key="nc")

        # Course Element Controls
        with st.expander("📚 3. Course / Award Name", expanded=False):
            course_show = st.checkbox("Show Course", value=True)
            course_prefix = st.text_input("Course Prefix Label", value="For successfully completing:")
            course_x = st.slider("Course X Position", 0, 1200, 380, key="cx")
            course_y = st.slider("Course Y Position", 0, 850, 420, key="cy")
            course_size = st.slider("Course Font Size", 10, 80, 35, key="cs")
            course_color = st.color_picker("Course Color", "#F8FAFC", key="cc")

        # Issue Date Controls
        with st.expander("📅 4. Issue Date", expanded=False):
            date_show = st.checkbox("Show Issue Date", value=True)
            date_prefix = st.text_input("Date Label Prefix", value="Issued Date:")
            date_x = st.slider("Date X Position", 0, 1200, 100, key="dx")
            date_y = st.slider("Date Y Position", 0, 850, 720, key="dy")
            date_size = st.slider("Date Font Size", 10, 50, 18, key="ds")
            date_color = st.color_picker("Date Color", "#94A3B8", key="dc")

        # Credential ID Controls
        with st.expander("🔑 5. Credential ID", expanded=False):
            id_show = st.checkbox("Show Credential ID", value=True)
            id_prefix = st.text_input("ID Label Prefix", value="Credential ID:")
            id_x = st.slider("ID X Position", 0, 1200, 100, key="ix")
            id_y = st.slider("ID Y Position", 0, 850, 750, key="iy")
            id_size = st.slider("ID Font Size", 10, 50, 18, key="is")
            id_color = st.color_picker("ID Color", "#94A3B8", key="ic")

        # QR Code Controls
        with st.expander("📱 6. Verification QR Code", expanded=False):
            qr_show = st.checkbox("Embed QR Code", value=True)
            qr_x = st.slider("QR Code X Position", 0, 1200, 950, key="qx")
            qr_y = st.slider("QR Code Y Position", 0, 850, 640, key="qy")
            qr_size = st.slider("QR Dimension Size", 50, 250, 140, key="qs")

    # Dynamic Element Configuration Dictionary
    elem_cfg = {
        'title': {'show': title_show, 'text': title_text, 'x': title_x, 'y': title_y, 'size': title_size, 'color': title_color},
        'name': {'show': name_show, 'x': name_x, 'y': name_y, 'size': name_size, 'color': name_color},
        'course': {'show': course_show, 'prefix': course_prefix, 'x': course_x, 'y': course_y, 'size': course_size, 'color': course_color},
        'date': {'show': date_show, 'prefix': date_prefix, 'x': date_x, 'y': date_y, 'size': date_size, 'color': date_color},
        'id': {'show': id_show, 'prefix': id_prefix, 'x': id_x, 'y': id_y, 'size': id_size, 'color': id_color},
        'qr': {'show': qr_show, 'x': qr_x, 'y': qr_y, 'size': qr_size}
    }

    if uploaded_template:
        base_img = Image.open(uploaded_template)
    else:
        base_img = create_default_template()

    with col_canvas:
        st.subheader("Interactive Canvas Preview")
        preview_id = "916bc487-09cc-4659-9794-a7072dd65ec7"
        preview_url = f"https://credsverse.app/?id={preview_id}"
        
        preview_cert = render_dynamic_certificate(
            base_img, "Jane Doe (Sample)", "AI & Machine Learning", "2026-08-19", preview_id, preview_url, elem_cfg
        )
        st.image(preview_cert, caption="Live Render Output", use_container_width=True)

    st.divider()
    
    if st.button("🚀 Process & Generate Batch Certificates", type="primary"):
        if not uploaded_csv:
            st.warning("Please upload a recipient CSV file to execute batch generation.")
        else:
            df_recipients = pd.read_csv(uploaded_csv)
            zip_buffer = io.BytesIO()
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            count = 0
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for idx, row in df_recipients.iterrows():
                    cred_id = str(uuid.uuid4())
                    v_url = f"https://credsverse.app/?id={cred_id}"
                    
                    cert_out = render_dynamic_certificate(
                        base_img, row['name'], row['course'], str(row['date']), cred_id, v_url, elem_cfg
                    )
                    
                    img_byte_arr = io.BytesIO()
                    cert_out.save(img_byte_arr, format='PNG')
                    zip_file.writestr(f"{row['name'].replace(' ', '_')}_{cred_id[:8]}.png", img_byte_arr.getvalue())
                    
                    cursor.execute("""
                        INSERT INTO credentials (credential_id, recipient_name, email, course_name, issue_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (cred_id, row['name'], row['email'], row['course'], str(row['date'])))
                    count += 1
                    
            conn.commit()
            conn.close()
            
            st.success(f"🎉 Successfully generated {count} custom credentials!")
            st.download_button("📦 Download Certificates ZIP Archive", data=zip_buffer.getvalue(), file_name="certificates.zip", mime="application/zip")

# ------------------------------------------
# TAB 2: EMAIL DISTRIBUTION
# ------------------------------------------
with tabs[1]:
    st.header("Email Distribution Engine")
    
    col_smtp, col_template = st.columns([1, 1])
    with col_smtp:
        st.subheader("SMTP Configuration")
        st.text_input("SMTP Server", "smtp.sendgrid.net")
        st.number_input("SMTP Port", value=587)
        st.text_input("Sender Email", "credentials@organization.com")
        
    with col_template:
        st.subheader("Email Template Customization")
        st.text_input("Subject", "Your Official Digital Certificate is Ready")
        st.text_area("Email Body", value="Hi {{recipient_name}},\n\nYour certificate for {{course_name}} is ready.\n\nVerify and view here: {{verification_url}}", height=150)

# ------------------------------------------
# TAB 3: ANALYTICS
# ------------------------------------------
with tabs[2]:
    st.header("Analytics & Viral K-Factor Dashboard")
    conn = sqlite3.connect(DB_FILE)
    df_events = pd.read_sql_query("SELECT * FROM analytics_events", conn)
    df_creds = pd.read_sql_query("SELECT * FROM credentials", conn)
    conn.close()
    
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Issued", len(df_creds))
    kpi2.metric("Total Views", len(df_events[df_events['event_type'] == 'view']))
    kpi3.metric("Shares Captured", len(df_events[df_events['event_type'] == 'share_click']))

# ------------------------------------------
# TAB 4: CREDENTIALS REGISTRY
# ------------------------------------------
with tabs[3]:
    st.header("Issued Credentials Registry")
    conn = sqlite3.connect(DB_FILE)
    df_all = pd.read_sql_query("SELECT * FROM credentials ORDER BY created_at DESC", conn)
    conn.close()
    
    st.dataframe(df_all, use_container_width=True)
    
    st.subheader("Launch Verification Portal")
    for idx, row in df_all.iterrows():
        c1, c2 = st.columns([3, 1])
        c1.write(f"**{row['recipient_name']}** - {row['course_name']} (`{row['credential_id']}`)")
        if c2.button("Open Portal ↗", key=f"v_{row['credential_id']}"):
            st.query_params["id"] = row['credential_id']
            st.rerun()
