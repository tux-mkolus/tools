"""NAT Module."""
import ipaddress
import logging
import re
import shlex
import csv
from collections import defaultdict
from io import StringIO
from validation import valid_ip, valid_network

class PortRange:
    """Port Range class."""

    def __init__(self, spec: str | None = None):
        """Create port range from start-end."""
        self.start = None
        self.end = None

        if spec is not None and spec != "":
            self.set(spec)

    def set(self, spec: str):
        """Set start and end port range using START-END or START:END as format."""
        if spec is None or spec == "":
            self.start = None
            self.end = None
            return

        rx_portrange = re.compile(r"^(?P<from>\d+)([-:](?P<to>\d+))?$")
        if (m := rx_portrange.fullmatch(spec)) is not None:
            from_port = int(m.group("from"))
            if from_port < 65536:
                self.start = from_port

                if m.group("to") is not None:
                    to_port = int(m.group("to"))
                    if to_port <= 65535:
                        self.end = to_port
                        if to_port < from_port:
                            (self.end, self.start) = (from_port, to_port)

                        return
                else:
                    self.end = self.start
                    return

        raise ValueError(f"invalid port range \"{spec}\".")

    def __repr__(self):
        """Repr."""
        if self.start is None:
            return ''

        if self.end is None or self.start == self.end:
            return f"{self.start}"

        return f"{self.start}-{self.end}"

    def __str__(self):
        """Str."""
        return self.__repr__()

    def __len__(self):
        """Port range lenght."""
        if self.start is None:
            return 0

        if self.end is None:
            return 1

        return self.end - self.start + 1

    def __eq__(self, other):
        """Equality operator."""
        if isinstance(other, str):
            other = PortRange(other)

        if other is None:
            return self.start is None and self.end is None

        return self.start == other.start and self.end == other.end

    def __hash__(self):
        """__hash__."""
        return hash(self.__repr__())


class IPRange:
    """Class for handling IP address ranges."""
    def __init__(self, spec: str | None = None):
        """Init."""
        self.start_ip = None
        self.end_ip = None
        self.any = False

        if spec is not None:
            self.set(spec)

    def set(self, spec: str):
        """Set the IP range using START_IP-END_IP, IP/MASK or 'any'."""
        spec = spec.strip().casefold()
        if spec == "any" or spec.strip() == "0.0.0.0":
            self.any = True
            return

        if spec.find("/") != -1:
            # cidr format
            try:
                ip_network = ipaddress.ip_network(spec)
            except ValueError as e:
                raise ValueError(f"invalid IP network {spec}: {e}") from e

            if ip_network.prefixlen == 0:
                # 0.0.0.0/0
                self.any = True
                return

            self.start_ip = ip_network.network_address
            self.end_ip = ip_network.broadcast_address
            self.any = False
        else:
            self.any = False
            tokens = spec.split("-",maxsplit=1)

            self.start_ip = valid_ip(tokens[0])
            if not self.start_ip:
                raise ValueError(f"invalid IP range '{spec}'")

            if len(tokens)==2:
                self.end_ip = valid_ip(tokens[1])
                if not self.end_ip:
                    raise ValueError(f"invalid IP range '{spec}'")

    def __repr__(self):
        """Repr."""
        if self.any:
            return "0.0.0.0"

        if self.end_ip is not None and self.start_ip != self.end_ip:
            return f"{self.start_ip}-{self.end_ip}"

        return str(self.start_ip)

    def __str__(self):
        """Str."""
        return self.__repr__()

    def __len__(self):
        """Length."""
        if self.any:
            return 4294967296

        if self.start_ip is None:
            return 0

        if self.end_ip is None:
            return 1

        return abs(int(self.start_ip)-int(self.end_ip))+1


class InterfaceMap:
    """Interface Map."""

    def __init__(self):
        """Init."""
        self.interface_map = {}

    def add(self, source: str, target: str):
        """Add an interface mapping."""

        if source in self.interface_map:
            raise ValueError(f"interface '{source}' already added")

        self.interface_map[source] = target

        logging.debug(
            "added interface translation: '%s' -> '%s'",
            source,
            target
        )

        return True

    def lookup(self, interface: str) -> str:
        """Lookup an interface map."""
        return self.interface_map[interface] if interface in self.interface_map else None


class NetworkMap:
    """Network Map,"""

    def __init__(self):
        """Init."""
        self.network_map = {}

    def add(self, network: str, interface: str):
        """Add a network to interface mapping."""
        # network address format validation
        if (network_object := valid_network(network)) is False:
            raise ValueError(f"invalid network address '{network}'")

        # duplicate test
        if network_object in self.network_map:
            raise ValueError(f"duplicate network {network_object}")

        # overlap test
        for network in self.network_map:
            if network.overlaps(network_object):
                raise ValueError(f"network {network_object} overlaps with {network}")

        self.network_map[network_object] = interface

        logging.debug(
            "added network to interface translation: '%s' -> '%s'",
            network_object,
            interface
        )

        return (network_object, interface)

    def lookup(self, ip_address: str) -> str | None:
        """Lookup a network to interface mapping."""
        if (ip_object := valid_ip(ip_address)) is False:
            return None
            #raise ValueError(f"'{ip_address}' is not a valid ip address")

        for (network, interface) in self.network_map.items():
            if ip_object in network:
                return interface

        return None


class Protocol:
    """Protocol Specification."""

    name_to_number = {
        "ah": 51,
        "esp": 50,
        "gre": 49,
        "icmp": 0,
        "tcp": 6,
        "udp": 17
    }

    def __init__(self, protocol_spec: str | None = None):
        """Init."""

        self.name = None
        self.id = None
        self.support_ports = None

        if protocol_spec is not None:
            self.set(protocol_spec)

    def set(self, protocol_spec: str):
        """Set the protocol value."""
        protocol_spec = protocol_spec.strip().casefold()
        if protocol_spec not in self.name_to_number:
            raise ValueError(f"unsupported protocol '{protocol_spec}'")

        self.name = protocol_spec
        self.id = self.name_to_number[protocol_spec]
        if protocol_spec in ["tcp", "udp"]:
            self.support_ports = True
        else:
            self.support_ports = False

    def __str__(self):
        """__str__."""
        return self.name if self.name is not None else ''

    def __repr__(self):
        """__repr__."""
        if self.name is not None:
            return f'{self.name}({self.id})'

        return ''


class NATRule:
    """NAT Specification."""
    def __init__(self):
        """Init."""
        self.external_interface = None
        self.external_address = IPRange("any")
        self.internal_interface = None
        self.internal_address = IPRange()
        self.protocol = Protocol()
        self.external_ports = PortRange()
        self.internal_ports = PortRange()
        self.comment = None

    def __repr__(self):
        """Repr."""
        protocol = "all" if self.protocol.id is None else self.protocol
        if self.protocol.support_ports:
            external_ports = ":???" if len(self.external_ports) == 0 else f":{self.external_ports}"
            if len(self.internal_ports) == 0:
                internal_ports = external_ports
            else:
                internal_ports = f":{self.internal_ports}"
        else:
            external_ports = ""
            internal_ports = ""

        return "{protocol}/{external_interface}->{external_address}{external_ports}->{internal_interface}->{internal_address}{internal_ports}".format(
            external_interface=self.external_interface if self.external_interface is not None else "???",
            internal_interface=self.internal_interface if self.internal_interface is not None else "???",
            protocol=protocol,
            external_address=self.external_address if len(self.external_address) else "?.?.?.?",
            internal_address=self.internal_address if len(self.internal_address) else "?.?.?.?",
            external_ports=external_ports,
            internal_ports=internal_ports
        )

    def __str__(self):
        """String."""
        repr_string = self.__repr__()
        if self.comment is not None:
            return f'{repr_string} "{self.comment}"'

        return repr_string

    def diagnose(self) -> list:
        """Diagnose NAT rule and return list of problems."""
        problems = []
        # internal and external interface set
        if self.external_interface is None:
            problems.append("no external interface")

        if self.internal_interface is None:
            problems.append("no internal interface")

        # external ip set
        if len(self.external_address) == 0:
            problems.append("no external IP")

        # internal ip set
        if len(self.internal_address) == 0:
            problems.append("no internal (mapped) IP")

        # ip range difference
        if len(self.external_address) and len(self.internal_address):
            if self.external_address.any:
                if len(self.internal_address) != 1:
                    problems.append("0.0.0.0 can be mapped only to 1 IP")
            elif len(self.external_address) != len(self.internal_address):
                problems.append(f"uneven external and internal ip range sizes: {len(self.external_address)} -> {len(self.internal_address)} ")

        # tcp and udp must have external port
        if self.protocol.id in [6,17]:
            if len(self.external_ports) == 0:
                problems.append(f"{self.protocol.name} requires at least an external port")
        else:
            problems.append(f"unsuported virtual IP protocol: {self.protocol.name}")

        return problems

    def is_valid(self) -> bool:
        """Validate NAT rule."""
        return len(self.diagnose())==0


class Services():
    """TCP/UDP Services Class."""
    def __init__(self):
        self.services  = {}
        self.tcp_portrange_to_service = defaultdict(lambda: None)
        self.udp_portrange_to_service = defaultdict(lambda: None)

    def add(
            self,
            name: str,
            tcp_portrange: str = None,
            udp_portrange: str = None,
            built_in: bool = False):
        """Add TCP/UDP/TCP+UDP service."""

        if name in self.services:
            raise KeyError(f"service {name} already on the list.")

        self.services[name] = {
            "tcp-portranges": [],
            "udp-portranges": [],
            "built_in": built_in
        }

        if tcp_portrange is not None and tcp_portrange != "":
            for portrange in tcp_portrange.split(','):
                port_range = PortRange(portrange)
                self.services[name]["tcp-portranges"].append(port_range)
                self.tcp_portrange_to_service[port_range] = name

        if udp_portrange is not None and udp_portrange != "":
            for portrange in udp_portrange.split(','):
                port_range = PortRange(portrange)
                self.services[name]["udp-portranges"].append(port_range)
                self.udp_portrange_to_service[port_range] = name


    def lookup(self, protocol: str, portrange: str | PortRange):
        """Check."""
        protocol = protocol.casefold().strip()
        if isinstance(portrange, str):
            portrange = PortRange(portrange)
        elif not isinstance(portrange, PortRange):
            raise TypeError (f"Services().lookup(): unsupported port rang type '{type(portrange)}'.")

        if protocol not in ["tcp", "udp"]:
            raise ValueError (f"Services().lookup(): unsupported protocol '{protocol}'.")

        if protocol == "tcp":
            return self.tcp_portrange_to_service[portrange]
        return self.udp_portrange_to_service[portrange]


def format_iptables (rules: list, config_lines: list, network_map: NetworkMap):
    """IPtables format parser."""
    current_section = None

    for config_line in config_lines:
        if config_line.startswith("*"):
            current_section = config_line.strip()[1:]
            continue

        if current_section == "nat":
            tokens = shlex.split(config_line.strip())
            if tokens[0] == "-A":
                rule_dict = {}
                while len(tokens) != 0:
                    k = tokens.pop(0)
                    v = tokens.pop(0)
                    rule_dict[k] = v

                if "-j" in rule_dict and rule_dict["-j"] != "DNAT":
                    # skip non-dnat rule
                    continue

                nat_rule = NATRule()
                # protocol
                if "-p" in rule_dict:
                    nat_rule.protocol.set(rule_dict["-p"])

                # external address
                if "-d" in rule_dict:
                    nat_rule.external_address.set(rule_dict["-d"])
                    if (external_interface := network_map.lookup(nat_rule.external_address)) is not None:
                        nat_rule.external_interface = external_interface

                # external ports
                if "--dport" in rule_dict:
                    nat_rule.external_ports.set(rule_dict["--dport"])

                # internal ports
                if "--to-destination" in rule_dict:
                    destination_spec = rule_dict["--to-destination"]
                    if destination_spec.find(":") != -1:
                        (ip, port) = destination_spec.split(":", maxsplit=1)
                        nat_rule.internal_ports.set(port)
                    else:
                        ip = destination_spec

                    nat_rule.internal_address.set(ip)
                    if (internal_interface := network_map.lookup(nat_rule.internal_address)) is not None:
                        nat_rule.internal_interface = internal_interface

                rules.append(nat_rule)


def format_csv(rules: list, config_lines: list, network_map: NetworkMap):
    """CSV Format parser."""
    required_fields = { "protocol", "extip", "extport", "mappedip" }
    csv_file = csv.DictReader(StringIO("\n".join(config_lines)))
    fields = set(csv_file.fieldnames)

    # FIXME
    if not fields >= required_fields:
        raise KeyError (
            "format_csv(): missing required fields: {missing}".format(
                missing= ", ".join(required_fields.difference(fields)))
        )

    has_mapped_port = "mappedport" in fields
    has_comment = "comment"
    for row in csv_file:
        nat_rule = NATRule()
        nat_rule.protocol.set(row["protocol"])
        nat_rule.external_address.set(row["extip"])
        if (external_interface := network_map.lookup(nat_rule.external_address)) is not None:
            nat_rule.external_interface = external_interface
        nat_rule.external_ports.set(row["extport"])
        nat_rule.internal_address.set(row["mappedip"])
        if (internal_interface := network_map.lookup(nat_rule.internal_address)) is not None:
            nat_rule.internal_interface = internal_interface
        nat_rule.external_ports.set(row["extport"])
        if has_mapped_port:
            nat_rule.internal_ports.set(row["mappedport"])
        else:
            nat_rule.internal_ports.set(row["extport"])

        if has_comment and row["comment"] != "":
            nat_rule.comment = row["comment"]

        rules.append(nat_rule)




