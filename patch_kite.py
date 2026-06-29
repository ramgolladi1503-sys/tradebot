import re

with open("core/kite_client.py", "r") as f:
    content = f.read()

content = content.replace(
"""        except Exception as e:
            logger.exception("instruments_fetch_failed exchange=%s err=%s", exchange, e)
            if cached:
                return cached.get("data", [])""",
"""        except Exception as e:
            logger.exception("instruments_fetch_failed exchange=%s err=%s", exchange, e)
            if cached:
                return cached.get("data", [])
            return []""")

with open("core/kite_client.py", "w") as f:
    f.write(content)
