import csv
import shlex
import ipaddress
from sys import exit

from collections import defaultdict

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


# configuration
RSC_FILE = "fortigate\\vip\\ara1-nat.rsc"
DEFAULT_WAN = "isp1"
DEFAULT_LAN = "lan"
SDWAN = True
network_to_interface ("128.1.0.0/16", "port11")
network_to_interface ("192.168.9.0/24", "lan")
network_to_interface ("10.1.1.0/24", "port9")
interface_map("WAN", "isp1")

# read configuration file and convert multi-line configs to single line
with open(RSC_FILE, encoding="utf-8") as f:
    rsc = f.read().replace("\\\n    ", "")
    config_lines = rsc.splitlines()

rules = []
fields = set()

# lookup nat config, if there is one
try:
    nat_config_index = config_lines.index("/ip firewall nat")
except ValueError:
    print("Configuration file {rsc_file} doesn't have a NAT configuration.")
    exit()

print(f"NAT configuration found at line {nat_config_index}.")

# convert NAT configuration to a dictionary array
for line in config_lines[nat_config_index+1:]:
    if line[0] == "/":
        break

    tokens = shlex.split(line)
    if tokens[0] == "add":
        rule = defaultdict(lambda: None)
        for token in tokens[1:]:
            (k, v) = token.split("=", maxsplit=1)
            rule[k] = v
            fields.add(k)

        if rule["action"] == "dst-nat":
            print(rule)
            rules.append(rule)

fields = list(fields)
fields.sort()

# create csv output for revision
with open("vips.csv", mode="w", newline="", encoding="utf-8") as output:
    csv_output = csv.DictWriter(output, fieldnames=fields)
    csv_output.writeheader()
    csv_output.writerows(rules)

# create terraform template
with open("virtual-ips.tf", mode="w", encoding="utf-8") as output:
    count = 1
    seen_services = set()

    for rule in rules:

        # skip disabled rules
        if rule["disabled"] == "yes":
            rule_status = "disable"
            print(f"rule {count}: warning: disabled")
        else:
            rule_status = "enable"

        if rule["dst-address"] is None and rule["in-interface"] is None:
            print(f"rule {count}: warning: no in-interface nor ip address.")
            rule["in-interface"] = DEFAULT_WAN

        if rule["protocol"] not in [None, "tcp", "udp"]:
            print(f"rule {count}: skipping: unsupported protocol.")

        # build vip name
        name = f"vip-{count:03}"
        vip_name = f"vip-{count:03}"
        if rule["dst-address"] is not None:
            vip_name += f'-{rule["dst-address"]}'
        else:
            vip_name += f'-{rule["in-interface"]}'

        if rule["dst-port"] is not None:
            vip_name += f':{rule["dst-port"]}'
            service_name = f'{rule["protocol"]}-{rule["to-ports"]}'
        else:
            service_name = None

        # interface handling
        if "in-interface" not in rule:
            # interface not specified
            real_interface = DEFAULT_WAN
        else:
            # try to map name to new name
            real_interface = interface_xlat(rule["in-interface"])
            if real_interface is None:
                # then try by ip address
                real_interface = ip_to_interface(rule["dst-address"])
                if real_interface is None:
                    real_interface = rule["dst-address"]

        output.write(f'resource "fortios_firewall_vip" "{name}" {{\n')
        output.write(f'  name    = "{vip_name}"\n')

        if rule["comment"] is not None:
            output.write(f'  comment = "{rule["comment"]}"\n')

        output.write(f'  extintf = "{real_interface}"\n')

        if rule["dst-address"] is not None:
            output.write(f'  extip   = "{rule["dst-address"]}"\n')

        output.write(f'  mappedip    {{ range = "{rule["to-addresses"]}" }}\n')

        if rule["protocol"] is not None:
            output.write(f'  protocol    = "{rule["protocol"]}"\n')
            output.write('  portforward = "enable"\n')
            output.write(f'  extport     = "{rule["dst-port"]}"\n')
            output.write(f'  mappedport  = "{rule["to-ports"]}"\n')

        output.write('}\n\n')

        # service
        if service_name is not None and service_name not in seen_services:
            seen_services.add(service_name)
            output.write(f'resource "fortios_firewallservice_custom" "{service_name}" {{\n')
            output.write(f'  name          = "{service_name}"\n')
            output.write('  protocol      = "TCP/UDP/SCTP"\n')
            output.write(f'  tcp_portrange = "{rule["to-ports"]}"\n')
            output.write('}\n\n')

        # policy

        output.write(f'resource "fortios_firewall_policy" "{name}" {{\n')
        output.write(f'  name    = "{vip_name}"\n')
        output.write('  action = "accept"\n')
        output.write('  logtraffic = "all"\n')
        output.write('  schedule = "always"\n')
        output.write(f'  status = "{rule_status}"\n')
        output.write(f'  dstaddr {{ name = fortios_firewall_vip.{name}.name }}\n')

        policy_dstintf = ip_to_interface(rule["to-addresses"])

        if policy_dstintf is None:
            policy_dstintf = DEFAULT_LAN

        output.write(f'  dstintf {{ name = "{policy_dstintf}" }}\n')

        if SDWAN:
            output.write('  srcintf { name = "virtual-wan-link" }\n')

        output.write('  srcaddr { name = "all" }\n')

        if service_name is not None:
            output.write(f'  service {{ name = fortios_firewallservice_custom.{service_name}.name }}\n')
        else:
            output.write('  service { name = "ALL" }\n')

        if rule["comment"] is not None:
            output.write(f'  comments = "{rule["comment"]}"\n')

        output.write('}\n\n')

        count += 1
