import os

from integrations.graph_mail import send_mail_graph


def send_welcome_email(to_email: str, full_name: str, temp_password: str = "Ph.2026") -> None:
    web_base = os.getenv("WEB_APP_URL", "http://localhost:5173").rstrip("/")
    login_url = f"{web_base}/login"
    subject = "Acceso Plataforma de Productividad"
    body = f"""
    <p>Hola {full_name},</p>
    <p>Tu usuario fue creado en la Plataforma de Productividad.</p>
    <p><strong>Usuario:</strong> {to_email}</p>
    <p><strong>Contrasena temporal:</strong> {temp_password}</p>
    <p><strong>Ingreso:</strong> <a href=\"{login_url}\">{login_url}</a></p>
    <p>Por seguridad, en el primer ingreso se te pedira cambiar la contrasena.</p>
    """
    send_mail_graph(to_email, subject, body)


def send_reset_password_email(to_email: str, reset_token: str) -> None:
    web_base = os.getenv("WEB_APP_URL", "http://localhost:5173").rstrip("/")
    reset_url = f"{web_base}/reset-password?token={reset_token}"
    subject = "Recuperacion de contrasena"
    body = f"""
    <p>Hola,</p>
    <p>Recibimos una solicitud para recuperar tu contrasena.</p>
    <p>Usa este enlace (expira pronto):</p>
    <p><a href=\"{reset_url}\">{reset_url}</a></p>
    <p>Si no solicitaste este cambio, puedes ignorar este correo.</p>
    """
    send_mail_graph(to_email, subject, body)
