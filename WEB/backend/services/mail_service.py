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
    <p><strong>Contraseña temporal:</strong> {temp_password}</p>
    <p><strong>Ingreso:</strong> <a href=\"{login_url}\">{login_url}</a></p>
    <p>Por seguridad, en el primer ingreso se te pedirá cambiar la contraseña.</p>
    """
    send_mail_graph(to_email, subject, body)


def send_reset_password_email(to_email: str, reset_code: str, expires_minutes: int) -> None:
    web_base = os.getenv("WEB_APP_URL", "http://localhost:5173").rstrip("/")
    recovery_url = f"{web_base}/forgot-password"
    subject = "Recuperación de contraseña"
    body = f"""
    <p>Hola,</p>
    <p>Recibimos una solicitud para recuperar tu contraseña.</p>
    <p>Ingresa a la plataforma en este enlace:</p>
    <p><a href=\"{recovery_url}\">{recovery_url}</a></p>
    <p>Luego usa este código para actualizar tu contraseña:</p>
    <p style=\"font-size:24px;font-weight:700;letter-spacing:4px;\">{reset_code}</p>
    <p>Este código expira en {expires_minutes} minutos.</p>
    <p>Si no solicitaste este cambio, puedes ignorar este correo.</p>
    """
    send_mail_graph(to_email, subject, body)
