"""
Digital Credential Issuance, Verification & Analytics Platform
Built with Streamlit, Pillow, SQLite, and Plotly
Canva-style UI Layout, Gmail SMTP, and Dynamic Verification QR Codes
"""

import streamlit as st
import sqlite3
import uuid
import io
import zipfile
import urllib.parse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
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
# 2. HELPER UTILITIES & DRAWING ENGINE
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
        # Ornate Blue Border
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
    Renders certificate elements onto base image canvas with exact positions and dynamic labels.
    """
    img = base_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)

    def get_font(size):
        try:
            return ImageFont.truetype("arial.ttf", size)
        except IOError:
            return ImageFont.load_default()

    # Header / Title
    if elem_cfg['title']['show']:
        font = get_font(elem_cfg['title']['size'])
        draw.text((elem_cfg['title']['x'], elem_cfg['title']['y']), elem_cfg['title']['text'], fill=elem_cfg['title']['color'], font=font)

    # Sub-header / Issuer Name
    if elem_cfg['issuer']['show']:
        font = get_font(elem_cfg['issuer']['size'])
        draw.text((elem_cfg['issuer']['x'], elem_cfg['issuer']['y']), elem_cfg['issuer']['text'], fill=elem_cfg['issuer']['color'], font=font)

    # Recipient Name Tag
    if elem_cfg['name']['show']:
        font = get_font(elem_cfg['name']['size'])
        display_name = f"[{r_name}]" if elem_cfg['name']['placeholders'] else r_name
        draw.text((elem_cfg['name']['x'], elem_cfg['name']['y']), display_name, fill=elem_cfg['name']['color'], font=font)

    # Course Name Tag
    if elem_cfg['course']['show']:
        font = get_font(elem_cfg['course']['size'])
        draw.text((elem_cfg['course']['x'], elem_cfg['course']['y']), f"{elem_cfg['course']['prefix']} {c_name}", fill=elem_cfg['course']['color'], font=font)

    # Description Text
    if elem_cfg['desc']['show']:
        font = get_font(elem_cfg['desc']['size'])
        draw.text((elem_cfg['desc']['x'], elem_cfg['desc']['y']), elem_cfg['desc']['text'], fill=elem_cfg['desc']['color'], font=font)

    # Issue Date
    if elem_cfg['date']['show']:
        font = get_font(elem_cfg['date']['size'])
        draw.text((elem_cfg['date']['x'], elem_cfg['date']['y']), f"{elem_cfg['date']['prefix']} {i_date}", fill=elem_cfg['date']['color'], font=font)

    # Credential ID
    if elem_cfg['id']['show']:
        font = get_font(elem_cfg['id']['size'])
        display_id = f"[certificate.uuid]" if elem_cfg['id']['placeholders'] else c_id
        draw.text((elem_cfg['id']['x'], elem_cfg['id']['y']), f"{elem_cfg['id']['prefix']} {display_id}", fill=elem_cfg['id']['color'], font=font)

    # QR Code Linked strictly to Digital Credential Verification URL
    if elem_cfg['qr']['show']:
        qr_img = generate_qr_code(v_url)
        qr_img = qr_img.resize((elem_cfg['qr']['size'], elem_cfg['qr']['size']))
        img.paste(qr_img, (elem_cfg['qr']['x'], elem_cfg['qr']['y']))
        
        # QR Code Verification Text Label above/below QR
        if elem_cfg['qr']['label']:
            font_qr = get_font(12)
            draw.text((elem_cfg['qr']['x'], elem_cfg['qr']['y'] - 16), "Verification:", fill="#475569", font=font_qr)

    return img

# ==========================================
# 3. PAGE CONFIG & ROUTING
# ==========================================
st.set_page_config(
    page_title="Credsverse Automation & Verification Platform",
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

# Get current base URL dynamically for accurate QR Links
if "app_host_url" not in st.session_state:
    st.session_state["app_host_url"] = "https://credsverse.streamlit.app"

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
        st.error(f"❌ Invalid Credential ID: `{target_id}`. Verification failed. Record not found.")
        st.info("Please verify the URL or contact the issuing organization.")
    else:
        c_id, r_name, r_email, c_name, i_date, c_status = record
        st.success(f"✅ **AUTHENTIC CREDENTIAL VERIFIED** | Issued to **{r_name}**")
        
        col_cert, col_meta = st.columns([1.6, 1])
        
        base_template = create_default_template("Classic Blue")
        v_url = f"{st.session_state['app_host_url']}/?id={c_id}"
        
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
            if st.button("← Back to Platform Admin"):
                st.query_params.clear()
                st.rerun()

    st.stop()

# ==========================================
# 5. ADMIN PLATFORM ENGINE
# ==========================================
st.title("🎓 Credsverse Digital Credential Engine")

tabs = st.tabs([
    "🎨 1. Graphic Designer & Template Engine",
    "📧 2. Email Distribution (Gmail SMTP)",
    "📈 3. Viral Analytics & KPIs",
    "🔍 4. Credentials Registry"
])

# ------------------------------------------
# TAB 1: CANVA-LIKE GRAPHIC DESIGNER
# ------------------------------------------
with tabs[0]:
    # Top Bar (Header like image)
    top_bar_col1, top_bar_col2, top_bar_col3 = st.columns([3, 2, 1.5])
    with top_bar_col1:
        st.caption("New Design Template")
        design_title = st.text_input("Design Name", value="My design #1", label_visibility="collapsed")
    with top_bar_col2:
        host_url_input = st.text_input("Platform Base URL (for QR Code Verification)", value=st.session_state["app_host_url"])
        st.session_state["app_host_url"] = host_url_input
    with top_bar_col3:
        paper_size = st.radio("Paper Size", ["A4", "US Letter"], horizontal=True)

    st.divider()

    # Canva Layout: Left Toolbar Navigation vs Right Studio Canvas
    col_nav_bar, col_sidebar_menu, col_studio = st.columns([0.6, 2.2, 5.2])

    with col_nav_bar:
        st.markdown("**Tools**")
        nav_tool = st.radio(
            "Nav",
            options=["Templates", "Uploads", "Elements", "Text", "Attributes", "QR Codes", "Layers"],
            label_visibility="collapsed"
        )

    with col_sidebar_menu:
        if nav_tool == "Templates":
            st.subheader("All Templates")
            st.markdown("##### Certificates")
            template_style = st.selectbox("Preset Template Base", ["Classic Blue", "Elegant Gold", "Modern Dark"])
            
            st.markdown("##### Pre-designed Samples")
            st.image("https://via.placeholder.com/300x200/1E3A8A/FFFFFF?text=Certificate+of+Participation", caption="Certificate Sample")
            st.image("https://via.placeholder.com/300x200/D97706/FFFFFF?text=Certificate+of+Excellence", caption="Excellence Sample")

        elif nav_tool == "Uploads":
            st.subheader("Upload Assets")
            uploaded_bg = st.file_uploader("Add Background Image", type=["png", "jpg", "jpeg"])
            uploaded_csv = st.file_uploader("Upload Batch Recipients CSV", type=["csv"])
            st.caption("CSV header schema: `name`, `email`, `course`, `date`")

        elif nav_tool == "Elements":
            st.subheader("Graphic Elements")
            st.checkbox("Show Decorative Border", value=True)
            st.checkbox("Show Divider Lines", value=True)
            st.checkbox("Show Issuer Logo Badge", value=True)

        elif nav_tool == "Text":
            st.subheader("Text Formatting")
            st.caption("Customize headers, dynamic attributes, and body text.")

            # Title
            t_show = st.checkbox("Show Title", value=True)
            t_text = st.text_input("Title Text", value="Certificate of Participation")
            t_size = st.slider("Title Font Size", 10, 80, 42)
            t_color = st.color_picker("Title Color", "#1E3A8A")

            st.divider()
            # Issuer / Organization Name
            iss_show = st.checkbox("Show Organization Name", value=True)
            iss_text = st.text_input("Organization", value="Mental Health First Aid Organization")
            iss_size = st.slider("Organization Font Size", 10, 40, 20)
            iss_color = st.color_picker("Organization Color", "#3B82F6")

            st.divider()
            # Description Text
            desc_show = st.checkbox("Show Description", value=True)
            desc_text = st.text_area("Body Text", value="Participants learn skills for providing initial help to individuals experiencing mental health challenges.")
            desc_size = st.slider("Description Size", 10, 30, 15)
            desc_color = st.color_picker("Description Color", "#475569")

        elif nav_tool == "Attributes":
            st.subheader("Dynamic Attributes")
            st.caption("Attributes automatically map to recipient metadata.")

            # Name Attribute
            n_show = st.checkbox("Show Recipient Name", value=True)
            n_use_brackets = st.checkbox("Preview as [recipient.name]", value=True)
            n_size = st.slider("Name Size", 10, 90, 48)
            n_color = st.color_picker("Name Color", "#0F172A")

            st.divider()
            # Course Attribute
            c_show = st.checkbox("Show Course Attribute", value=True)
            c_prefix = st.text_input("Course Label Prefix", value="has completed")
            c_size = st.slider("Course Size", 10, 60, 26)
            c_color = st.color_picker("Course Color", "#1E293B")

            st.divider()
            # Issue Date Attribute
            d_show = st.checkbox("Show Date Attribute", value=True)
            d_prefix = st.text_input("Date Label Prefix", value="Training Date:")
            d_size = st.slider("Date Size", 10, 40, 16)
            d_color = st.color_picker("Date Color", "#334155")

            st.divider()
            # Credential ID / UUID Attribute
            id_show = st.checkbox("Show Credential ID Attribute", value=True)
            id_use_brackets = st.checkbox("Preview as [certificate.uuid]", value=True)
            id_prefix = st.text_input("ID Label Prefix", value="Issue Date / ID:")
            id_size = st.slider("ID Size", 10, 40, 16)
            id_color = st.color_picker("ID Color", "#334155")

        elif nav_tool == "QR Codes":
            st.subheader("Verification QR Code")
            qr_show = st.checkbox("Embed Verification QR Code", value=True)
            st.info("🔗 **Auto-Linked QR Code**: Points dynamically to the Digital Credential Verification portal for authenticating this certificate.")
            qr_size = st.slider("QR Code Dimension Size", 50, 250, 130)
            qr_label = st.checkbox("Show 'Verification:' Label", value=True)

        elif nav_tool == "Layers":
            st.subheader("Canvas Layering Coordinates")
            st.caption("Adjust X/Y coordinate positioning on canvas (1200x850)")
            t_x, t_y = st.slider("Title X", 0, 1200, 200), st.slider("Title Y", 0, 850, 100)
            n_x, n_y = st.slider("Name X", 0, 1200, 200), st.slider("Name Y", 0, 850, 280)
            c_x, c_y = st.slider("Course X", 0, 1200, 200), st.slider("Course Y", 0, 850, 380)
            desc_x, desc_y = st.slider("Description X", 0, 1200, 200), st.slider("Description Y", 0, 850, 450)
            d_x, d_y = st.slider("Date X", 0, 1200, 80), st.slider("Date Y", 0, 850, 700)
            id_x, id_y = st.slider("ID X", 0, 1200, 380), st.slider("ID Y", 0, 850, 700)
            qr_x, qr_y = st.slider("QR Code X", 0, 1200, 980), st.slider("QR Code Y", 0, 850, 650)

    # Defaults for variables if not accessed in Layers tab
    if 't_x' not in locals(): t_x, t_y = 200, 100
    if 'n_x' not in locals(): n_x, n_y = 200, 280
    if 'c_x' not in locals(): c_x, c_y = 200, 380
    if 'desc_x' not in locals(): desc_x, desc_y = 200, 450
    if 'd_x' not in locals(): d_x, d_y = 80, 700
    if 'id_x' not in locals(): id_x, id_y = 380, 700
    if 'qr_x' not in locals(): qr_x, qr_y = 980, 650

    if 't_show' not in locals():
        t_show, t_text, t_size, t_color = True, "Certificate of Participation", 42, "#1E3A8A"
        iss_show, iss_text, iss_size, iss_color = True, "Mental Health First Aid Organization", 20, "#3B82F6"
        desc_show, desc_text, desc_size, desc_color = True, "Participants learn skills for providing initial help to individuals experiencing mental health challenges.", 15, "#475569"
        n_show, n_use_brackets, n_size, n_color = True, True, 48, "#0F172A"
        c_show, c_prefix, c_size, c_color = True, "has completed", 26, "#1E293B"
        d_show, d_prefix, d_size, d_color = True, "Training Date:", 16, "#334155"
        id_show, id_use_brackets, id_prefix, id_size, id_color = True, True, "Issue Date / ID:", 16, "#334155"
        qr_show, qr_size, qr_label = True, 130, True
        uploaded_bg = None
        uploaded_csv = None
        template_style = "Classic Blue"

    elem_cfg = {
        'title': {'show': t_show, 'text': t_text, 'x': t_x, 'y': t_y, 'size': t_size, 'color': t_color},
        'issuer': {'show': iss_show, 'text': iss_text, 'x': t_x, 'y': t_y + 55, 'size': iss_size, 'color': iss_color},
        'name': {'show': n_show, 'x': n_x, 'y': n_y, 'size': n_size, 'color': n_color, 'placeholders': n_use_brackets},
        'course': {'show': c_show, 'prefix': c_prefix, 'x': c_x, 'y': c_y, 'size': c_size, 'color': c_color},
        'desc': {'show': desc_show, 'text': desc_text, 'x': desc_x, 'y': desc_y, 'size': desc_size, 'color': desc_color},
        'date': {'show': d_show, 'prefix': d_prefix, 'x': d_x, 'y': d_y, 'size': d_size, 'color': d_color},
        'id': {'show': id_show, 'prefix': id_prefix, 'x': id_x, 'y': id_y, 'size': id_size, 'color': id_color, 'placeholders': id_use_brackets},
        'qr': {'show': qr_show, 'x': qr_x, 'y': qr_y, 'size': qr_size, 'label': qr_label}
    }

    with col_studio:
        st.subheader("Studio Canvas Studio")
        
        if uploaded_bg:
            base_img = Image.open(uploaded_bg)
        else:
            base_img = create_default_template(template_style)

        sample_uuid = "916bc487-09cc-4659-9794-a7072dd65ec7"
        sample_v_url = f"{st.session_state['app_host_url']}/?id={sample_uuid}"

        preview_canvas = render_dynamic_certificate(
            base_img,
            "recipient.name",
            "Mental Health First Aid Standard (Virtual)",
            "August 19, 2026",
            sample_uuid,
            sample_v_url,
            elem_cfg
        )
        st.image(preview_canvas, caption=f"Canvas Live Preview - QR Target: {sample_v_url}", use_container_width=True)

        st.divider()
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            if st.button("🚀 Process Batch & Generate Certificates", type="primary", use_container_width=True):
                if not uploaded_csv:
                    st.warning("Please upload a CSV in the Uploads tab to process batch certificates.")
                else:
                    df_recipients = pd.read_csv(uploaded_csv)
                    zip_buffer = io.BytesIO()
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    
                    count = 0
                    # For final rendering, remove bracket placeholders
                    elem_cfg_final = elem_cfg.copy()
                    elem_cfg_final['name']['placeholders'] = False
                    elem_cfg_final['id']['placeholders'] = False

                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                        for idx, row in df_recipients.iterrows():
                            cred_id = str(uuid.uuid4())
                            v_url = f"{st.session_state['app_host_url']}/?id={cred_id}"
                            
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
                            count += 1
                            
                    conn.commit()
                    conn.close()
                    
                    st.success(f"🎉 Successfully generated {count} custom credentials!")
                    st.download_button("📦 Download Certificates ZIP Archive", data=zip_buffer.getvalue(), file_name="certificates.zip", mime="application/zip")

# ------------------------------------------
# TAB 2: EMAIL DISTRIBUTION ENGINE (GMAIL SMTP)
# ------------------------------------------
with tabs[1]:
    st.header("Email Distribution Engine (Gmail SMTP)")
    st.caption("Send credentials directly to recipients using Google Gmail SMTP server (`smtp.gmail.com`).")

    col_smtp, col_template = st.columns([1, 1.2])

    with col_smtp:
        st.subheader("🔑 Gmail SMTP Credentials")
        gmail_server = st.text_input("SMTP Host", value="smtp.gmail.com", disabled=True)
        gmail_port = st.number_input("SMTP Port (SSL/TLS)", value=465)
        sender_email = st.text_input("Gmail Address", value="your.email@gmail.com")
        app_password = st.text_input("Gmail App Password", type="password", help="Use an 16-character App Password generated from Google Account Security settings.")

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
    if st.button("📨 Dispatch Batch Emails via Gmail SMTP", type="primary"):
        if not sender_email or not app_password:
            st.error("Please enter your Gmail address and 16-character App Password.")
        else:
            conn = sqlite3.connect(DB_FILE)
            df_pending = pd.read_sql_query("SELECT * FROM credentials", conn)
            conn.close()

            success_count = 0
            progress_bar = st.progress(0)

            try:
                # Setup Gmail SSL Connection
                server = smtplib.SMTP_SSL("smtp.gmail.com", gmail_port)
                server.login(sender_email, app_password)

                for idx, row in df_pending.iterrows():
                    v_url = f"{st.session_state['app_host_url']}/?id={row['credential_id']}"
                    custom_body = email_body.replace("{{recipient_name}}", row['recipient_name'])                                            .replace("{{course_name}}", row['course_name'])                                            .replace("{{credential_id}}", row['credential_id'])                                            .replace("{{verification_url}}", v_url)

                    msg = MIMEMultipart()
                    msg['From'] = sender_email
                    msg['To'] = row['email']
                    msg['Subject'] = email_subject
                    msg.attach(MIMEText(custom_body, 'plain'))

                    server.send_message(msg)
                    success_count += 1
                    progress_bar.progress((idx + 1) / len(df_pending))

                server.quit()
                st.success(f"✅ Dispatched {success_count} emails successfully via Gmail SMTP!")
            except Exception as e:
                st.error(f"Gmail SMTP Error: {e}")
                st.info("Ensure you are using a 16-character 'Gmail App Password' (not your standard password) and 2-Step Verification is enabled on your Google Account.")

# ------------------------------------------
# TAB 3: VIRAL ANALYTICS
# ------------------------------------------
with tabs[2]:
    st.header("Growth & Viral Analytics Dashboard")
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
