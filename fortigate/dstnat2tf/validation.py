"""Validators Module."""
import ipaddress
import logging

def valid_ip(ip_address: str) -> ipaddress.IPv4Address | bool:
    """Validate IP address and return it as an ipv4_address object."""
    try:
        ipv4_address = ipaddress.IPv4Address(ip_address)
    except ValueError as exception:
        logging.debug(
            "invalid ip '%s': '%s'",
            ip_address,
            exception)
        return False

    return ipv4_address


def valid_network(network_address: str) -> ipaddress.IPv4Network | bool:
    """Validate network address and return it as a ipv4_network object."""
    try:
        ipv4_network = ipaddress.IPv4Network(network_address)
    except ValueError as exception:
        logging.debug(
            "valid_network(): invalid network '%s': %s", 
            network_address,
            exception)
        return False

    return ipv4_network


def valid_fortigate_interface (interface_name: str) -> bool:
    """Return true if 'interface' is a valid FortiGate interface name."""
    rx_fortigate_interface = re.compile(r"[0-9-_ A-Z]{1,15}", flags=re.IGNORECASE)
    return rx_fortigate_interface.fullmatch(interface_name) is not None

