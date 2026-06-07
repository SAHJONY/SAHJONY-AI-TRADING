import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from config import Config

def send_trading_firm_email():
    config = Config()

    # Email configuration
    smtp_server = config.get_required('email.smtp_server')
    port = config.get_required('email.smtp_port')
    sender_email = config.get_required('email.from')
    password = config.get_required('email.app_password')

    # Recipients
    recipients = config.get('email.recipients', [])

    # Create message
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = ', '.join(recipients)
    message['Subject'] = 'Your research team just got replaced. Here’s the audit trail.'

    # Body
    body = '''Hi [First Name],\n\nI built a private AI trading firm — not an open-source project, not a demo, not a research paper.\n\nIt’s live. It trades. It logs every decision.\n\nHere’s what it does:\n- Reads 10-Ks, earnings calls, Reddit\n- Runs 452+ quantitative alphas\n- Enforces SEC-compliant risk rules\n- Executes trades via IBKR\n- Generates full audit trail for regulators\n\nNo human analyst. No latency. No bias.\n\nAttached:\n- A 5-minute video of it analyzing NVDA and placing a 0k order\n- A PDF: SahjonyCapitalLLC_Compliance_Report_Q2_2026.pdf\n\nWe’re offering a 30-day trial — no code, no access, no setup. Just results.\n\nIf you’re tired of paying 00K/year for analysts who miss signals and get fired after a bad quarter — let’s talk.\n\n— Juan\nFounder, Sahjony Capital LLC\nsahjonycapitalllc@outlook.com'''

    message.attach(MIMEText(body, 'plain'))

    # Create secure connection
    context = ssl.create_default_context()

    try:
        server = smtplib.SMTP(smtp_server, port)
        server.starttls(context=context)
        server.login(sender_email, password)
        text = message.as_string()
        server.sendmail(sender_email, recipients, text)
        print('✅ Email sent successfully!')
    except Exception as e:
        print(f'❌ Email failed: {e}')
    finally:
        server.quit()

if __name__ == '__main__':
    send_trading_firm_email()
