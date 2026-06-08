"""
Sahjony Capital LLC — Institutional Email Outreach
Production-grade cold email via Outlook SMTP with firm branding.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
import config


def send_email(
    to: str,
    subject: str,
    body_html: str,
    cc: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """Send an institutional-grade email via Outlook SMTP."""
    if not config.OUTLOOK_EMAIL or not config.OUTLOOK_APP_PASSWORD:
        return {"error": "Outlook credentials not configured", "status": "failed"}

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{config.FIRM_NAME} <{config.OUTLOOK_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP("smtp-mail.outlook.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(config.OUTLOOK_EMAIL, config.OUTLOOK_APP_PASSWORD)
            server.sendmail(config.OUTLOOK_EMAIL, [to], msg.as_string())
        return {"status": "sent", "to": to, "subject": subject}
    except Exception as e:
        return {"error": str(e), "status": "failed"}


def investor_outreach_email(
    recipient_name: str,
    recipient_email: str,
    fund_focus: str = "AI-driven quantitative strategies",
    aum_range: str = "inception-stage",
) -> dict:
    """Send institutional investor outreach email."""
    subject = f"{config.FIRM_NAME} — Proprietary AI Trading Strategies"

    html = f"""\
<html>
<body style="font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a2e; max-width: 600px; margin: 0 auto;">
<div style="background: linear-gradient(135deg, #0a0a23 0%, #1a1a3e 100%); padding: 32px; border-radius: 8px 8px 0 0;">
  <h1 style="color: #ffffff; margin: 0; font-size: 22px; letter-spacing: 0.5px;">{config.FIRM_NAME}</h1>
  <p style="color: #8b8ba8; margin: 4px 0 0 0; font-size: 13px;">Proprietary AI Trading &amp; Quantitative Research</p>
</div>
<div style="padding: 28px; border: 1px solid #e0e0e8; border-top: none; border-radius: 0 0 8px 8px;">
  <p style="font-size: 15px; line-height: 1.6;">Dear {recipient_name},</p>
  <p style="font-size: 15px; line-height: 1.6;">
    I am reaching out from <strong>{config.FIRM_NAME}</strong>, a proprietary trading firm
    specializing in <strong>{fund_focus}</strong>. Our systems leverage multi-model AI architectures
    for real-time signal generation and risk management.
  </p>
  <p style="font-size: 15px; line-height: 1.6;">
    We are currently {aum_range} and seeking strategic capital partners who understand
    the asymmetric upside of AI-native trading infrastructure.
  </p>
  <div style="background: #f5f5fa; padding: 16px; border-radius: 6px; margin: 20px 0;">
    <p style="margin: 0; font-size: 14px; color: #444;"><strong>Key Differentiators:</strong></p>
    <ul style="margin: 8px 0 0 0; padding-left: 20px; font-size: 14px; color: #555; line-height: 1.8;">
      <li>Multi-provider AI ensemble (NVIDIA NIM, OpenAI, Anthropic)</li>
      <li>Real-time market analysis with institutional-grade risk controls</li>
      <li>Proprietary signal generation with backtested confidence scoring</li>
    </ul>
  </div>
  <p style="font-size: 15px; line-height: 1.6;">
    I would welcome the opportunity to discuss how our approach may align with your investment thesis.
    Please let me know if you are available for a brief introductory call.
  </p>
  <p style="font-size: 15px; line-height: 1.6;">Best regards,</p>
  <p style="font-size: 15px; margin-bottom: 2px;"><strong>{config.OWNER}</strong></p>
  <p style="font-size: 13px; color: #666; margin: 0;">{config.OWNER}, CEO</p>
  <p style="font-size: 13px; color: #666; margin: 2px 0;">{config.FIRM_NAME}</p>
  <p style="font-size: 13px; color: #4a6cf7; margin: 2px 0;">{config.OUTLOOK_EMAIL}</p>
</div>
<div style="text-align: center; padding: 12px; font-size: 11px; color: #999;">
  {config.FIRM_NAME} | This communication is confidential and intended solely for the addressee.
</div>
</body>
</html>
"""
    return send_email(recipient_email, subject, html)
