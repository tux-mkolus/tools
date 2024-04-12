import argparse
import os
import sys
import shlex
from collections import defaultdict
from jinja2 import Template

class DHCPServerLease:

    def __init__ (self, mac, ip, comment=None):
        self.mac = mac.lower()
        self.ip = ip
        self.comment = comment

    def __str__ (self):
        if self.comment is None:
            return f"{self.mac} ➡️ {self.ip}"
        else:
            return f"{self.mac} ➡️ {self.ip} ({self.comment})"
    
    def __repr__ (self):
        return f"{self.ip} {self.mac}"

class DHCPServer:

    def __init__ (self, name):
        self.name = name
        self.id = 1
        self.leases = []

    def add_lease (self, mac, ip, comment=None):
        self.leases.append(DHCPServerLease(mac, ip, comment))

    def __repr__ (self):
        return f"DHCPServer({self.name})"

    def __str__ (self):
        return self.__repr__

parser = argparse.ArgumentParser(
    prog='import-mkt-dhcp-leases',
    description='Exports Mikrotik DHCP leases as a FortiGate script.'
)

parser.add_argument('config', help="Mikrotik config file.")
args = parser.parse_args()

if not os.path.isfile(args.config):
    print(f"Invalid config file: {args.config}, exiting.")
    sys.exit(-1)

try:
    with open(args.config, encoding="utf-8") as f:
        rsc_content = f.read().replace("\\\n    ", "")
        config_lines = rsc_content.splitlines()
except Exception as err:
    print(f"Unable to read file '{args.config}', error: {err}")
    sys.exit(-1)

try:
    leases_config_line = config_lines.index("/ip dhcp-server lease")
except ValueError:
    abort(f"Configuration file '{args.config}' doesn't appear to have DHCP leases, exiting.")
    sys.exit(-1)

dhcp_servers = {}

for line in config_lines[leases_config_line+1:]:
    if line[0] == "/":
        break

    tokens = shlex.split(line)
    if tokens[0] == "add":
        lease = defaultdict(lambda: None)
        for token in tokens[1:]:
            (k, v) = token.split("=", maxsplit=1)
            lease[k] = v

        if lease["server"] not in dhcp_servers:
            dhcp_servers[lease["server"]] = DHCPServer(lease["server"])

        dhcp_servers[lease["server"]].add_lease(
            mac=lease["mac-address"],
            ip=lease["address"],
            comment=lease["comment"]
        )

with open("dhcp.conf.jinja2", encoding="utf-8") as template_file:
    template = Template(template_file.read())

server_id = 1

for dhcp_server in dhcp_servers:
    print(template.render(
        server_id = server_id,
        server_name = dhcp_servers[dhcp_server].name,
        leases = dhcp_servers[dhcp_server].leases
    ))

    server_id += 1

