import urllib.request
import urllib.error
import urllib.parse
import json
import time

class UpstoxAPIError(Exception):
    def __init__(self, code, reason):
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")

class UpstoxClient:
    def __init__(self, token):
        self.token = token
        
    def get(self, url, max_retries=3):
        if not self.token:
            raise UpstoxAPIError("MISSING_TOKEN", "AUTHENTICATION_ROTATION_REQUIRED")
            
        headers = {
            "Accept": "application/json",
            "Api-Version": "3.0",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "curl/8.4.0"
        }
        req = urllib.request.Request(url, headers=headers)
        attempt = 0
        while attempt < max_retries:
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read()
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise UpstoxAPIError("AUTHENTICATION_FAILED", "401")
                elif e.code == 403:
                    body = e.read()
                    try:
                        j = json.loads(body)
                        if any(err.get('errorCode') == 'UDAPI1149' for err in j.get('errors', [])):
                            raise UpstoxAPIError("PLUS_ENTITLEMENT_FAILED", "UDAPI1149")
                    except Exception:
                        pass
                    raise UpstoxAPIError("FORBIDDEN", "403")
                elif e.code == 429:
                    r = int(e.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(r)
                    attempt += 1
                elif e.code in (500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    attempt += 1
                else:
                    raise UpstoxAPIError("HTTP_ERROR", str(e.code))
            except Exception as e:
                time.sleep(2 ** attempt)
                attempt += 1
                
        raise UpstoxAPIError("MAX_RETRIES", "Retries exceeded")\n