"""
Digital Credential Issuance, Verification & Analytics Platform
Built with Streamlit, Pillow, SQLite, and Plotly
Post-Processing Email Template Editor & Dynamic Email Dispatcher
"""

import streamlit as st
import sqlite3
import uuid
import io
import zipfile
import urllib.parse
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
            ("916bc487-09cc-4659-9794-a7072dd65ec7", "Saima Gul", "saima@example.com", "Mental Health First Aid Standard", "2026-08-19", "VALID"),
            ("812ab341-12cd-4123-8821-b6072dd54fa1", "Alex Chen", "alex@example.com", "AI Bootcamp 17", "2026-08-17", "VALID")
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
# 2. DRAWING & FONT SCALING ENGINE
# ==========================================
def generate_qr_code(verification_url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=1,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

def create_default_template(style="Classic Blue"):
    if style == "Classic Blue":
        img = Image.new("RGB", (1200, 850), color="#FFFFFF")
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 1180, 830], outline="#1E3A8A", width=8)
        draw.rectangle([35, 35, 1165, 815], outline="#3B82F6", width=2)
    elif style == "Elegant Gold":
        img = Image.new("RGB", (1200, 850), color="#FFFDF0")
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 1180, 830], outline="#D97706", width=8)
        draw.rectangle([35, 35, 1165, 815], outline="#F59E0B", width=2)
    else:  # Modern Dark
        img = Image.new("RGB", (1200, 850), color="#0F172A")
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 1180, 830], outline="#CBD5E1", width=4)
        draw.rectangle([35, 35, 1165, 815], outline="#38BDF8", width=2)
    return img

def render_dynamic_certificate(base_img, r_name, c_name, i_date, c_id, v_url, elem_cfg):
    """
    Renders certificate elements onto canvas with accurate pixel font scaling.
    """
    img = base_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)

    def get_font(size_px):
        try:
            return ImageFont.truetype("arial.ttf", size_px)
        except IOError:
            try:
                return ImageFont.load_default(size=size_px)
            except TypeError:
                return ImageFont.load_default()

    # 1. Header / Title
    if elem_cfg['title']['show']:
        font = get_font(elem_cfg['title']['size'])
        draw.text((elem_cfg['title']['x'], elem_cfg['title']['y']), elem_cfg['title']['text'], fill=elem_cfg['title']['color'], font=font)

    # 2. Issuer / Organization Name
    if elem_cfg['issuer']['show']:
        font = get_font(elem_cfg['issuer']['size'])
        draw.text((elem_cfg['issuer']['x'], elem_cfg['issuer']['y']), elem_cfg['issuer']['text'], fill=elem_cfg['issuer']['color'], font=font)

    # 3. Recipient Name Tag
    if elem_cfg['name']['show']:
        font = get_font(elem_cfg['name']['size'])
        display_name = f"[{r_name}]" if elem_cfg['name']['placeholders'] else r_name
        draw.text((elem_cfg['name']['x'], elem_cfg['name']['y']), display_name, fill=elem_cfg['name']['color'], font=font)

    # 4. Course Tag
    if elem_cfg['course']['show']:
        font = get_font(elem_cfg['course']['size'])
        draw.text((elem_cfg['course']['x'], elem_cfg['course']['y']), f"{elem_cfg['course']['prefix']} {c_name}", fill=elem_cfg['course']['color'], font=font)

    # 5. Description Body
    if elem_cfg['desc']['show']:
        font = get_font(elem_cfg['desc']['size'])
        draw.text((elem_cfg['desc']['x'], elem_cfg['desc']['y']), elem_cfg['desc']['text'], fill=elem_cfg['desc']['color'], font=font)

    # 6. Issue Date
    if elem_cfg['date']['show']:
        font = get_font(elem_cfg['date']['size'])
        draw.text((elem_cfg['date']['x'], elem_cfg['date']['y']), f"{elem_cfg['date']['prefix']} {i_date}", fill=elem_cfg['date']['color'], font=font)

    # 7. Credential ID
    if elem_cfg['id']['show']:
        font = get_font(elem_cfg['id']['size'])
        display_id = f"[certificate.uuid]" if elem_cfg['id']['placeholders'] else c_id
        draw.text((elem_cfg['id']['x'], elem_cfg['id']['y']), f"{elem_cfg['id']['prefix']} {display_id}", fill=elem_cfg['id']['color'], font=font)

    # 8. Verification QR Code
    if elem_cfg['qr']['show']:
        qr_img = generate_qr_code(v_url)
        qr_img = qr_img.resize((elem_cfg['qr']['size'], elem_cfg['qr']['size']))
        img.paste(qr_img, (elem_cfg['qr']['x'], elem_cfg['qr']['y']))
        
        if elem_cfg['qr']['label']:
            font_qr = get_font(max(12, int(elem_cfg['qr']['size'] * 0.1)))
            draw.text((elem_cfg['qr']['x'], elem_cfg['qr']['y'] - 18), "Verification:", fill="#475569", font=font_qr)

    return img

def send_custom_batch_emails(df_recipients, custom_subject, custom_body_template):
    """
    Helper to dispatch customized email notifications via SMTP to CSV recipients.
    """
    app_password = None
    if hasattr(st, "secrets") and "GMAIL_APP_PASSWORD" in st.secrets:
        app_password = st.secrets["GMAIL_APP_PASSWORD"]
    else:
        app_password = os.environ.get("GMAIL_APP_PASSWORD")

    sender_email = st.secrets.get("GMAIL_ADDRESS", "your.email@gmail.com") if hasattr(st, "secrets") else "your.email@gmail.com"

    if not app_password:
        st.error("❌ Email password missing! Please set `GMAIL_APP_PASSWORD` in your Streamlit Secrets (`.streamlit/secrets.toml`).")
        return False

    success_count = 0
    progress_bar = st.progress(0)

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, app_password)

        for idx, row in df_recipients.iterrows():
            v_url = f"https://certificate-tv.streamlit.app/?id={row['credential_id']}"
            custom_body = custom_body_template.replace("{{recipient_name}}", str(row['name']))\
                                              .replace("{{course_name}}", str(row['course']))\
                                              .replace("{{credential_id}}", str(row['credential_id']))\
                                              .replace("{{verification_url}}", v_url)

            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = row['email']
            msg['Subject'] = custom_subject
            msg.attach(MIMEText(custom_body, 'plain'))

            server.send_message(msg)
            success_count += 1
            progress_bar.progress((idx + 1) / len(df_recipients))

        server.quit()
        st.success(f"✅ Dispatched {success_count} emails successfully to CSV recipients!")
        return True
    except Exception as e:
        st.error(f"SMTP Error: {e}")
        return False

# ==========================================
# 3. PAGE CONFIG & ROUTING
# ==========================================
st.set_page_config(
    page_title="Digital Credential Engine",
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

    st.markdown("<h2 style='text-align: center; color: #1E3A8A;'>🎓 Digital Credential Verification Portal</h2>", unsafe_allow_html=True)
    
    if not record:
        st.error(f"❌ Invalid Credential ID: `{target_id}`. Verification failed.")
        st.info("Please check the link or contact the issuing organization.")
    else:
        c_id, r_name, r_email, c_name, i_date, c_status = record
        st.success(f"✅ **AUTHENTIC CREDENTIAL VERIFIED** | Issued to **{r_name}**")
        
        col_cert, col_meta = st.columns([1.6, 1])
        
        base_template = create_default_template("Classic Blue")
        v_url = f"https://certificate-tv.streamlit.app/?id={c_id}"
        
        default_cfg = {
            'title': {'show': True, 'text': 'Certificate of Participation', 'x': 250, 'y': 100, 'size': 44, 'color': '#1E3A8A'},
            'issuer': {'show': True, 'text': 'Mental Health First Aid Organization', 'x': 250, 'y': 160, 'size': 20, 'color': '#3B82F6'},
            'name': {'show': True, 'x': 250, 'y': 280, 'size': 48, 'color': '#1E293B', 'placeholders': False},
            'course': {'show': True, 'prefix': 'has completed', 'x': 250, 'y': 380, 'size': 28, 'color': '#0F172A'},
            'desc': {'show': True, 'text': 'Participants learn skills for providing support to individuals in need.', 'x': 250, 'y': 440, 'size': 16, 'color': '#64748B'},
            'date': {'show': True, 'prefix': 'Training Date:', 'x': 100, 'y': 700, 'size': 16, 'color': '#334155'},
            'id': {'show': True, 'prefix': 'Issue Date / ID:', 'x': 400, 'y': 700, 'size': 16, 'color': '#334155', 'placeholders': False},
            'qr': {'show': True, 'x': 980, 'y': 650, 'size': 130, 'label': True}
        }
        
        cert_img = render_dynamic_certificate(base_template, r_name, c_name, i_date, c_id, v_url, default_cfg)
        
        with col_cert:
            st.image(cert_img, caption=f"Verified Digital Certificate (ID: {c_id})", use_container_width=True)
            
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
            st.markdown("### Credential Record")
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
            st.markdown(f'<a href="{linkedin_share_url}" target="_blank"><button style="width:100%; background-color:#0A66C2; color:white; border:none; padding:10px; border-radius:5px; cursor:pointer; font-weight:bold;">Add to LinkedIn Profile</button></a>', unsafe_allow_html=True)

            st.markdown("---")
            if st.button("← Back to Admin Console"):
                st.query_params.clear()
                st.rerun()

    st.stop()

# ==========================================
# 5. ADMIN PLATFORM ENGINE
# ==========================================
st.title("🎓 Digital Credential Management Platform")

tabs = st.tabs([
    "🎨 1. Graphic Designer & Template Engine",
    "📧 2. Email Distribution Engine",
    "📈 3. Analytics Dashboard",
    "🔍 4. Credentials Registry"
])

# ------------------------------------------
# TAB 1: GRAPHIC DESIGNER & TEMPLATE ENGINE
# ------------------------------------------
with tabs[0]:
    defaults = {
        't_show': True, 't_text': 'Certificate of Participation', 't_size': 42, 't_color': '#1E3A8A', 't_x': 200, 't_y': 100,
        'iss_show': True, 'iss_text': 'Mental Health First Aid Organization', 'iss_size': 20, 'iss_color': '#3B82F6',
        'desc_show': True, 'desc_text': 'Participants learn skills for providing initial help to individuals experiencing mental health challenges.', 'desc_size': 15, 'desc_color': '#475569', 'desc_x': 200, 'desc_y': 450,
        'n_show': True, 'n_use_brackets': True, 'n_size': 48, 'n_color': '#0F172A', 'n_x': 200, 'n_y': 280,
        'c_show': True, 'c_prefix': 'has completed', 'c_size': 26, 'c_color': '#1E293B', 'c_x': 200, 'c_y': 380,
        'd_show': True, 'd_prefix': 'Training Date:', 'd_size': 16, 'd_color': '#334155', 'd_x': 80, 'd_y': 700,
        'id_show': True, 'id_use_brackets': True, 'id_prefix': 'Issue Date / ID:', 'id_size': 16, 'id_color': '#334155', 'id_x': 380, 'id_y': 700,
        'qr_show': True, 'qr_size': 130, 'qr_label': True, 'qr_x': 980, 'qr_y': 650,
        'template_style': 'Classic Blue', 'uploaded_bg': None, 'uploaded_csv': None,
        'batch_processed': False, 'batch_zip': None, 'batch_df': None
    }
    
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    col_nav_bar, col_sidebar_menu, col_studio = st.columns([0.7, 2.5, 5.2])

    with col_nav_bar:
        st.markdown("**Tools**")
        nav_tool = st.radio(
            "Nav",
            options=["Templates", "Uploads", "Text", "Attributes", "QR Code", "Layers"],
            label_visibility="collapsed"
        )

    with col_sidebar_menu:
        if nav_tool == "Templates":
            st.subheader("Base Template")
            st.session_state['template_style'] = st.selectbox("Style Preset", ["Classic Blue", "Elegant Gold", "Modern Dark"])

        elif nav_tool == "Uploads":
            st.subheader("Upload Assets")
            st.session_state['uploaded_bg'] = st.file_uploader("Custom Background Image", type=["png", "jpg", "jpeg"])
            st.session_state['uploaded_csv'] = st.file_uploader("Recipients CSV File", type=["csv"])
            st.caption("CSV header schema: `name`, `email`, `course`, `date`")

        elif nav_tool == "Text":
            st.subheader("Text Elements")
            with st.expander("Main Title", expanded=True):
                st.session_state['t_show'] = st.checkbox("Show Title", value=st.session_state['t_show'])
                st.session_state['t_text'] = st.text_input("Title Text", value=st.session_state['t_text'])
                st.session_state['t_size'] = st.number_input("Font Size (px)", 10, 150, st.session_state['t_size'], step=2, key="ts_px")
                st.session_state['t_color'] = st.color_picker("Title Color", st.session_state['t_color'])

            with st.expander("Organization / Issuer"):
                st.session_state['iss_show'] = st.checkbox("Show Issuer", value=st.session_state['iss_show'])
                st.session_state['iss_text'] = st.text_input("Issuer Name", value=st.session_state['iss_text'])
                st.session_state['iss_size'] = st.number_input("Font Size (px)", 10, 100, st.session_state['iss_size'], step=2, key="is_px")
                st.session_state['iss_color'] = st.color_picker("Issuer Color", st.session_state['iss_color'])

            with st.expander("Description Body"):
                st.session_state['desc_show'] = st.checkbox("Show Description", value=st.session_state['desc_show'])
                st.session_state['desc_text'] = st.text_area("Body Text", value=st.session_state['desc_text'])
                st.session_state['desc_size'] = st.number_input("Font Size (px)", 10, 80, st.session_state['desc_size'], step=2, key="ds_px")
                st.session_state['desc_color'] = st.color_picker("Body Color", st.session_state['desc_color'])

        elif nav_tool == "Attributes":
            st.subheader("Dynamic Attributes")
            with st.expander("Recipient Name", expanded=True):
                st.session_state['n_show'] = st.checkbox("Show Name", value=st.session_state['n_show'])
                st.session_state['n_use_brackets'] = st.checkbox("Preview as [recipient.name]", value=st.session_state['n_use_brackets'])
                st.session_state['n_size'] = st.number_input("Font Size (px)", 10, 150, st.session_state['n_size'], step=2, key="ns_px")
                st.session_state['n_color'] = st.color_picker("Name Color", st.session_state['n_color'])

            with st.expander("Editable Course Title", expanded=True):
                st.session_state['c_show'] = st.checkbox("Show Course", value=st.session_state['c_show'])
                st.session_state['c_prefix'] = st.text_input("Label Prefix", value=st.session_state['c_prefix'])
                st.session_state['c_size'] = st.number_input("Font Size (px)", 10, 100, st.session_state['c_size'], step=2, key="cs_px")
                st.session_state['c_color'] = st.color_picker("Course Color", st.session_state['c_color'])

            with st.expander("Training Date"):
                st.session_state['d_show'] = st.checkbox("Show Date", value=st.session_state['d_show'])
                st.session_state['d_prefix'] = st.text_input("Date Prefix", value=st.session_state['d_prefix'])
                st.session_state['d_size'] = st.number_input("Font Size (px)", 10, 80, st.session_state['d_size'], step=2, key="dt_px")
                st.session_state['d_color'] = st.color_picker("Date Color", st.session_state['d_color'])

            with st.expander("Credential ID (UUID)"):
                st.session_state['id_show'] = st.checkbox("Show Credential ID", value=st.session_state['id_show'])
                st.session_state['id_use_brackets'] = st.checkbox("Preview as [certificate.uuid]", value=st.session_state['id_use_brackets'])
                st.session_state['id_prefix'] = st.text_input("ID Prefix", value=st.session_state['id_prefix'])
                st.session_state['id_size'] = st.number_input("Font Size (px)", 10, 80, st.session_state['id_size'], step=2, key="ids_px")
                st.session_state['id_color'] = st.color_picker("ID Color", st.session_state['id_color'])

        elif nav_tool == "QR Code":
            st.subheader("Verification QR Code")
            st.session_state['qr_show'] = st.checkbox("Embed QR Code", value=st.session_state['qr_show'])
            st.info("🔗 **Auto-Generated QR Link**: Encodes the dynamic `credential_id` verification portal URL directly onto each certificate.")
            st.session_state['qr_size'] = st.number_input("QR Size (px)", 50, 300, st.session_state['qr_size'], step=5, key="qrs_px")
            st.session_state['qr_label'] = st.checkbox("Show 'Verification:' Label", value=st.session_state['qr_label'])

        elif nav_tool == "Layers":
            st.subheader("Canvas Coordinates")
            st.caption("Adjust X and Y positions on 1200 x 850 canvas")
            st.session_state['t_x'], st.session_state['t_y'] = st.slider("Title (X, Y)", 0, 1200, st.session_state['t_x']), st.slider("Title Y", 0, 850, st.session_state['t_y'])
            st.session_state['n_x'], st.session_state['n_y'] = st.slider("Name (X, Y)", 0, 1200, st.session_state['n_x']), st.slider("Name Y", 0, 850, st.session_state['n_y'])
            st.session_state['c_x'], st.session_state['c_y'] = st.slider("Course (X, Y)", 0, 1200, st.session_state['c_x']), st.slider("Course Y", 0, 850, st.session_state['c_y'])
            st.session_state['desc_x'], st.session_state['desc_y'] = st.slider("Description (X, Y)", 0, 1200, st.session_state['desc_x']), st.slider("Description Y", 0, 850, st.session_state['desc_y'])
            st.session_state['d_x'], st.session_state['d_y'] = st.slider("Date (X, Y)", 0, 1200, st.session_state['d_x']), st.slider("Date Y", 0, 850, st.session_state['d_y'])
            st.session_state['id_x'], st.session_state['id_y'] = st.slider("ID (X, Y)", 0, 1200, st.session_state['id_x']), st.slider("ID Y", 0, 850, st.session_state['id_y'])
            st.session_state['qr_x'], st.session_state['qr_y'] = st.slider("QR Code (X, Y)", 0, 1200, st.session_state['qr_x']), st.slider("QR Code Y", 0, 850, st.session_state['qr_y'])

    # Build config dynamically from state
    elem_cfg = {
        'title': {'show': st.session_state['t_show'], 'text': st.session_state['t_text'], 'x': st.session_state['t_x'], 'y': st.session_state['t_y'], 'size': st.session_state['t_size'], 'color': st.session_state['t_color']},
        'issuer': {'show': st.session_state['iss_show'], 'text': st.session_state['iss_text'], 'x': st.session_state['t_x'], 'y': st.session_state['t_y'] + 55, 'size': st.session_state['iss_size'], 'color': st.session_state['iss_color']},
        'name': {'show': st.session_state['n_show'], 'x': st.session_state['n_x'], 'y': st.session_state['n_y'], 'size': st.session_state['n_size'], 'color': st.session_state['n_color'], 'placeholders': st.session_state['n_use_brackets']},
        'course': {'show': st.session_state['c_show'], 'prefix': st.session_state['c_prefix'], 'x': st.session_state['c_x'], 'y': st.session_state['c_y'], 'size': st.session_state['c_size'], 'color': st.session_state['c_color']},
        'desc': {'show': st.session_state['desc_show'], 'text': st.session_state['desc_text'], 'x': st.session_state['desc_x'], 'y': st.session_state['desc_y'], 'size': st.session_state['desc_size'], 'color': st.session_state['desc_color']},
        'date': {'show': st.session_state['d_show'], 'prefix': st.session_state['d_prefix'], 'x': st.session_state['d_x'], 'y': st.session_state['d_y'], 'size': st.session_state['d_size'], 'color': st.session_state['d_color']},
        'id': {'show': st.session_state['id_show'], 'prefix': st.session_state['id_prefix'], 'x': st.session_state['id_x'], 'y': st.session_state['id_y'], 'size': st.session_state['id_size'], 'color': st.session_state['id_color'], 'placeholders': st.session_state['id_use_brackets']},
        'qr': {'show': st.session_state['qr_show'], 'x': st.session_state['qr_x'], 'y': st.session_state['qr_y'], 'size': st.session_state['qr_size'], 'label': st.session_state['qr_label']}
    }

    with col_studio:
        st.subheader("🎨 Studio Live Canvas Preview")

        if st.session_state['uploaded_bg']:
            base_img = Image.open(st.session_state['uploaded_bg'])
        else:
            base_img = create_default_template(st.session_state['template_style'])

        sample_uuid = "916bc487-09cc-4659-9794-a7072dd65ec7"
        sample_v_url = f"https://certificate-tv.streamlit.app/?id={sample_uuid}"

        preview_canvas = render_dynamic_certificate(
            base_img,
            "recipient.name",
            "Mental Health First Aid Standard (Virtual)",
            "August 19, 2026",
            sample_uuid,
            sample_v_url,
            elem_cfg
        )
        st.image(preview_canvas, caption=f"Live Studio Canvas Output (Target: {sample_v_url})", use_container_width=True)

        st.divider()
        
        # Batch Processing Engine
        if st.button("🚀 Process Batch & Prepare Certificates", type="primary", use_container_width=True):
            if not st.session_state['uploaded_csv']:
                st.warning("Please upload a CSV file in the 'Uploads' tool tab first.")
            else:
                df_recipients = pd.read_csv(st.session_state['uploaded_csv'])
                zip_buffer = io.BytesIO()
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                count = 0
                elem_cfg_final = elem_cfg.copy()
                elem_cfg_final['name']['placeholders'] = False
                elem_cfg_final['id']['placeholders'] = False

                processed_records = []

                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for idx, row in df_recipients.iterrows():
                        cred_id = str(uuid.uuid4())
                        v_url = f"https://certificate-tv.streamlit.app/?id={cred_id}"
                        
                        cert_out = render_dynamic_certificate(
                            base_img, row['name'], row['course'], str(row['date']), cred_id, v_url, elem_cfg_final
                        )
                        
                        img_byte_arr = io.BytesIO()
                        cert_out.save(img_byte_arr, format='PNG')
                        zip_file.writestr(f"{row['name'].replace(' ', '_')}_{cred_id[:8]}.png", img_byte_arr.getvalue())
                        
                        cursor.execute("""
                            INSERT INTO credentials (credential_id, recipient_name, email, course_name, issue_date)
                            VALUES (?, ?, ?, ?, ?)
                        """, (cred_id, row['name'], row['email'], row['course'], str(row['date'])))
                        
                        processed_records.append({
                            'credential_id': cred_id,
                            'name': row['name'],
                            'email': row['email'],
                            'course': row['course']
                        })
                        count += 1
                        
                conn.commit()
                conn.close()
                
                st.session_state['batch_processed'] = True
                st.session_state['batch_zip'] = zip_buffer.getvalue()
                st.session_state['batch_df'] = pd.DataFrame(processed_records)
                st.success(f"🎉 Successfully prepared {count} custom certificates!")

        # Post-Processing Actions (2 Options: Download OR Customized Batch Email)
        if st.session_state['batch_processed']:
            st.subheader("📦 Next Actions: Choose How to Proceed")
            
            act_col1, act_col2 = st.columns([1, 1.2])
            
            with act_col1:
                st.markdown("#### Option 1: Download ZIP Archive")
                st.download_button(
                    label="⬇️ Download Certificates (.ZIP)",
                    data=st.session_state['batch_zip'],
                    file_name="certificates_batch.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
            with act_col2:
                st.markdown("#### Option 2: Send Custom Email to CSV Users")
                
                # Customizable Email Template Expander
                with st.expander("✉️ Customize Email Message Template", expanded=True):
                    custom_subject = st.text_input("Subject Line", value="Your Official Digital Certificate is Ready!", key="post_email_subj")
                    
                    default_body_template = """Hi {{recipient_name}},

Congratulations on completing {{course_name}}!

Your official digital certificate has been issued. You can view, verify, and add your certificate to your LinkedIn profile using the link below:

Digital Credential Verification Link:
{{verification_url}}

Credential ID: {{credential_id}}

Best regards,
Mental Health First Aid Organization"""

                    custom_body = st.text_area("Email Body Template", value=default_body_template, height=180, key="post_email_body")
                    st.caption("Placeholders: `{{recipient_name}}`, `{{course_name}}`, `{{credential_id}}`, `{{verification_url}}`")

                if st.button("📨 Send Custom Email to Users in CSV", type="primary", use_container_width=True):
                    if st.session_state['batch_df'] is not None:
                        send_custom_batch_emails(st.session_state['batch_df'], custom_subject, custom_body)

# ------------------------------------------
# TAB 2: EMAIL DISTRIBUTION ENGINE
# ------------------------------------------
with tabs[1]:
    st.header("Email Distribution Engine")
    st.caption("Send credentials directly to recipients using your configured email sender.")

    col_smtp, col_template = st.columns([1, 1.2])

    with col_smtp:
        st.subheader("✉️ Sender Configuration")
        
        default_sender = st.secrets.get("GMAIL_ADDRESS", "your.email@gmail.com") if hasattr(st, "secrets") else "your.email@gmail.com"
        sender_email = st.text_input("Sender Email Address", value=default_sender)
        
        st.info("🔒 **Security Active:** Passwords and SMTP authentication credentials are automatically loaded securely from backend Secrets.")

    with col_template:
        st.subheader("📧 Email Message Template")
        email_subject = st.text_input("Subject Line", value="Your Digital Credential Certificate is Ready!")
        
        default_gmail_body = """Hi {{recipient_name}},

Congratulations on completing {{course_name}}!

Your official digital certificate has been issued. You can view, verify, and add your certificate to your LinkedIn profile using the link below:

Digital Credential Verification Link:
{{verification_url}}

Credential ID: {{credential_id}}

Best regards,
Mental Health First Aid Organization"""

        email_body = st.text_area("Email Body Template", value=default_gmail_body, height=200)

    st.divider()
    if st.button("📨 Dispatch Batch Emails to All Issued Records", type="primary"):
        conn = sqlite3.connect(DB_FILE)
        df_pending = pd.read_sql_query("SELECT credential_id, recipient_name as name, email, course_name as course FROM credentials", conn)
        conn.close()

        if not df_pending.empty:
            send_custom_batch_emails(df_pending, email_subject, email_body)

# ------------------------------------------
# TAB 3: VIRAL ANALYTICS
# ------------------------------------------
with tabs[2]:
    st.header("Growth & Analytics Dashboard")
    conn = sqlite3.connect(DB_FILE)
    df_events = pd.read_sql_query("SELECT * FROM analytics_events", conn)
    df_creds = pd.read_sql_query("SELECT * FROM credentials", conn)
    conn.close()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Credentials Issued", len(df_creds))
    kpi2.metric("Verification Page Views", len(df_events[df_events['event_type'] == 'view']))
    kpi3.metric("Social Share Clicks", len(df_events[df_events['event_type'] == 'share_click']))
    kpi4.metric("Downloads (PNG/PDF)", len(df_events[df_events['event_type'].str.contains('download')]))

# ------------------------------------------
# TAB 4: CREDENTIALS REGISTRY
# ------------------------------------------
with tabs[3]:
    st.header("Issued Credentials Registry")
    conn = sqlite3.connect(DB_FILE)
    df_all = pd.read_sql_query("SELECT * FROM credentials ORDER BY created_at DESC", conn)
    conn.close()

    st.dataframe(df_all, use_container_width=True)

    st.subheader("Test Verification Links")
    for idx, row in df_all.iterrows():
        c1, c2 = st.columns([3, 1])
        c1.write(f"**{row['recipient_name']}** - {row['course_name']} (`{row['credential_id']}`)")
        if c2.button("Open Portal ↗", key=f"v_{row['credential_id']}"):
            st.query_params["id"] = row['credential_id']
            st.rerun()
