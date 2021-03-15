import random


def random_mac_address() -> str:
    """Generate a random MAC address.

    The MAC address will have a 1 in its least significant bit, indicating it
    to be a locally administered address.
    """
    return "02:00:00:%02x:%02x:%02x" % (random.randint(0, 255),
                                        random.randint(0, 255),
                                        random.randint(0, 255))
