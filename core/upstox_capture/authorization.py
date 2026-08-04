import requests
import logging

logger = logging.getLogger("upstox_auth")

def preflight_auth(token: str) -> bool:
    """Perform a harmless authorization preflight check against the Upstox API."""
    url = "https://api.upstox.com/v2/user/profile"
    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            logger.info("Preflight auth successful.")
            return True
        else:
            logger.error(
                f"Preflight auth failed. Status: {resp.status_code}, Response: {resp.text}"
            )
            if "UDAPI1221" in resp.text:
                logger.error(
                    "=> UPSTOX IP WHITELIST ERROR: The API key does not allow this machine's IP. "
                    "Please whitelist this IP in the Upstox Developer Console."
                )
            return False
    except Exception as e:
        logger.error(f"Preflight auth exception: {e}")
        return False
