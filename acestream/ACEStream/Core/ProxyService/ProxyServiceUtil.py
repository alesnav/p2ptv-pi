#Embedded file name: ACEStream\Core\ProxyService\ProxyServiceUtil.pyo
import string
import random

def generate_proxy_challenge():
    chars = string.letters + string.digits
    challenge = ''
    for i in range(8):
        challenge = challenge + random.choice(chars)

    return challenge


def decode_challenge_from_peerid(peerid):
    return peerid[12:20]


def encode_challenge_in_peerid(peerid, challenge):
    encoded_peer_id = peerid[:12] + challenge
    return encoded_peer_id
