import ipaddress

network_mappings = {}
interface_mapings = {}

def network_to_interface (network: str, interface: str) -> bool:
    """Add a network to interface mapping."""
    try:
        network_object = ipaddress.IPv4Network(network)
    except ValueError as e:
        print(f"network_to_interface(): invaldid network {network}: '{e}'")
        return False

    if network_object in network_mappings:
        print(f"network_to_interface(): invaldid network {network}: '{e}'")
        return False

    network_mappings[network_object] = interface

    return True

def interface_map (old_interface: str, new_interface: str) -> bool:
    """Create an interface name translation."""    
    if old_interface in interface_mapings:
        return False

    interface_mapings[old_interface] = new_interface

    return True

def ip_to_interface (ip_address: str) -> str | None:
    """Lookup an IP to interface mapping."""
    try:
        ip_object = ipaddress.IPv4Address(ip_address)
    except ValueError as e:
        print(f"ip_to_interface(): {ip_address} ignored: '{e}'")
        return None

    for (network, interface) in network_mappings.items():
        if ip_object in network:
            return interface

    return None

def interface_xlat (old_interface: str) -> str:
    """Translate an interface name."""
    return interface_mapings[old_interface] if old_interface in interface_mapings else None
