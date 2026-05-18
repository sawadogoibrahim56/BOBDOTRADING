"""
BTF – Service de Notifications
Email, SMS/Push pour : connexion admin, ordres exécutés, abonnement activé, arrêt d'urgence.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger("btf.notifications")


async def send_login_alert(user, ip: str):
    """Alerte de connexion utilisateur."""
    subject = "🔐 Nouvelle connexion BTF"
    body = (
        f"Bonjour {user.full_name},\n\n"
        f"Une nouvelle connexion a été détectée sur votre compte BTF.\n"
        f"IP: {ip}\n"
        f"Heure: {datetime.utcnow().isoformat()} UTC\n\n"
        f"Si ce n'est pas vous, changez votre mot de passe immédiatement."
    )
    await _send_email(user.email, subject, body)


async def send_admin_login_alert(user, ip: str, user_agent: str):
    """Alerte critique de connexion admin."""
    subject = "🚨 CONNEXION ADMIN BTF"
    body = (
        f"ALERTE SÉCURITÉ – Connexion au panneau admin BTF\n\n"
        f"Admin: {user.email}\n"
        f"IP: {ip}\n"
        f"User-Agent: {user_agent}\n"
        f"Heure: {datetime.utcnow().isoformat()} UTC\n\n"
        f"Si ce n'est pas vous, révoquez immédiatement les accès."
    )
    admin_email = os.getenv("ADMIN_ALERT_EMAIL", user.email)
    await _send_email(admin_email, subject, body)
    await _send_sms(os.getenv("ADMIN_PHONE", ""), f"BTF ADMIN LOGIN: {ip} – {datetime.utcnow().strftime('%H:%M')} UTC")


async def send_order_notification(user, order):
    """Notification d'exécution d'ordre."""
    subject = f"⚡ Ordre Exécuté – {order.symbol}"
    body = (
        f"Votre ordre sur BTF a été exécuté.\n\n"
        f"Paire: {order.symbol}\n"
        f"Côté: {order.side.upper()}\n"
        f"Quantité: {order.quantity}\n"
        f"Prix: {order.filled_price}\n"
        f"Mode: {order.mode.upper()}\n"
        f"Stop-Loss: {order.stop_loss or 'N/A'}\n"
        f"Take-Profit: {order.take_profit or 'N/A'}\n"
        f"Risque: {order.risk_percent:.2f}%\n\n"
        f"Connectez-vous sur BTF pour suivre votre position."
    )
    await _send_email(user.email, subject, body)
    if user.phone:
        await _send_sms(user.phone, f"BTF: {order.side.upper()} {order.symbol} @ {order.filled_price} exécuté")


async def send_subscription_activated_notification(user, months: int):
    """Notification d'activation d'abonnement."""
    subject = "✅ Abonnement BTF Activé !"
    body = (
        f"Bonjour {user.full_name},\n\n"
        f"Votre abonnement BTF a été activé pour {months} mois.\n"
        f"Vous avez maintenant accès au trading réel.\n\n"
        f"Slogan: L'argent simple, sécurisé et intelligent pour le Burkina et l'Afrique de l'Ouest.\n\n"
        f"Connectez-vous sur https://btf.bf pour commencer."
    )
    await _send_email(user.email, subject, body)
    if user.phone:
        await _send_sms(user.phone, f"BTF: Abonnement activé {months} mois. Bon trading !")


async def send_emergency_stop_alert(user, drawdown: float, resume_at):
    """Alerte arrêt d'urgence."""
    subject = "🛑 Arrêt d'Urgence BTF – Trading Bloqué"
    body = (
        f"ALERTE RISQUE – Arrêt d'Urgence Automatique\n\n"
        f"Votre drawdown quotidien a atteint {drawdown:.2f}%.\n"
        f"Le trading a été bloqué automatiquement pendant 24 heures.\n"
        f"Reprise prévue: {resume_at.isoformat()}\n\n"
        f"Le Gardien du Risque BTF protège votre capital."
    )
    await _send_email(user.email, subject, body)
    if user.phone:
        await _send_sms(user.phone, f"BTF URGENCE: Drawdown {drawdown:.1f}%. Trading bloqué 24h.")


async def send_payment_received_notification(user, payment):
    """Confirmation réception de preuve de paiement."""
    subject = "📩 Preuve de Paiement Reçue – BTF"
    body = (
        f"Bonjour {user.full_name},\n\n"
        f"Nous avons bien reçu votre preuve de paiement via {payment.payment_method}.\n"
        f"Montant: {payment.amount_fcfa:,.0f} F CFA\n"
        f"Référence: {payment.transaction_ref or 'N/A'}\n\n"
        f"Votre abonnement sera activé sous 24h ouvrées après vérification.\n"
        f"Merci de votre confiance."
    )
    await _send_email(user.email, subject, body)


# ─── BACKENDS D'ENVOI ─────────────────────────────────────────────────────────

async def _send_email(to: str, subject: str, body: str):
    """Envoi email via SMTP (configurable en .env)."""
    try:
        smtp_host   = os.getenv("SMTP_HOST", "")
        smtp_port   = int(os.getenv("SMTP_PORT", "587"))
        smtp_user   = os.getenv("SMTP_USER", "")
        smtp_pass   = os.getenv("SMTP_PASSWORD", "")
        from_email  = os.getenv("FROM_EMAIL", "noreply@btf.bf")

        if not smtp_host or not smtp_user:
            logger.debug(f"Email non configuré – Simulé: {to} | {subject}")
            return

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg["From"]    = from_email
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to, msg.as_string())
        logger.info(f"Email envoyé: {to} | {subject}")
    except Exception as e:
        logger.error(f"Erreur email: {e}")


async def _send_sms(phone: str, message: str):
    """Envoi SMS via Twilio ou Orange SMS API."""
    try:
        if not phone:
            return
        twilio_sid  = os.getenv("TWILIO_ACCOUNT_SID", "")
        twilio_token= os.getenv("TWILIO_AUTH_TOKEN", "")
        twilio_from = os.getenv("TWILIO_FROM_NUMBER", "")

        if not twilio_sid:
            logger.debug(f"SMS simulé: {phone} | {message}")
            return

        from twilio.rest import Client
        client = Client(twilio_sid, twilio_token)
        client.messages.create(body=message, from_=twilio_from, to=phone)
        logger.info(f"SMS envoyé: {phone}")
    except Exception as e:
        logger.error(f"Erreur SMS: {e}")
