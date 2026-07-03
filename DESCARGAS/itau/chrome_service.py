import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from curl_cffi import requests
from selenium import webdriver
from selenium.common.exceptions import JavascriptException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait


LOGIN_URL = "https://sac.itau.cl/sfiler/Login.action"
LANDING_URL = "https://sac.itau.cl/sfiler/"
TARGET_URL_SUBSTRING = "Login.action"
DOMAIN_SWITCH_URL_SUBSTRING = "DomainSwitchConfirmationAction.action"
REQUIRED_APP_COOKIES = ("JSESSIONID", "SFILER_COOKIE")
IMPORTANT_COOKIE_NAMES = (
    "SFILER_COOKIE",
    "JSESSIONID",
    "visid_incap_2973278",
    "incap_ses_621_2973278",
    "nlbi_2973278",
    "nlbi_2973278_2147483392",
    "reese84",
)
RELEVANT_COOKIE_NAMES = set(REQUIRED_APP_COOKIES)
RELEVANT_HEADER_NAMES = {
    "cookie",
    "referer",
    "origin",
    "sec-fetch-site",
    "sec-fetch-mode",
    "sec-fetch-dest",
    "sec-fetch-user",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "accept-language",
    "user-agent",
}
ITAU_USERNAME_ENV = "ITAU_USERNAME"
ITAU_PASSWORD_ENV = "ITAU_PASSWORD"
ITAU_USERNAME_FALLBACK_ENV = "USUARIO"
ITAU_PASSWORD_FALLBACK_ENV = "CLAVE"
ITAU_REQUEST_LOCALE_ENV = "ITAU_REQUEST_LOCALE"
ITAU_DIAGNOSTIC_DIR_ENV = "ITAU_DIAGNOSTIC_DIR"
ITAU_SEND_RUN_ID_HEADER_ENV = "ITAU_SEND_RUN_ID_HEADER"
ITAU_BOOTSTRAP_COOKIES_ENV = "ITAU_BOOTSTRAP_COOKIES"
CURL_IMPERSONATE = "chrome"
DEFAULT_DIAGNOSTIC_DIR = os.path.join(os.path.dirname(__file__), "diagnostics")
EDGE_COOKIE_NAMES = tuple(name for name in IMPORTANT_COOKIE_NAMES if name not in REQUIRED_APP_COOKIES)
BLOCKING_STATUS_CODES = {401, 403, 406, 429, 503}
CORRELATION_HEADER_NAMES = {
    "cf-ray",
    "request-id",
    "x-amz-cf-id",
    "x-cache",
    "x-correlation-id",
    "x-iinfo",
    "x-request-id",
    "x-served-by",
    "via",
}
SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "proxy-authorization", "set-cookie"}
POST_LOGIN_WAIT_SECONDS = 15

REFERENCE_REQUEST_HEADERS = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "accept-language": "es-ES,es;q=0.9",
    "cache-control": "max-age=0",
    "host": "sac.itau.cl",
    "referer": LANDING_URL,
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}
REFERENCE_POST_HEADERS = {
    "Accept": REFERENCE_REQUEST_HEADERS["accept"],
    "Accept-Language": REFERENCE_REQUEST_HEADERS["accept-language"],
    "Cache-Control": REFERENCE_REQUEST_HEADERS["cache-control"],
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://sac.itau.cl",
    "Referer": LOGIN_URL,
    "Sec-CH-UA": REFERENCE_REQUEST_HEADERS["sec-ch-ua"],
    "Sec-CH-UA-Mobile": REFERENCE_REQUEST_HEADERS["sec-ch-ua-mobile"],
    "Sec-CH-UA-Platform": REFERENCE_REQUEST_HEADERS["sec-ch-ua-platform"],
    "Sec-Fetch-Dest": REFERENCE_REQUEST_HEADERS["sec-fetch-dest"],
    "Sec-Fetch-Mode": REFERENCE_REQUEST_HEADERS["sec-fetch-mode"],
    "Sec-Fetch-Site": REFERENCE_REQUEST_HEADERS["sec-fetch-site"],
    "Sec-Fetch-User": REFERENCE_REQUEST_HEADERS["sec-fetch-user"],
    "Upgrade-Insecure-Requests": REFERENCE_REQUEST_HEADERS["upgrade-insecure-requests"],
    "User-Agent": REFERENCE_REQUEST_HEADERS["user-agent"],
}
REFERENCE_REQUIRED_COOKIES = {name: "<required>" for name in REQUIRED_APP_COOKIES}

CHROME_PROFILE_STAGING = {
    "user_agent": REFERENCE_REQUEST_HEADERS["user-agent"],
    "accept_language": REFERENCE_REQUEST_HEADERS["accept-language"],
    "viewport": {"width": 1920, "height": 1080},
    "referer_base": LANDING_URL,
    "client_hints": {
        "brands": [
            {"brand": "Chromium", "version": "148"},
            {"brand": "Google Chrome", "version": "148"},
            {"brand": "Not/A)Brand", "version": "99"},
        ],
        "fullVersion": "148.0.0.0",
        "platform": "Windows",
        "platformVersion": "10.0.0",
        "architecture": "x86",
        "model": "",
        "mobile": False,
    },
    "headers": {
        "Accept": REFERENCE_REQUEST_HEADERS["accept"],
        "Cache-Control": REFERENCE_REQUEST_HEADERS["cache-control"],
        "Referer": REFERENCE_REQUEST_HEADERS["referer"],
        "Upgrade-Insecure-Requests": REFERENCE_REQUEST_HEADERS["upgrade-insecure-requests"],
        "Sec-CH-UA": REFERENCE_REQUEST_HEADERS["sec-ch-ua"],
        "Sec-CH-UA-Mobile": REFERENCE_REQUEST_HEADERS["sec-ch-ua-mobile"],
        "Sec-CH-UA-Platform": REFERENCE_REQUEST_HEADERS["sec-ch-ua-platform"],
    },
}


def normalize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in (headers or {}).items()}


def build_cookie_snapshot(cookies: list[dict[str, Any]]) -> dict[str, str]:
    return {cookie["name"]: cookie["value"] for cookie in cookies if cookie.get("name")}


def parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for part in (cookie_header or "").split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookie_map[name] = value
    return cookie_map


def build_cookie_map_from_session(session: requests.Session) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    try:
        for cookie in session.cookies:
            name = getattr(cookie, "name", None)
            value = getattr(cookie, "value", None)
            if name:
                cookie_map[name] = value
    except TypeError:
        pass

    get_dict = getattr(session.cookies, "get_dict", None)
    if not cookie_map and callable(get_dict):
        cookie_map = dict(get_dict())

    return cookie_map


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return uuid.uuid4().hex


def mask_value(value: Any) -> str:
    if value is None:
        return "<missing>"
    text = str(value)
    if not text:
        return "<empty>"
    return f"<present:length={len(text)}>"


def summarize_cookie_map(cookie_map: dict[str, str] | None) -> dict[str, Any]:
    cookie_map = cookie_map or {}
    cookie_names = sorted(name for name, value in cookie_map.items() if value is not None)
    return {
        "present_cookie_names": cookie_names,
        "present_cookie_count": len(cookie_names),
        "required_cookie_names": list(REQUIRED_APP_COOKIES),
        "present_required_cookie_names": [name for name in REQUIRED_APP_COOKIES if cookie_map.get(name)],
        "missing_required_cookie_names": [name for name in REQUIRED_APP_COOKIES if not cookie_map.get(name)],
        "edge_cookie_names": [name for name in EDGE_COOKIE_NAMES if cookie_map.get(name)],
        "cookies": {name: mask_value(cookie_map.get(name)) for name in cookie_names},
    }


def extract_set_cookie_names(header_value: Any) -> list[str]:
    if not header_value:
        return []
    values = header_value if isinstance(header_value, list) else [header_value]
    names: list[str] = []
    for value in values:
        parts = str(value).split(", ")
        for part in parts:
            first = part.split(";", 1)[0]
            if "=" in first:
                name = first.split("=", 1)[0].strip()
                if name and name not in names:
                    names.append(name)
    return names


def sanitize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (headers or {}).items():
        normalized = str(key).lower()
        if normalized == "set-cookie":
            sanitized[key] = {
                "present": bool(value),
                "cookie_names": extract_set_cookie_names(value),
            }
        elif normalized in SENSITIVE_HEADER_NAMES:
            sanitized[key] = mask_value(value)
        else:
            sanitized[key] = value
    return sanitized


def filter_headers_for_evidence(headers: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_headers(headers)
    selected_names = set(RELEVANT_HEADER_NAMES) | CORRELATION_HEADER_NAMES | {"server", "location", "set-cookie"}
    return sanitize_headers(
        {
            key: value
            for key, value in normalized.items()
            if key in selected_names
        }
    )


def extract_correlation_ids(headers: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_headers(headers)
    return {
        name: normalized[name]
        for name in sorted(CORRELATION_HEADER_NAMES)
        if normalized.get(name)
    }


def redact_sensitive_text(text: str | None, sensitive_values: list[str] | None = None) -> str:
    redacted = text or ""
    for value in sensitive_values or []:
        if value:
            redacted = redacted.replace(value, "***")
    return redacted


def compact_url(url: Any, max_chars: int = 500) -> Any:
    if not isinstance(url, str):
        return url
    if url.startswith("data:"):
        return f"{url[:80]}...<truncated:data-url:length={len(url)}>"
    if len(url) > max_chars:
        return f"{url[:max_chars]}...<truncated:length={len(url)}>"
    return url


def sanitize_snapshot(snapshot: dict[str, Any] | None, sensitive_values: list[str] | None = None) -> dict[str, Any]:
    if not snapshot:
        return {}
    sanitized = dict(snapshot)
    for key in ("html_excerpt", "body_text_excerpt"):
        sanitized[key] = redact_sensitive_text(str(sanitized.get(key, "")), sensitive_values)
    return sanitized


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    if "loginForm.password" in sanitized:
        sanitized["loginForm.password"] = "***"
    if "loginForm.username" in sanitized:
        sanitized["loginForm.username"] = mask_value(sanitized["loginForm.username"])
    return sanitized


def load_login_config_from_env() -> dict[str, str]:
    username = (os.getenv(ITAU_USERNAME_ENV) or os.getenv(ITAU_USERNAME_FALLBACK_ENV, "")).strip()
    password = os.getenv(ITAU_PASSWORD_ENV) or os.getenv(ITAU_PASSWORD_FALLBACK_ENV, "")
    request_locale = os.getenv(ITAU_REQUEST_LOCALE_ENV, "es").strip() or "es"

    if not username:
        raise ValueError(f"Falta la variable de entorno {ITAU_USERNAME_ENV} o {ITAU_USERNAME_FALLBACK_ENV}")
    if not password:
        raise ValueError(f"Falta la variable de entorno {ITAU_PASSWORD_ENV} o {ITAU_PASSWORD_FALLBACK_ENV}")

    return {
        "username": username,
        "password": password,
        "request_locale": request_locale,
    }


def build_login_payload(username: str, password: str, request_locale: str = "es") -> dict[str, str]:
    return {
        "origUrl": "",
        "request_locale": request_locale,
        "loginForm.username": username,
        "loginForm.password": password,
    }


def build_login_headers() -> dict[str, str]:
    return dict(REFERENCE_POST_HEADERS)


def create_http_session() -> requests.Session:
    session = requests.Session(impersonate=CURL_IMPERSONATE)
    session.headers.update(
        {
            "User-Agent": REFERENCE_REQUEST_HEADERS["user-agent"],
            "Accept": REFERENCE_REQUEST_HEADERS["accept"],
            "Accept-Language": REFERENCE_REQUEST_HEADERS["accept-language"],
            "Cache-Control": REFERENCE_REQUEST_HEADERS["cache-control"],
        }
    )
    return session


def infer_session_stage(cookie_map: dict[str, str], missing_required: list[str]) -> str:
    if not missing_required:
        return "app_ready"
    if any(cookie_map.get(name) for name in IMPORTANT_COOKIE_NAMES):
        return "edge_only"
    return "blocked"


def compare_cookies(reference: dict[str, str], captured: dict[str, str]) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    keys = list(dict.fromkeys(list(reference.keys()) + list(captured.keys())))
    for key in keys:
        reference_value = reference.get(key)
        captured_value = captured.get(key)
        if reference_value == "<required>" and captured_value:
            continue
        if reference_value != captured_value:
            differences.append(
                {
                    "cookie": key,
                    "reference": reference_value,
                    "captured": captured_value,
                }
            )
    return differences


def filter_relevant_cookie_differences(differences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [difference for difference in differences if difference.get("cookie") in RELEVANT_COOKIE_NAMES]


def sanitize_cookie_differences(differences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for difference in differences:
        sanitized.append(
            {
                "cookie": difference.get("cookie"),
                "reference": difference.get("reference"),
                "captured": mask_value(difference.get("captured")),
            }
        )
    return sanitized


def sanitize_associated_cookies(cookies: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in cookies or []:
        if not isinstance(item, dict):
            continue
        cookie = item.get("cookie", {})
        sanitized.append(
            {
                "name": cookie.get("name") or item.get("name"),
                "blockedReasons": item.get("blockedReasons"),
                "exemptionReason": item.get("exemptionReason"),
                "value": mask_value(cookie.get("value") or item.get("value")),
            }
        )
    return sanitized


def compare_headers(
    reference_headers: dict[str, Any],
    captured_headers: dict[str, Any],
    important_order: list[str] | None = None,
) -> list[dict[str, Any]]:
    important_order = important_order or [
        "cookie",
        "referer",
        "origin",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-dest",
        "sec-fetch-user",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "accept-language",
        "user-agent",
    ]

    normalized_reference = normalize_headers(reference_headers)
    normalized_captured = normalize_headers(captured_headers)

    differences: list[dict[str, Any]] = []
    seen = set()
    for key in important_order + sorted(set(normalized_reference) | set(normalized_captured)):
        if key in seen:
            continue
        seen.add(key)
        reference_value = normalized_reference.get(key)
        captured_value = normalized_captured.get(key)
        if reference_value != captured_value:
            differences.append(
                {
                    "header": key,
                    "reference": reference_value,
                    "captured": captured_value,
                }
            )
    return differences


def filter_relevant_header_differences(differences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [difference for difference in differences if difference.get("header") in RELEVANT_HEADER_NAMES]


def warm_up_http_session(session: requests.Session) -> dict[str, Any]:
    response = session.get(
        LANDING_URL,
        timeout=30,
        allow_redirects=True,
        impersonate=CURL_IMPERSONATE,
    )
    cookie_map = build_cookie_map_from_session(session)
    missing_required = [name for name in REQUIRED_APP_COOKIES if not cookie_map.get(name)]

    return {
        "status_code": response.status_code,
        "final_url": response.url,
        "headers": dict(response.headers),
        "cookie_map": cookie_map,
        "important_cookie_names": [name for name in IMPORTANT_COOKIE_NAMES if cookie_map.get(name)],
        "required_cookie_names": list(REQUIRED_APP_COOKIES),
        "missing_required_cookies": missing_required,
        "session_stage": infer_session_stage(cookie_map, missing_required),
        "ready_for_login": not missing_required,
    }


def post_login(
    session: requests.Session,
    username: str,
    password: str,
    request_locale: str = "es",
) -> dict[str, Any]:
    payload = build_login_payload(username, password, request_locale)
    headers = build_login_headers()
    cookies_before_post = build_cookie_map_from_session(session)
    response = session.post(
        LOGIN_URL,
        data=payload,
        headers=headers,
        timeout=30,
        allow_redirects=False,
        impersonate=CURL_IMPERSONATE,
    )
    cookies_after_post = build_cookie_map_from_session(session)

    return {
        "request": {
            "url": LOGIN_URL,
            "headers": headers,
            "payload": sanitize_payload(payload),
            "cookies_before_post": cookies_before_post,
        },
        "response": {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "location": response.headers.get("Location"),
            "cookies_after_post": cookies_after_post,
        },
        "raw_response": response,
    }


def follow_domain_switch_if_present(
    session: requests.Session,
    response: requests.Response,
) -> dict[str, Any]:
    location = response.headers.get("Location", "")
    if DOMAIN_SWITCH_URL_SUBSTRING not in location:
        return {
            "attempted": False,
            "location": location,
            "status_code": None,
            "final_url": None,
            "headers": {},
            "cookie_map": build_cookie_map_from_session(session),
        }

    follow_response = session.get(
        location,
        timeout=30,
        allow_redirects=True,
        impersonate=CURL_IMPERSONATE,
    )

    return {
        "attempted": True,
        "location": location,
        "status_code": follow_response.status_code,
        "final_url": follow_response.url,
        "headers": dict(follow_response.headers),
        "cookie_map": build_cookie_map_from_session(session),
    }


def infer_http_blocking_hypothesis(
    warmup: dict[str, Any],
    post_response: dict[str, Any],
    redirect_followup: dict[str, Any],
    relevant_cookie_differences: list[dict[str, Any]],
) -> str:
    status_code = post_response.get("status_code")
    location = post_response.get("location") or ""

    if warmup.get("status_code") != 200:
        return "missing_prelogin_cookies"
    if status_code == 302 and DOMAIN_SWITCH_URL_SUBSTRING in location and not relevant_cookie_differences:
        return "login_post_redirect_success"
    if status_code == 302 and DOMAIN_SWITCH_URL_SUBSTRING in location and redirect_followup.get("attempted") and redirect_followup.get("status_code") not in {200, 302}:
        return "domain_switch_followup_failed"
    if status_code != 302:
        return "login_post_rejected"
    return "unknown"


def build_chrome_options(headless: bool, profile: dict[str, Any] | None = None) -> Options:
    profile = profile or CHROME_PROFILE_STAGING
    viewport = profile.get("viewport", {})

    options = Options()
    if headless:
        options.add_argument("--headless=new")

    if profile.get("user_agent_override"):
        options.add_argument(f"user-agent={profile['user_agent_override']}")
    options.add_argument(f"--window-size={viewport.get('width', 1920)},{viewport.get('height', 1080)}")
    options.add_argument(f"--lang={profile.get('accept_language', 'es-ES').split(',')[0]}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    options.add_experimental_option("perfLoggingPrefs", {"enableNetwork": True, "enablePage": False})
    return options


def configure_network_context(driver: WebDriver, profile: dict[str, Any] | None = None, run_id: str | None = None) -> None:
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Page.enable", {})
    if os.getenv(ITAU_SEND_RUN_ID_HEADER_ENV, "").strip().lower() in {"1", "true", "yes"} and run_id:
        driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"X-Automation-Run-Id": run_id}})


def collect_network_events(driver: WebDriver) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for entry in driver.get_log("performance"):
        try:
            message = json.loads(entry["message"])
            inner_message = message.get("message", {})
            method = inner_message.get("method", "")
            params = inner_message.get("params", {})
            if method.startswith("Network."):
                events.append({"method": method, "params": params})
        except (KeyError, TypeError, json.JSONDecodeError):
                continue
    return events


def summarize_network_events(events: list[dict[str, Any]], max_items: int = 120) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for event in events:
        method = event.get("method")
        params = event.get("params", {})
        summary: dict[str, Any] = {
            "method": method,
            "requestId": params.get("requestId"),
        }
        if method == "Network.requestWillBeSent":
            request = params.get("request", {})
            summary.update(
                {
                    "url": compact_url(request.get("url")),
                    "request_method": request.get("method"),
                    "has_post_data": bool(request.get("postData")),
                }
            )
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            summary.update(
                {
                    "url": compact_url(response.get("url")),
                    "status": response.get("status"),
                    "statusText": response.get("statusText"),
                    "response_headers": filter_headers_for_evidence(response.get("headers", {})),
                }
            )
        elif method == "Network.loadingFailed":
            summary.update(
                {
                    "errorText": params.get("errorText"),
                    "blockedReason": params.get("blockedReason"),
                    "corsErrorStatus": params.get("corsErrorStatus"),
                }
            )
        else:
            continue
        summaries.append(summary)
    return summaries[-max_items:]


def list_response_summaries(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    request_methods: dict[str, str] = {}
    for event in events:
        if event.get("method") != "Network.requestWillBeSent":
            continue
        params = event.get("params", {})
        request = params.get("request", {})
        request_id = params.get("requestId")
        if request_id:
            request_methods[request_id] = request.get("method")

    for event in events:
        if event.get("method") != "Network.responseReceived":
            continue
        params = event.get("params", {})
        response = params.get("response", {})
        request_id = params.get("requestId")
        responses.append(
            {
                "requestId": request_id,
                "method": request_methods.get(request_id),
                "url": response.get("url"),
                "status": response.get("status"),
                "statusText": response.get("statusText"),
                "headers": response.get("headers", {}),
            }
        )
    return responses


def find_latest_response(
    events: list[dict[str, Any]],
    url_substring: str | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    responses = list_response_summaries(events)
    for response in reversed(responses):
        url = str(response.get("url") or "")
        response_method = str(response.get("method") or "").upper()
        if url_substring and url_substring not in url:
            continue
        if method and response_method != method.upper():
            continue
        return response
    return {}


def extract_response_body_excerpt(driver: WebDriver, request_id: str | None, max_chars: int = 1500) -> str:
    if not request_id:
        return ""
    try:
        body_result = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
    except Exception:
        return ""
    body = body_result.get("body", "")
    if body_result.get("base64Encoded"):
        return "<base64-response-body>"
    return str(body)[:max_chars]


def extract_request_headers(events: list[dict[str, Any]], url_substring: str) -> dict[str, Any]:
    for event in events:
        if event.get("method") != "Network.requestWillBeSent":
            continue
        request = event.get("params", {}).get("request", {})
        url = str(request.get("url", ""))
        if url_substring in url:
            return {
                "requestId": event.get("params", {}).get("requestId"),
                "url": url,
                "method": request.get("method"),
                "headers": request.get("headers", {}),
                "postData": request.get("postData"),
            }
    return {}


def extract_request_extra_info(events: list[dict[str, Any]], url_substring: str) -> dict[str, Any]:
    request_ids = set()
    for event in events:
        if event.get("method") != "Network.requestWillBeSent":
            continue
        request = event.get("params", {}).get("request", {})
        url = str(request.get("url", ""))
        if url_substring in url:
            request_id = event.get("params", {}).get("requestId")
            if request_id:
                request_ids.add(request_id)

    for event in events:
        if event.get("method") != "Network.requestWillBeSentExtraInfo":
            continue
        params = event.get("params", {})
        if params.get("requestId") in request_ids:
            return {
                "requestId": params.get("requestId"),
                "headers": params.get("headers", {}),
                "associatedCookies": params.get("associatedCookies", []),
                "connectTiming": params.get("connectTiming"),
                "siteHasCookieInOtherPartition": params.get("siteHasCookieInOtherPartition"),
            }
    return {}


def extract_response_summary(events: list[dict[str, Any]], url_substring: str) -> dict[str, Any]:
    for event in events:
        if event.get("method") != "Network.responseReceived":
            continue
        response = event.get("params", {}).get("response", {})
        url = str(response.get("url", ""))
        if url_substring in url:
            return {
                "requestId": event.get("params", {}).get("requestId"),
                "url": url,
                "status": response.get("status"),
                "statusText": response.get("statusText"),
                "headers": response.get("headers", {}),
            }
    return {}


def merge_request_diagnostics(events: list[dict[str, Any]], url_substring: str) -> dict[str, Any]:
    request_snapshot = extract_request_headers(events, url_substring)
    extra_info = extract_request_extra_info(events, url_substring)
    response_snapshot = extract_response_summary(events, url_substring)

    unified_headers = {}
    unified_headers.update(request_snapshot.get("headers", {}))
    unified_headers.update(extra_info.get("headers", {}))

    return {
        "requestId": request_snapshot.get("requestId") or extra_info.get("requestId") or response_snapshot.get("requestId"),
        "url": request_snapshot.get("url") or response_snapshot.get("url"),
        "method": request_snapshot.get("method"),
        "headers": unified_headers,
        "postData": request_snapshot.get("postData"),
        "associatedCookies": extra_info.get("associatedCookies", []),
        "extraInfo": {
            "connectTiming": extra_info.get("connectTiming"),
            "siteHasCookieInOtherPartition": extra_info.get("siteHasCookieInOtherPartition"),
        },
        "response": {
            "status": response_snapshot.get("status"),
            "statusText": response_snapshot.get("statusText"),
            "headers": response_snapshot.get("headers", {}),
        },
    }


def wait_for_required_cookies(driver: WebDriver, required_names: list[str], timeout: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_cookie_map: dict[str, str] = {}

    while time.time() < deadline:
        cookie_map = {
            cookie.get("name"): cookie.get("value")
            for cookie in driver.get_cookies()
            if cookie.get("name")
        }
        last_cookie_map = cookie_map
        missing = [name for name in required_names if not cookie_map.get(name)]
        if not missing:
            return {
                "ready": True,
                "cookie_map": cookie_map,
                "missing_required_cookies": [],
                "elapsed_seconds": timeout - max(0, deadline - time.time()),
            }
        time.sleep(0.5)

    return {
        "ready": False,
        "cookie_map": last_cookie_map,
        "missing_required_cookies": [name for name in required_names if not last_cookie_map.get(name)],
        "elapsed_seconds": timeout,
    }


def wait_for_navigation_or_cookies(driver: WebDriver, wait: WebDriverWait, timeout: int) -> dict[str, Any]:
    started_at = time.time()
    initial_url = driver.current_url
    initial_iframe_count = driver.execute_script("return document.querySelectorAll('iframe').length")

    cookie_result = wait_for_required_cookies(driver, list(REQUIRED_APP_COOKIES), timeout=timeout)
    changed_url = driver.current_url != initial_url
    current_iframe_count = driver.execute_script("return document.querySelectorAll('iframe').length")
    iframe_added = current_iframe_count > initial_iframe_count

    if changed_url:
        try:
            wait.until(lambda current_driver: current_driver.execute_script("return document.readyState") == "complete")
        except TimeoutException:
            logging.info("La URL cambió durante el warm-up, pero el documento no llegó a estado complete dentro del tiempo de espera.")

    return {
        "ready": cookie_result["ready"],
        "cookie_map": cookie_result["cookie_map"],
        "missing_required_cookies": cookie_result["missing_required_cookies"],
        "elapsed_seconds": round(time.time() - started_at, 2),
        "url_changed": changed_url,
        "initial_url": initial_url,
        "current_url": driver.current_url,
        "iframe_added": iframe_added,
        "initial_iframe_count": initial_iframe_count,
        "current_iframe_count": current_iframe_count,
    }


def infer_blocking_hypothesis(
    warmup: dict[str, Any],
    landing_navigation_diagnostics: dict[str, Any],
    navigation_mode: str,
    response_snapshot: dict[str, Any],
    relevant_header_differences: list[dict[str, Any]],
    relevant_cookie_differences: list[dict[str, Any]],
) -> str:
    detected_navigation_type = landing_navigation_diagnostics.get("detected_navigation_type")
    status = response_snapshot.get("status")

    if warmup.get("missing_required_cookies"):
        if detected_navigation_type == "none":
            return "landing_without_visible_login_transition"
        if detected_navigation_type == "script_hint":
            return "redirect_or_script_navigation_not_reproduced"
        if navigation_mode == "direct_fallback":
            return "redirect_or_script_navigation_not_reproduced"
        return "missing_app_session_cookies"
    if status == 403 and any(
        difference["header"] in {"sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "cookie"}
        for difference in relevant_header_differences
    ):
        return "header_mismatch"
    if status == 403 and relevant_cookie_differences:
        return "missing_app_session_cookies"
    return "unknown"


def classify_blocking_reason(
    *,
    stage: str,
    status: int | None,
    cookie_map: dict[str, str] | None,
    response_headers: dict[str, Any] | None,
    response_body_excerpt: str = "",
    login_rendered: bool = False,
    post_login_loaded: bool = False,
) -> str:
    cookie_map = cookie_map or {}
    headers = normalize_headers(response_headers)
    body = (response_body_excerpt or "").lower()
    missing_required = [name for name in REQUIRED_APP_COOKIES if not cookie_map.get(name)]
    has_edge_cookie = any(cookie_map.get(name) for name in EDGE_COOKIE_NAMES)
    edge_header_text = " ".join(str(headers.get(name, "")) for name in ("server", "x-iinfo", "via", "x-cache")).lower()
    edge_body_markers = (
        "imperva",
        "incapsula",
        "access denied",
        "request unsuccessful",
        "blocked",
        "forbidden",
        "pardon our interruption",
        "acceso restringido",
        "reese",
    )

    if any(marker in body for marker in edge_body_markers):
        return "waf_or_cdn_rejected"
    if post_login_loaded:
        return "unknown"
    if status in BLOCKING_STATUS_CODES:
        if any(marker in body for marker in edge_body_markers) or "incap" in edge_header_text or "imperva" in edge_header_text:
            return "waf_or_cdn_rejected"
        return "waf_or_cdn_rejected"
    if has_edge_cookie and missing_required and not login_rendered:
        return "missing_app_session_cookie"
    if missing_required and not has_edge_cookie and not login_rendered:
        return "missing_edge_cookie"
    if stage == "login_loaded" and login_rendered:
        return "unknown"
    if stage == "authenticated" and not post_login_loaded:
        return "post_login_navigation_failed"
    if stage == "failed" and login_rendered:
        return "login_post_rejected"
    if not login_rendered:
        return "login_not_rendered"
    return "unknown"


def build_waf_log_lookup(
    *,
    run_id: str,
    timestamp_utc: str,
    url: str | None,
    status: int | None,
    cookie_map: dict[str, str] | None,
    response_headers: dict[str, Any] | None,
) -> dict[str, Any]:
    headers = response_headers or {}
    return {
        "timestamp_utc": timestamp_utc,
        "run_id": run_id,
        "url": url,
        "status": status,
        "cookie_names": summarize_cookie_map(cookie_map).get("present_cookie_names", []),
        "correlation_ids": extract_correlation_ids(headers),
        "response_headers": filter_headers_for_evidence(headers),
    }


def build_evidence(
    *,
    request_snapshot: dict[str, Any] | None,
    response_snapshot: dict[str, Any] | None,
    cookie_map: dict[str, str] | None,
    response_body_excerpt: str = "",
    network_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    request_headers = (request_snapshot or {}).get("headers", {})
    response_headers = (response_snapshot or {}).get("headers", {})
    return {
        "status": (response_snapshot or {}).get("status"),
        "statusText": (response_snapshot or {}).get("statusText"),
        "url": (response_snapshot or {}).get("url") or (request_snapshot or {}).get("url"),
        "requestId": (response_snapshot or {}).get("requestId") or (request_snapshot or {}).get("requestId"),
        "request_method": (request_snapshot or {}).get("method") or (response_snapshot or {}).get("method"),
        "request_headers": filter_headers_for_evidence(request_headers),
        "response_headers": filter_headers_for_evidence(response_headers),
        "correlation_ids": extract_correlation_ids(response_headers),
        "cookies": summarize_cookie_map(cookie_map),
        "response_body_excerpt": response_body_excerpt[:1500],
        "network_events": summarize_network_events(network_events or []),
    }


def is_login_rendered(driver: WebDriver) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const hasPassword = Boolean(document.querySelector('input[type="password"]'));
                const hasLoginForm = Array.from(document.forms || []).some((form) =>
                    /Login\\.action|login/i.test(form.action || '') || /login/i.test(form.id || '') || /login/i.test(form.name || '')
                );
                return hasPassword || hasLoginForm;
                """
            )
        )
    except JavascriptException:
        return False


def is_post_login_loaded(driver: WebDriver) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const hasPassword = Boolean(document.querySelector('input[type="password"]'));
                const urlLooksLoggedIn = !/Login\\.action/i.test(window.location.href);
                const bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                const hasFailureText = /credencial|password|contraseña|usuario|login|ingresar/.test(bodyText) && hasPassword;
                return urlLooksLoggedIn && !hasPassword && !hasFailureText && document.readyState === 'complete';
                """
            )
        )
    except JavascriptException:
        return False


def wait_for_post_login_state(driver: WebDriver, timeout: int = POST_LOGIN_WAIT_SECONDS) -> dict[str, Any]:
    started_at = time.time()
    while time.time() - started_at < timeout:
        if is_post_login_loaded(driver):
            return {
                "post_login_loaded": True,
                "elapsed_seconds": round(time.time() - started_at, 2),
                "current_url": driver.current_url,
            }
        time.sleep(0.5)
    return {
        "post_login_loaded": False,
        "elapsed_seconds": round(time.time() - started_at, 2),
        "current_url": driver.current_url,
    }


def submit_login_form(driver: WebDriver, username: str, password: str) -> dict[str, Any]:
    try:
        return driver.execute_script(
            """
            const usernameValue = arguments[0];
            const passwordValue = arguments[1];
            const inputs = Array.from(document.querySelectorAll('input'));
            const passwordInput = inputs.find((input) => (input.type || '').toLowerCase() === 'password');
            const usernameInput =
                document.querySelector('input[name="loginForm.username"]') ||
                inputs.find((input) => /user|usuario|rut|login|email|mail/i.test(`${input.name || ''} ${input.id || ''} ${input.autocomplete || ''}`)) ||
                inputs.find((input) => ['text', 'email', ''].includes((input.type || '').toLowerCase()));
            if (!usernameInput || !passwordInput) {
                return { submitted: false, reason: 'login_fields_not_found' };
            }
            const setValue = (element, value) => {
                element.focus();
                element.value = value;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            };
            setValue(usernameInput, usernameValue);
            setValue(passwordInput, passwordValue);
            const form = passwordInput.form || usernameInput.form;
            if (form) {
                if (form.requestSubmit) {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
                return { submitted: true, method: 'form_submit' };
            }
            const submitButton = document.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
            if (submitButton) {
                submitButton.click();
                return { submitted: true, method: 'button_click' };
            }
            return { submitted: false, reason: 'submit_control_not_found' };
            """,
            username,
            password,
        )
    except JavascriptException as exc:
        return {"submitted": False, "reason": "javascript_exception", "error": str(exc)}


class ChromeService:
    def __init__(self):
        self.headless = False
        self.profile = CHROME_PROFILE_STAGING
        self.diagnostic_mode = True
        self.run_id = new_run_id()

    def prepare_browser_context(self) -> dict[str, Any]:
        chrome = self.get_chrome(self.headless, self.profile, self.run_id)
        wait = WebDriverWait(chrome, timeout=20, poll_frequency=0.5)
        runtime_profile = self.capture_browser_runtime_profile(chrome)
        bootstrap = self.inject_bootstrap_cookies(chrome, wait)
        return {
            "chrome": chrome,
            "wait": wait,
            "run_id": self.run_id,
            "started_at_utc": now_utc_iso(),
            "runtime_profile": runtime_profile,
            "bootstrap_cookies": bootstrap,
        }

    def inject_bootstrap_cookies(self, chrome: WebDriver, wait: WebDriverWait) -> dict[str, Any]:
        cookie_map = parse_cookie_header(os.getenv(ITAU_BOOTSTRAP_COOKIES_ENV))
        if not cookie_map:
            return {
                "attempted": False,
                "injected_cookie_names": [],
                "present_after_injection": [],
            }

        chrome.get("https://sac.itau.cl/")
        try:
            self.wait_for_document_ready(chrome, wait)
        except TimeoutException:
            logging.info("El documento base no llego a complete antes de inyectar cookies bootstrap.")

        injected_names: list[str] = []
        failed_names: list[str] = []
        for name, value in cookie_map.items():
            try:
                chrome.add_cookie(
                    {
                        "name": name,
                        "value": value,
                        "domain": "sac.itau.cl",
                        "path": "/",
                        "secure": True,
                    }
                )
                injected_names.append(name)
            except Exception:
                failed_names.append(name)
                logging.exception("No fue posible inyectar cookie bootstrap %s.", name)

        present = build_cookie_snapshot(chrome.get_cookies())
        return {
            "attempted": True,
            "injected_cookie_names": injected_names,
            "failed_cookie_names": failed_names,
            "present_after_injection": [name for name in injected_names if present.get(name)],
        }

    @staticmethod
    def capture_browser_runtime_profile(chrome: WebDriver) -> dict[str, Any]:
        try:
            return chrome.execute_script(
                """
                const uaData = navigator.userAgentData
                    ? {
                        brands: navigator.userAgentData.brands || [],
                        mobile: navigator.userAgentData.mobile,
                        platform: navigator.userAgentData.platform
                    }
                    : null;
                return {
                    user_agent: navigator.userAgent,
                    language: navigator.language,
                    languages: navigator.languages || [],
                    platform: navigator.platform,
                    webdriver: navigator.webdriver,
                    user_agent_data: uaData,
                    viewport: {
                        width: window.innerWidth,
                        height: window.innerHeight,
                        device_pixel_ratio: window.devicePixelRatio
                    }
                };
                """
            )
        except JavascriptException:
            logging.exception("No fue posible capturar el perfil runtime de Chrome.")
            return {}

    @staticmethod
    def wait_for_document_ready(chrome: WebDriver, wait: WebDriverWait) -> None:
        wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")

    def capture_landing_snapshot(self, chrome: WebDriver) -> dict[str, Any]:
        return chrome.execute_script(
            """
            const html = document.documentElement ? document.documentElement.outerHTML : '';
            return {
                url: window.location.href,
                title: document.title || '',
                document_ready_state: document.readyState,
                html_excerpt: html.slice(0, 4000),
                body_text_excerpt: (document.body ? document.body.innerText : '').slice(0, 1500)
            };
            """
        )

    def inspect_landing_navigation(self, chrome: WebDriver) -> dict[str, Any]:
        try:
            return chrome.execute_script(
                """
                const navigationSignals = {
                    location_href: window.location.href,
                    navigation_entries: (performance.getEntriesByType('navigation') || []).map((entry) => ({
                        type: entry.type || '',
                        name: entry.name || ''
                    })).slice(0, 5),
                    window_location_mentions: 0,
                    history_mentions: 0
                };
                const scripts = Array.from(document.scripts || []);
                const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 25).map((element) => ({
                    text: (element.innerText || '').trim().slice(0, 120),
                    href: element.href,
                    target: element.target || ''
                }));
                const forms = Array.from(document.forms || []).slice(0, 10).map((form) => ({
                    action: form.action || '',
                    method: (form.method || 'get').toLowerCase(),
                    id: form.id || '',
                    name: form.name || ''
                }));
                const iframes = Array.from(document.querySelectorAll('iframe[src]')).slice(0, 10).map((frame) => ({
                    src: frame.src,
                    id: frame.id || '',
                    name: frame.name || ''
                }));
                const metaRefresh = Array.from(document.querySelectorAll('meta[http-equiv]'))
                    .filter((meta) => (meta.getAttribute('http-equiv') || '').toLowerCase() === 'refresh')
                    .map((meta) => meta.getAttribute('content') || '');
                const scriptHints = scripts
                    .map((script, index) => {
                        const content = script.innerText || '';
                        const source = script.src || '';
                        const combined = source + ' ' + content;
                        if (!/Login\\.action|login|sfiler|window\\.location|location\\.href|replaceState|pushState/i.test(combined)) {
                            return null;
                        }
                        return {
                            index,
                            src: source,
                            excerpt: content.slice(0, 500),
                            mentions_window_location: /window\\.location|location\\.href/i.test(combined),
                            mentions_history_api: /replaceState|pushState/i.test(combined)
                        };
                    })
                    .filter(Boolean)
                    .slice(0, 12);
                navigationSignals.window_location_mentions = scriptHints.filter((hint) => hint.mentions_window_location).length;
                navigationSignals.history_mentions = scriptHints.filter((hint) => hint.mentions_history_api).length;
                const candidateTargets = [];
                for (const link of links) {
                    if (/Login\\.action|login|sfiler/i.test(link.href) || /login|ingresar|acceder/i.test(link.text)) {
                        candidateTargets.push({ type: 'link', value: link.href || link.text });
                    }
                }
                for (const form of forms) {
                    if (/Login\\.action|login|sfiler/i.test(form.action)) {
                        candidateTargets.push({ type: 'form', value: form.action });
                    }
                }
                for (const frame of iframes) {
                    if (/Login\\.action|login|sfiler/i.test(frame.src)) {
                        candidateTargets.push({ type: 'iframe', value: frame.src });
                    }
                }
                for (const refresh of metaRefresh) {
                    if (/Login\\.action|login|sfiler/i.test(refresh)) {
                        candidateTargets.push({ type: 'meta_refresh', value: refresh });
                    }
                }
                let detectedNavigationType = 'none';
                if (metaRefresh.length) {
                    detectedNavigationType = 'meta_refresh';
                } else if (iframes.length) {
                    detectedNavigationType = 'iframe';
                } else if (forms.some((form) => form.action)) {
                    detectedNavigationType = 'form';
                } else if (links.some((link) => link.href)) {
                    detectedNavigationType = 'link';
                } else if (scriptHints.length) {
                    detectedNavigationType = 'script_hint';
                }
                return {
                    detected_navigation_type: detectedNavigationType,
                    candidate_targets: candidateTargets.slice(0, 20),
                    forms,
                    links,
                    iframes,
                    meta_refresh: metaRefresh,
                    script_hints: scriptHints,
                    navigation_signals: navigationSignals
                };
                """
            )
        except JavascriptException:
            logging.exception("No fue posible inspeccionar la landing para extraer el mecanismo de navegación.")
            return {
                "detected_navigation_type": "inspection_error",
                "candidate_targets": [],
                "forms": [],
                "links": [],
                "iframes": [],
                "meta_refresh": [],
                "script_hints": [],
                "navigation_signals": {},
            }

    def warm_up_session(self, chrome: WebDriver, wait: WebDriverWait) -> dict[str, Any]:
        logging.info("Abriendo landing inicial para obtener cookies base...")
        chrome.get(LANDING_URL)
        self.wait_for_document_ready(chrome, wait)
        navigation_or_cookie_state = wait_for_navigation_or_cookies(chrome, wait, timeout=8)

        cookies = chrome.get_cookies()
        cookie_names = {cookie.get("name") for cookie in cookies}
        important_cookies = [name for name in IMPORTANT_COOKIE_NAMES if name in cookie_names]
        missing_required = navigation_or_cookie_state["missing_required_cookies"]
        session_stage = infer_session_stage(navigation_or_cookie_state["cookie_map"], missing_required)

        logging.info("Landing cargada. Cookies detectadas: %s", sorted(cookie_names))
        logging.info("Cookies requeridas faltantes: %s", missing_required)
        return {
            "cookies": cookies,
            "cookie_map": navigation_or_cookie_state["cookie_map"],
            "important_cookie_names": important_cookies,
            "required_cookie_names": list(REQUIRED_APP_COOKIES),
            "missing_required_cookies": missing_required,
            "session_stage": session_stage,
            "ready_for_login": not missing_required,
            "current_url_after_warmup": navigation_or_cookie_state["current_url"],
            "document_ready_state": chrome.execute_script("return document.readyState"),
            "warmup_elapsed_seconds": navigation_or_cookie_state["elapsed_seconds"],
            "url_changed_during_warmup": navigation_or_cookie_state["url_changed"],
            "iframe_added_during_warmup": navigation_or_cookie_state["iframe_added"],
        }

    def attempt_real_navigation(
        self,
        chrome: WebDriver,
        wait: WebDriverWait,
        landing_navigation_diagnostics: dict[str, Any],
    ) -> str:
        detected_navigation_type = landing_navigation_diagnostics.get("detected_navigation_type")
        if TARGET_URL_SUBSTRING in chrome.current_url:
            return "real_navigation"
        if detected_navigation_type in {"none", "inspection_error", "script_hint"}:
            return "direct_fallback"

        current_url = chrome.current_url
        try:
            if detected_navigation_type == "meta_refresh":
                wait.until(lambda driver: driver.current_url != current_url)
            elif detected_navigation_type == "iframe":
                iframe_sources = [iframe.get("src", "") for iframe in landing_navigation_diagnostics.get("iframes", [])]
                if any(TARGET_URL_SUBSTRING in src for src in iframe_sources):
                    return "iframe_detected"
                return "direct_fallback"
            elif detected_navigation_type == "form":
                submitted = chrome.execute_script(
                    """
                    const forms = Array.from(document.forms || []);
                    const form = forms.find((candidate) => /Login\\.action|login|sfiler/i.test(candidate.action || ''));
                    if (!form) {
                        return false;
                    }
                    form.submit();
                    return true;
                    """
                )
                if not submitted:
                    return "direct_fallback"
                wait.until(lambda driver: driver.current_url != current_url or TARGET_URL_SUBSTRING in driver.current_url)
            elif detected_navigation_type == "link":
                clicked = chrome.execute_script(
                    """
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const link = links.find((candidate) => /Login\\.action|login|sfiler/i.test(candidate.href || ''));
                    if (!link) {
                        return false;
                    }
                    link.click();
                    return true;
                    """
                )
                if not clicked:
                    return "direct_fallback"
                wait.until(lambda driver: driver.current_url != current_url or TARGET_URL_SUBSTRING in driver.current_url)
            else:
                return "direct_fallback"

            self.wait_for_document_ready(chrome, wait)
            return "real_navigation"
        except (JavascriptException, TimeoutException):
            logging.exception("No fue posible reproducir la navegación detectada desde la landing.")
            return "direct_fallback"

    def run_login_flow_legacy(self) -> dict[str, Any]:
        chrome = self.get_chrome(self.headless, self.profile)
        wait = WebDriverWait(chrome, timeout=20, poll_frequency=0.5)
        try:
            warmup = self.warm_up_session(chrome, wait)
            landing_snapshot = self.capture_landing_snapshot(chrome)
            landing_navigation_diagnostics = self.inspect_landing_navigation(chrome)
            navigation_mode = self.attempt_real_navigation(chrome, wait, landing_navigation_diagnostics)

            if navigation_mode == "direct_fallback":
                logging.info("No se detectó una transición visible al login; usando navegación directa como fallback diagnóstico...")
                chrome.get(LOGIN_URL)
                self.wait_for_document_ready(chrome, wait)
            elif navigation_mode == "iframe_detected":
                logging.info("Se detectó un iframe como mecanismo de navegación al login.")
            else:
                logging.info("La navegación hacia Login.action se realizó desde la landing.")

            time.sleep(2)

            events = collect_network_events(chrome)
            request_snapshot = merge_request_diagnostics(events, TARGET_URL_SUBSTRING)
            response_snapshot = request_snapshot.get("response", {})
            captured_cookie_map = build_cookie_snapshot(chrome.get_cookies())
            header_differences = compare_headers(REFERENCE_REQUEST_HEADERS, request_snapshot.get("headers", {}))
            relevant_header_differences = filter_relevant_header_differences(header_differences)
            cookie_differences = compare_cookies(REFERENCE_REQUIRED_COOKIES, captured_cookie_map)
            relevant_cookie_differences = filter_relevant_cookie_differences(cookie_differences)
            blocking_hypothesis = infer_blocking_hypothesis(
                warmup,
                landing_navigation_diagnostics,
                navigation_mode,
                response_snapshot,
                relevant_header_differences,
                relevant_cookie_differences,
            )

            result = {
                "landing_url": LANDING_URL,
                "login_url": LOGIN_URL,
                "final_url": chrome.current_url,
                "navigation_mode": navigation_mode,
                "warmup": warmup,
                "landing_snapshot": landing_snapshot,
                "landing_navigation_diagnostics": landing_navigation_diagnostics,
                "current_url_after_warmup": warmup["current_url_after_warmup"],
                "request_snapshot": request_snapshot,
                "response_snapshot": response_snapshot,
                "header_differences": header_differences,
                "relevant_header_differences": relevant_header_differences,
                "cookie_differences": cookie_differences,
                "relevant_cookie_differences": relevant_cookie_differences,
                "blocking_hypothesis": blocking_hypothesis,
            }

            if navigation_mode == "direct_fallback":
                sec_fetch_site = normalize_headers(request_snapshot.get("headers", {})).get("sec-fetch-site")
                logging.info(
                    "Fallback directo detectado. Sec-Fetch-Site observado: %s; este valor suele quedar en 'none' cuando la navegación no nace desde la landing.",
                    sec_fetch_site,
                )

            if self.diagnostic_mode:
                logging.info("Resumen warmup: %s", json.dumps(warmup, ensure_ascii=False, indent=2))
                logging.info("Landing snapshot: %s", json.dumps(landing_snapshot, ensure_ascii=False, indent=2))
                logging.info(
                    "Diagnóstico de navegación landing: %s",
                    json.dumps(landing_navigation_diagnostics, ensure_ascii=False, indent=2),
                )
                logging.info("Resumen request Login.action: %s", json.dumps(request_snapshot, ensure_ascii=False, indent=2))
                logging.info("Resumen response Login.action: %s", json.dumps(response_snapshot, ensure_ascii=False, indent=2))
                logging.info("Diferencias de headers: %s", json.dumps(header_differences, ensure_ascii=False, indent=2))
                logging.info(
                    "Diferencias de headers relevantes: %s",
                    json.dumps(relevant_header_differences, ensure_ascii=False, indent=2),
                )
                logging.info("Diferencias de cookies: %s", json.dumps(cookie_differences, ensure_ascii=False, indent=2))
                logging.info(
                    "Diferencias de cookies relevantes: %s",
                    json.dumps(relevant_cookie_differences, ensure_ascii=False, indent=2),
                )
                logging.info("Hipótesis de bloqueo: %s", blocking_hypothesis)

            return result
        except Exception:
            logging.exception("Error durante la ejecución")
            raise
        finally:
            chrome.quit()

    def load_login_page(self, chrome: WebDriver, wait: WebDriverWait) -> dict[str, Any]:
        warmup = self.warm_up_session(chrome, wait)
        landing_snapshot = self.capture_landing_snapshot(chrome)
        landing_navigation_diagnostics = self.inspect_landing_navigation(chrome)
        navigation_mode = self.attempt_real_navigation(chrome, wait, landing_navigation_diagnostics)

        if navigation_mode == "direct_fallback":
            logging.info("No se detecto una transicion visible al login; usando navegacion directa como fallback diagnostico...")
            chrome.get(LOGIN_URL)
            self.wait_for_document_ready(chrome, wait)
        elif navigation_mode == "iframe_detected":
            logging.info("Se detecto un iframe como mecanismo de navegacion al login.")
        else:
            logging.info("La navegacion hacia Login.action se realizo desde la landing.")

        time.sleep(2)
        events = collect_network_events(chrome)
        request_snapshot = merge_request_diagnostics(events, TARGET_URL_SUBSTRING)
        response_snapshot = request_snapshot.get("response", {})
        response_body_excerpt = extract_response_body_excerpt(chrome, response_snapshot.get("requestId"))
        captured_cookie_map = build_cookie_snapshot(chrome.get_cookies())
        login_rendered = is_login_rendered(chrome)
        stage = "login_loaded" if login_rendered else "landing"
        page_diagnostic_text = " ".join(
            str(landing_snapshot.get(key, ""))
            for key in ("title", "body_text_excerpt", "html_excerpt")
        )
        blocking_reason = classify_blocking_reason(
            stage=stage,
            status=response_snapshot.get("status"),
            cookie_map=captured_cookie_map,
            response_headers=response_snapshot.get("headers", {}),
            response_body_excerpt=response_body_excerpt or page_diagnostic_text,
            login_rendered=login_rendered,
        )

        return {
            "stage": stage,
            "login_rendered": login_rendered,
            "navigation_mode": navigation_mode,
            "warmup": {
                **warmup,
                "cookies": summarize_cookie_map(captured_cookie_map),
                "cookie_map": summarize_cookie_map(warmup.get("cookie_map", {})),
            },
            "landing_snapshot": sanitize_snapshot(landing_snapshot),
            "landing_navigation_diagnostics": landing_navigation_diagnostics,
            "request_snapshot": {
                **request_snapshot,
                "headers": filter_headers_for_evidence(request_snapshot.get("headers", {})),
                "associatedCookies": sanitize_associated_cookies(request_snapshot.get("associatedCookies", [])),
            },
            "response_snapshot": {
                **response_snapshot,
                "headers": filter_headers_for_evidence(response_snapshot.get("headers", {})),
            },
            "raw_response_snapshot": response_snapshot,
            "cookie_map": captured_cookie_map,
            "evidence": build_evidence(
                request_snapshot=request_snapshot,
                response_snapshot=response_snapshot,
                cookie_map=captured_cookie_map,
                response_body_excerpt=response_body_excerpt or page_diagnostic_text[:1500],
                network_events=events,
            ),
            "blocking_reason": blocking_reason,
            "network_events": summarize_network_events(events),
        }

    def authenticate_and_validate_first_view(self, chrome: WebDriver, wait: WebDriverWait) -> dict[str, Any]:
        try:
            config = load_login_config_from_env()
        except ValueError as exc:
            return {
                "success": False,
                "stage": "failed",
                "blocking_reason": "login_post_rejected",
                "auth_attempt": {"submitted": False, "reason": str(exc)},
                "evidence": {
                    "status": None,
                    "url": chrome.current_url,
                    "cookies": summarize_cookie_map(build_cookie_snapshot(chrome.get_cookies())),
                },
            }

        collect_network_events(chrome)
        submitted = submit_login_form(chrome, config["username"], config["password"])
        if not submitted.get("submitted"):
            return {
                "success": False,
                "stage": "failed",
                "blocking_reason": "login_not_rendered",
                "auth_attempt": submitted,
                "evidence": {
                    "status": None,
                    "url": chrome.current_url,
                    "cookies": summarize_cookie_map(build_cookie_snapshot(chrome.get_cookies())),
                },
            }

        post_login_state = wait_for_post_login_state(chrome)
        events = collect_network_events(chrome)
        response_snapshot = find_latest_response(events, method="POST") or find_latest_response(events, TARGET_URL_SUBSTRING)
        response_body_excerpt = extract_response_body_excerpt(chrome, response_snapshot.get("requestId"))
        cookie_map = build_cookie_snapshot(chrome.get_cookies())
        post_login_loaded = bool(post_login_state.get("post_login_loaded"))
        stage = "post_login_loaded" if post_login_loaded else "failed"
        blocking_reason = classify_blocking_reason(
            stage="authenticated" if submitted.get("submitted") else stage,
            status=response_snapshot.get("status"),
            cookie_map=cookie_map,
            response_headers=response_snapshot.get("headers", {}),
            response_body_excerpt=response_body_excerpt,
            login_rendered=is_login_rendered(chrome),
            post_login_loaded=post_login_loaded,
        )
        if not post_login_loaded and blocking_reason == "unknown":
            blocking_reason = "login_post_rejected"

        return {
            "success": post_login_loaded,
            "stage": stage,
            "blocking_reason": blocking_reason,
            "auth_attempt": {
                "submitted": submitted.get("submitted"),
                "method": submitted.get("method"),
                "reason": submitted.get("reason"),
            },
            "post_login_state": post_login_state,
            "evidence": build_evidence(
                request_snapshot={"method": "POST", "url": LOGIN_URL, "headers": {}},
                response_snapshot=response_snapshot,
                cookie_map=cookie_map,
                response_body_excerpt=redact_sensitive_text(
                    response_body_excerpt,
                    [config["username"], config["password"]],
                ),
                network_events=events,
            ),
            "network_events": summarize_network_events(events),
        }

    def write_diagnostic_artifact(self, result: dict[str, Any], chrome: WebDriver | None = None) -> dict[str, Any]:
        diagnostic_dir = os.getenv(ITAU_DIAGNOSTIC_DIR_ENV, DEFAULT_DIAGNOSTIC_DIR)
        os.makedirs(diagnostic_dir, exist_ok=True)
        run_id = result.get("run_id") or self.run_id
        artifact_result = dict(result)

        if chrome is not None:
            screenshot_path = os.path.join(diagnostic_dir, f"itau_{run_id}.png")
            try:
                chrome.save_screenshot(screenshot_path)
                artifact_result["screenshot_path"] = screenshot_path
            except Exception:
                logging.exception("No fue posible guardar screenshot diagnostico.")

        artifact_path = os.path.join(diagnostic_dir, f"itau_{run_id}.json")
        artifact_result["artifact_path"] = artifact_path
        with open(artifact_path, "w", encoding="utf-8") as artifact_file:
            json.dump(artifact_result, artifact_file, ensure_ascii=False, indent=2, default=str)
        return {
            "artifact_path": artifact_path,
            "screenshot_path": artifact_result.get("screenshot_path"),
        }

    def run_login_flow(self) -> dict[str, Any]:
        context = self.prepare_browser_context()
        chrome = context["chrome"]
        wait = context["wait"]
        try:
            login_result = self.load_login_page(chrome, wait)
            raw_response_snapshot = login_result.pop("raw_response_snapshot", {})
            login_result.pop("cookie_map", None)
            success = False
            stage = login_result["stage"]
            blocking_reason = login_result["blocking_reason"]
            auth_result: dict[str, Any] | None = None

            if login_result["login_rendered"]:
                auth_result = self.authenticate_and_validate_first_view(chrome, wait)
                success = bool(auth_result.get("success"))
                stage = auth_result.get("stage", stage)
                blocking_reason = auth_result.get("blocking_reason", blocking_reason)

            response_headers = raw_response_snapshot.get("headers", {})
            status = login_result.get("evidence", {}).get("status")
            if auth_result:
                response_headers = auth_result.get("evidence", {}).get("response_headers", response_headers)
                status = auth_result.get("evidence", {}).get("status", status)

            result = {
                "success": success,
                "stage": stage,
                "blocking_reason": blocking_reason,
                "run_id": context["run_id"],
                "started_at_utc": context["started_at_utc"],
                "finished_at_utc": now_utc_iso(),
                "landing_url": LANDING_URL,
                "login_url": LOGIN_URL,
                "final_url": chrome.current_url,
                "browser_runtime_profile": context["runtime_profile"],
                "bootstrap_cookies": context["bootstrap_cookies"],
                "login": login_result,
                "auth": auth_result,
                "evidence": auth_result.get("evidence") if auth_result else login_result.get("evidence"),
                "waf_log_lookup": build_waf_log_lookup(
                    run_id=context["run_id"],
                    timestamp_utc=context["started_at_utc"],
                    url=chrome.current_url,
                    status=status,
                    cookie_map=build_cookie_snapshot(chrome.get_cookies()),
                    response_headers=response_headers,
                ),
            }
            artifact_paths = self.write_diagnostic_artifact(result, chrome)
            result.update(artifact_paths)

            if self.diagnostic_mode:
                logging.info("Resultado Itau: %s", json.dumps(result, ensure_ascii=False, indent=2, default=str))

            return result
        except Exception:
            logging.exception("Error durante la ejecucion")
            raise
        finally:
            chrome.quit()

    def run_http_login_flow(self) -> dict[str, Any]:
        config = load_login_config_from_env()
        session = create_http_session()

        warmup = warm_up_http_session(session)
        cookies_before_post = dict(warmup["cookie_map"])

        post_result = post_login(
            session,
            username=config["username"],
            password=config["password"],
            request_locale=config["request_locale"],
        )
        post_response = post_result["response"]
        redirect_followup = follow_domain_switch_if_present(session, post_result["raw_response"])
        cookies_after_post = build_cookie_map_from_session(session)
        cookie_differences = compare_cookies(REFERENCE_REQUIRED_COOKIES, cookies_after_post)
        relevant_cookie_differences = filter_relevant_cookie_differences(cookie_differences)
        header_differences = compare_headers(REFERENCE_POST_HEADERS, post_result["request"]["headers"])
        relevant_header_differences = filter_relevant_header_differences(header_differences)

        required_cookie_state = {
            "required_cookie_names": list(REQUIRED_APP_COOKIES),
            "missing_after_post": [name for name in REQUIRED_APP_COOKIES if not cookies_after_post.get(name)],
            "cookie_map": summarize_cookie_map(cookies_after_post),
            "session_stage": infer_session_stage(
                cookies_after_post,
                [name for name in REQUIRED_APP_COOKIES if not cookies_after_post.get(name)],
            ),
        }

        blocking_hypothesis = infer_http_blocking_hypothesis(
            warmup=warmup,
            post_response=post_response,
            redirect_followup=redirect_followup,
            relevant_cookie_differences=relevant_cookie_differences,
        )

        result = {
            "success": False,
            "stage": "http_diagnostic",
            "blocking_reason": classify_blocking_reason(
                stage="failed",
                status=post_response.get("status_code"),
                cookie_map=cookies_after_post,
                response_headers=post_response.get("headers", {}),
                login_rendered=False,
            ),
            "warmup": {
                **warmup,
                "headers": filter_headers_for_evidence(warmup.get("headers", {})),
                "cookie_map": summarize_cookie_map(warmup.get("cookie_map", {})),
            },
            "post_request": {
                **post_result["request"],
                "headers": filter_headers_for_evidence(post_result["request"].get("headers", {})),
                "cookies_before_post": summarize_cookie_map(post_result["request"].get("cookies_before_post", {})),
            },
            "post_response": {
                **post_response,
                "headers": filter_headers_for_evidence(post_response.get("headers", {})),
                "cookies_after_post": summarize_cookie_map(post_response.get("cookies_after_post", {})),
            },
            "redirect_followup": {
                **redirect_followup,
                "headers": filter_headers_for_evidence(redirect_followup.get("headers", {})),
                "cookie_map": summarize_cookie_map(redirect_followup.get("cookie_map", {})),
            },
            "cookies_before_post": summarize_cookie_map(cookies_before_post),
            "cookies_after_post": summarize_cookie_map(cookies_after_post),
            "required_cookie_state": required_cookie_state,
            "header_differences": header_differences,
            "relevant_header_differences": relevant_header_differences,
            "cookie_differences": sanitize_cookie_differences(cookie_differences),
            "relevant_cookie_differences": sanitize_cookie_differences(relevant_cookie_differences),
            "blocking_hypothesis": blocking_hypothesis,
            "waf_log_lookup": build_waf_log_lookup(
                run_id=self.run_id,
                timestamp_utc=now_utc_iso(),
                url=post_response.get("location") or LOGIN_URL,
                status=post_response.get("status_code"),
                cookie_map=cookies_after_post,
                response_headers=post_response.get("headers", {}),
            ),
        }

        if self.diagnostic_mode:
            logging.info("Warm-up HTTP: %s", json.dumps(warmup, ensure_ascii=False, indent=2))
            logging.info("POST request: %s", json.dumps(post_result["request"], ensure_ascii=False, indent=2))
            logging.info("POST response: %s", json.dumps(post_response, ensure_ascii=False, indent=2))
            logging.info("Redirect follow-up: %s", json.dumps(redirect_followup, ensure_ascii=False, indent=2))
            logging.info("Estado cookies requeridas: %s", json.dumps(required_cookie_state, ensure_ascii=False, indent=2))
            logging.info("Hipótesis HTTP: %s", blocking_hypothesis)

        return result

    def test_itau(self) -> dict[str, Any]:
        return self.run_login_flow()

    def test_itau_http(self) -> dict[str, Any]:
        return self.run_http_login_flow()

    @staticmethod
    def get_chrome(headless: bool, profile: dict[str, Any] | None = None, run_id: str | None = None) -> WebDriver:
        logging.info("Iniciando navegador Chrome para Itau...")
        options = build_chrome_options(headless=headless, profile=profile)
        logging.info("Configurando ChromeDriver para ambiente local...")
        driver = webdriver.Chrome(options=options)
        configure_network_context(driver, profile or CHROME_PROFILE_STAGING, run_id=run_id)
        return driver


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service = ChromeService()
    result = service.test_itau()
    print(json.dumps(result, ensure_ascii=False, indent=2))
