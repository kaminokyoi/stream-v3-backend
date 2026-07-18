"""User-related utilities: client-IP extraction and IP geolocation.

get_location_info performs a blocking HTTP call to ip-api.com and should
therefore only be invoked from an asynchronous Celery task.
"""
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract the client IP from a request (X-Forwarded-For aware)."""
    if not request:
        return "Inconnu"
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_location_info(ip):
    """Resolve an IP to a human-readable location string (blocking HTTP call)."""
    if not ip or ip in ['127.0.0.1', 'localhost', '::1']:
        return "Localhost (Développement)"
    try:
        url = f"http://ip-api.com/json/{ip}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2.0) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                city = data.get('city')
                region = data.get('regionName')
                country = data.get('country')
                isp = data.get('isp')
                return f"{city}, {region}, {country} (FSI: {isp})"
    except Exception as e:
        logger.warning(f"Failed to fetch IP location: {e}")
    return "Inconnue"
