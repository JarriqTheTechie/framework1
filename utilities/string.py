import urllib.parse


def encode_uri(string: str) -> str:
    return urllib.parse.quote(string)
