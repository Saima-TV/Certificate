# TAB 2: EMAIL DISTRIBUTION ENGINE
# ------------------------------------------
with tabs[1]:
    st.header("Email Distribution Engine")
    st.header("Email Distribution")
st.caption("Select specific issued records from the database and dispatch customized email credentials.")

col_smtp, col_template = st.columns([1, 1.2])
@@ -619,7 +619,7 @@ def send_custom_batch_emails(df_recipients, custom_subject, custom_body_template
Credential ID: {{credential_id}}

Best regards,
Mental Health First Aid Organization"""
Tech Valley"""

email_body = st.text_area("Email Body Template", value=default_gmail_body, height=180, key="tab2_email_body")
st.caption("Placeholders: `{{recipient_name}}`, `{{course_name}}`, `{{credential_id}}`, `{{verification_url}}`")
@@ -667,51 +667,6 @@ def send_custom_batch_emails(df_recipients, custom_subject, custom_body_template

if st.button(f"📨 Dispatch Emails to Selected Records ({len(target_recipients)})", type="primary", use_container_width=True):
send_custom_batch_emails(target_recipients, email_subject, email_body)
# ------------------------------------------
# TAB 2: EMAIL DISTRIBUTION ENGINE
# ------------------------------------------
with tabs[1]:
    st.header("Email Distribution Engine")
    st.caption("Send credentials directly to recipients using your configured email sender.")

    col_smtp, col_template = st.columns([1, 1.2])

    with col_smtp:
        st.subheader("Sender Configuration")
        
        default_sender = st.secrets.get("GMAIL_ADDRESS", "your.email@gmail.com") if hasattr(st, "secrets") else "your.email@gmail.com"
        sender_email = st.text_input("Sender Email Address", value=default_sender)
        
        st.info("🔒 **Security Active:** Passwords and SMTP authentication credentials are automatically loaded securely from backend Secrets.")

    with col_template:
        st.subheader("Email Message Template")
        email_subject = st.text_input("Subject Line", value="Your Digital Credential Certificate is Ready!")
        
        default_gmail_body = """Hi {{recipient_name}},

Congratulations on completing {{course_name}}!

Your official digital certificate has been issued. You can view, verify, and add your certificate to your LinkedIn profile using the link below:

Digital Credential Verification Link:
{{verification_url}}

Credential ID: {{credential_id}}

Best regards,
Tech Valley"""

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
