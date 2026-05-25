import os

import requests


def _graph_access_token() -> str:
    tenant_id = os.getenv("AZURE_TENANT_ID", "").strip()
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    client_secret = os.getenv("AZURE_CLIENT_SECRET", "").strip()

    if tenant_id and client_id and client_secret:
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        form = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        token_response = requests.post(token_url, data=form, timeout=30)
        if token_response.status_code != 200:
            raise RuntimeError(
                f"No se pudo obtener token Graph: {token_response.status_code} {token_response.text}"
            )
        body = token_response.json()
        access_token = str(body.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Azure no devolvio access_token para Graph")
        return access_token

    fallback = os.getenv("GRAPH_ACCESS_TOKEN", "").strip()
    if fallback:
        return fallback

    raise RuntimeError(
        "Faltan credenciales de Graph. Define AZURE_TENANT_ID/AZURE_CLIENT_ID/AZURE_CLIENT_SECRET o GRAPH_ACCESS_TOKEN"
    )


def send_mail_graph(to_email: str, subject: str, html_body: str) -> None:
    token = _graph_access_token()
    sender = os.getenv("GRAPH_SENDER_UPN", "").strip() or os.getenv(
        "GRAPH_SENDER_USER_ID", ""
    ).strip()
    if not sender:
        raise RuntimeError("Falta GRAPH_SENDER_UPN o GRAPH_SENDER_USER_ID")

    url = f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": "true",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code not in (200, 202):
        raise RuntimeError(f"Graph sendMail fallo: {response.status_code} {response.text}")
