import upstox_client.feeder.proto.MarketDataFeedV3_pb2 as pb
from google.protobuf import json_format

def decode_feed_response(binary_data: bytes) -> dict:
    """Decodes raw binary protobuf frame into a python dictionary."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(binary_data)
    # MessageToDict handles converting protobuf to a native dict format
    return json_format.MessageToDict(feed_response)
