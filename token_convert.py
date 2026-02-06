from kiteconnect import KiteConnect

api_key = "yfqy95s55t2noi2n"
api_secret = "7abtdl7h6b722vy7fu7xhzy28a847aea"
request_token = "HYpGxf7uQfz12iJl61XXglXoKjUs7FUI"

kite = KiteConnect(api_key=api_key)
data = kite.generate_session(request_token, api_secret=api_secret)

access_token = data["access_token"]
print(access_token)

