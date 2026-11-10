"""Display-only projection of verified platform claims, never an authority source."""
from urllib.parse import urlsplit


def profile_claims(claims):
    fields = {'email': 'email', 'phone': 'phone', 'preferred_username': 'username',
              'active_org_name': 'org_name', 'active_org_type': 'org_type',
              'active_workspace_name': 'workspace_name'}
    result = {}
    for source, target in fields.items():
        value = claims.get(source)
        if isinstance(value, str) and 0 < len(value) <= 500 and not any(ord(c) < 32 for c in value):
            result[target] = value
    phone = claims.get('phone_number')
    if 'phone' not in result and isinstance(phone, str) and len(phone) <= 80 and not any(ord(c) < 32 for c in phone):
        result['phone'] = phone
    for name in ('email_verified', 'phone_verified'):
        value = claims.get(name)
        if type(value) is bool:
            result[name] = value
    picture = claims.get('picture')
    if isinstance(picture, str) and len(picture) <= 2048 and not any(ord(c) < 32 for c in picture):
        try:
            parsed = urlsplit(picture)
            if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
                result['avatar_url'] = picture
        except ValueError:
            pass
    return result
