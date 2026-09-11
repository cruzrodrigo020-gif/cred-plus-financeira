import json
import os
import urllib.error
import urllib.request

from app import v14_public


def _safe_error_body(exc) -> str:
    try:
        raw = exc.read().decode('utf-8', errors='replace')
    except Exception:
        raw = ''
    if not raw:
        return ''
    try:
        data = json.loads(raw)
        err = data.get('error', {}) if isinstance(data, dict) else {}
        safe = {
            'message': err.get('message'),
            'type': err.get('type'),
            'code': err.get('code'),
            'error_subcode': err.get('error_subcode'),
            'fbtrace_id': err.get('fbtrace_id'),
        }
        return json.dumps(safe, ensure_ascii=False)
    except Exception:
        return raw[:1000]


def send_whatsapp_confirmation_diagnostic(client_id: int, name: str, whatsapp: str) -> None:
    if not whatsapp or not v14_public.whatsapp_confirmation_configured():
        print(f'PUBLIC_CONFIRM_WHATSAPP_ERROR client_id={client_id} error=not_configured')
        return

    phone = v14_public.normalize_whatsapp(whatsapp)
    if len(phone) < 12:
        print(f'PUBLIC_CONFIRM_WHATSAPP_ERROR client_id={client_id} error=invalid_phone')
        return

    graph_version = os.getenv('WHATSAPP_GRAPH_VERSION', '').strip()
    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
    template_name = os.getenv('WHATSAPP_TEMPLATE_NAME', '').strip()
    template_lang = os.getenv('WHATSAPP_TEMPLATE_LANG', 'pt_BR').strip() or 'pt_BR'

    payload = {
        'messaging_product': 'whatsapp',
        'to': phone,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': template_lang},
            'components': [
                {
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': name[:60]}],
                }
            ],
        },
    }

    request = urllib.request.Request(
        f'https://graph.facebook.com/{graph_version}/{phone_number_id}/messages',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode('utf-8', errors='replace')
        message_id = ''
        try:
            parsed = json.loads(body)
            messages = parsed.get('messages') or []
            if messages:
                message_id = messages[0].get('id', '')
        except Exception:
            pass
        print(f'PUBLIC_CONFIRM_WHATSAPP_OK client_id={client_id} message_id={message_id}')
    except urllib.error.HTTPError as exc:
        detail = _safe_error_body(exc)
        print(f'PUBLIC_CONFIRM_WHATSAPP_ERROR client_id={client_id} error=HTTPError status={exc.code} detail={detail}')
    except urllib.error.URLError as exc:
        print(f'PUBLIC_CONFIRM_WHATSAPP_ERROR client_id={client_id} error=URLError reason={str(exc.reason)[:300]}')
    except TimeoutError:
        print(f'PUBLIC_CONFIRM_WHATSAPP_ERROR client_id={client_id} error=TimeoutError')
    except Exception as exc:
        print(f'PUBLIC_CONFIRM_WHATSAPP_ERROR client_id={client_id} error={type(exc).__name__} detail={str(exc)[:300]}')


v14_public.send_whatsapp_confirmation = send_whatsapp_confirmation_diagnostic
