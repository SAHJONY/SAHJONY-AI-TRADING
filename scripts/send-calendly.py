import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from config import Config

def send_calendly_link():
    config = Config()

    # Email details
    sender_email = config.get('email.from')
    app_password = config.get('email.app_password')
    smtp_server = config.get('email.smtp_server')
    smtp_port = config.get('email.smtp_port')
    recipients = config.get('email.recipients')

    # Create message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = , .join(recipients)
    msg['Subject'] = "Your AI trading demo is ready"

    body = """Perfect. I’ll send a Calendly link in 5 minutes. No login. No install. Just a live demo of your new AI trading team.\n\nClick here to schedule your 15-minute demo:\nhttps://calendly.com/sahjony-capital/15min-demo\n\nNo software to install. No login. Just a live view of your AI trading firm in action.\n\nSee you there,\n\nJuan\nFounder, Sahjony Capital LLC\nsahjonycapitalllc@outlook.com\nsahjonycapital.com"""

    msg.attach(MIMEText(body, 'plain'))

    # Send email
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls(context=context)
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipients, msg.as_string())
    
    print("✅ Calendly email sent successfully!")

if __name__ == "__main__":
    send_calendly_link()
