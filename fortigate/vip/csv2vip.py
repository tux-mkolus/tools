import argparse
import csv
import json
import ipaddress
import sys

# iterator for port specifications
def portspec_gen(portspec):
    for current_spec in portspec.split(" "):
        # ignore source port
        if ":" in current_spec:
            current_spec=current_spec.split(":")[0]

        if "-" in current_spec:
            # port range
            range_def = [int(x) for x in current_spec.split("-")]
            for port in range(range_def[0], range_def[1]+1):
                yield(port)
        else:
            # port
            yield(int(current_spec))

# ip validation
def validate_ip(ip_address):
    try:
        ip=ipaddress.ip_address(ip_address.strip())
        return(ip)
    except ValueError:
        return(None)

def validate_port(port):
    try:
        port=int(port)
    except ValueError:
        return(None)
    
    if port<1 or port>65535:
        return(None)

    return(port)

parser = argparse.ArgumentParser(description="FortiGate Virtual IP creator")
parser.add_argument("--vips", help="CSV Virtual IPs file", default="vips.csv")
parser.add_argument("--services", help="JSON services file", default="services.json")
parser.add_argument("--output", help="output file for FortiGate configuration script", default="fortigate.conf")
parser.add_argument("--netcat-script", help="output file for Netcat VIP testing script", default="test-vips1.ps1")
parser.add_argument("--map-ip", help="REAL_IP:MAPPED_IP use MAPPED_IP instead of REAL_IP in the netcat script", action="append")
args = parser.parse_args()

# input file
required_fields = [
    "protocol",
    "external interface", 
    "external ip", 
    "external port",
    "internal interface",
    "internal ip","internal port",
    "comment"
]

print("Parsing VIPs file '{vips_file}':".format(
        vips_file=args.vips
))
try:
    vips_file = open(args.vips, encoding="utf-8-sig", newline="")
    csv_input = csv.DictReader(vips_file)
    # check for missing fields
    missing_fields = set(required_fields) - set(csv_input.fieldnames)
    if len(missing_fields) >0:
        print("*ERROR* missing fields in csv file: {fields}".format(
            fields=", ".join(missing_fields)
        ))
except OSError as err:
    print("*ERROR* cannot open input file '{vips_file}': {err}".format(
        vips_file=args.vips,
        err=err
    ))
    sys.exit(-1)

# services file
print("Parsing services file '{services_file}':".format(
        services_file=args.services
))

try:
    services_file = open(args.services, encoding="utf-8")
except OSError as err:
    print("*ERROR* cannot open services file '{services_file}': {err}".format(
        services_file=args.services,
        err=err
    ))
    sys.exit(-1)

try:
    json_services = json.load(services_file)
except json.JSONDecodeError as err:
    print("*ERROR* invalid JSON file '{services_file}': {err}".format(
        services_file=args.services,
        err=err
    ))
    sys.exit(-1)

proto_port_service_map = {
    "tcp": dict(),
    "udp": dict()
}

for service in json_services["results"]:
    if service["q_origin_key"] in ["ALL_TCP", "ALL_UDP", "NONE", "TRACEROUTE"]:
        continue
    # only TCP/UDP services
    if "protocol" in service and service["protocol"] == "TCP/UDP/SCTP":
        # with specific ports
        print("\tservice {name}: TCP: {tcp_portrange} UDP: {udp_portrange}".format(
            name=service["q_origin_key"],
            tcp_portrange=service["tcp-portrange"],
            udp_portrange=service["udp-portrange"]
        ))

        if service["tcp-portrange"] != "":
            for port in portspec_gen(service["tcp-portrange"]):
                proto_port_service_map["tcp"][port] = service["q_origin_key"]

        if service["udp-portrange"] != "":
            for port in portspec_gen(service["udp-portrange"]):
                proto_port_service_map["udp"][port] = service["q_origin_key"]

# output files
try:
    netcat_file=open(args.netcat_script, "w", encoding="utf-8")
except OSError as err:
    print("*ERROR* cannot create netcat script file '{netcat_file}': {err}".format(
        netcat_file=args.args.netcat_script,
        err=err
    ))
    sys.exit(-1)

try:
    fortigate_file=open(args.output, "w", encoding="utf-8")
except OSError as err:
    print("*ERROR* cannot create FortiGate script file '{fortigate_file}': {err}".format(
        fortigate_file=args.args.output,
        err=err
    ))
    sys.exit(-1)

# maps
ip_map = dict()
if args.map_ip is not None:
    print("Configuring IP mapping:")
    for mapping in args.map_ip:
        try:
            (ip_real, ip_mapped) = map(lambda ip: ipaddress.ip_address(ip), mapping.split(":",2))
            print(f"\t{ip_real} mapped to {ip_mapped}")
        except ValueError:
            print(f"*ERROR* invalid ip mapping '{mapping}'")
            sys.exit(-1)

        ip_map[ip_real] = ip_mapped

# pre-process VIP file
print("Pre-processing VIP file:")
line=1
abort=False
vips = dict()

for row in csv_input:
    external_ip = validate_ip(row["external ip"])
    if external_ip is None:
        print(f"\tline {line: 2} Invalid external IP {external_ip}")
        abort=True

    external_port = validate_port(row["external port"])
    if external_port is None:
        print(f"\tline {line: 2} Invalid external port {external_port}")
        abort=True

    internal_ip = validate_ip(row["internal ip"])
    if internal_ip is None:
        print(f"\tline {line: 2} Invalid internal IP {internal_ip}")
        abort = True
    
    internal_port = validate_port(row["external port"])
    if internal_port is None:
        print(f"\tline {line: 2} Invalid external port {external_port}")
        abort=True

    protocol=row["protocol"].strip().casefold()
    if protocol not in ["tcp", "udp"]:
        print(f"\tline {line: 2} Invalid protocol {external_port}")
        abort=True

    external_interface = row["external interface"].strip().casefold()
    internal_interface = row["internal interface"].strip().casefold()

    key = f"{external_interface}.{external_ip}.{internal_interface}.{internal_ip}"
    if key not in vips:
        vips[key] = {
            "external_interface": external_interface,
            "external_ip": external_ip,
            "internal_interface": internal_interface,
            "internal_ip": internal_ip,
            "services": list()
        }

    vips[key]["services"].append({
        "protocol": protocol,
        "external_port": external_port,
        "internal_port": internal_port
    })

    line += 1
    print(f"\tline {line: 2} {protocol}/{external_interface}->{external_ip}:{external_port}->{internal_interface}->{internal_ip}:{internal_port}")

for vipspec in vips:
    # netcat
    if vips[vipspec]["external_ip"] in ip_map:
        testing_ip = ip_map[vips[vipspec]["external_ip"]]
    else:
        testing_ip = vips[vipspec]["external_ip"]

    for service in vips[vipspec]["services"]:
        # netcat
        netcat_file.write("# {protocol}/{external_interface}->{external_ip}{testing_ip}:{external_port}->{internal_interface}->{internal_ip}:{internal_port}\n".format(
            protocol=service["protocol"],
            external_interface=vips[vipspec]["external_interface"],
            external_ip=vips[vipspec]["external_ip"],
            testing_ip="(" + str(testing_ip) + ")" if testing_ip != vips[vipspec]["external_ip"] else "",
            internal_interface=vips[vipspec]["internal_interface"],
            internal_ip=vips[vipspec]["internal_ip"],
            external_port=service["external_port"],
            internal_port=service["internal_port"],
        ))
        netcat_file.write("ncat --wait 1 {udp}{testing_ip} {port}\n".format(
            testing_ip = testing_ip,
            port = service["external_port"],
            udp = "--udp " if service["protocol"] == "udp" else ""
        ))

        # fortigate / service
        if service["internal_port"] not in proto_port_service_map[service["protocol"]]:
            # service doesn't exists
            q_origin_key = service["protocol"] + "-" + str(service["internal_port"])
            fortigate_file.write("""
config firewall service custom
    edit \"{q_origin_key}\"
        set {proto}-portrange {port}
    next
end
""".format(
    q_origin_key=q_origin_key,
    proto=service["protocol"],
    port=service["internal_port"]
))
            proto_port_service_map[service["protocol"]][service["internal_port"]] = q_origin_key
 
        # fortigate / vip
        vip_name = "vip-{extip}-{proto}-{port}".format(
            extip=vips[vipspec]["external_ip"],
            proto=service["protocol"],
            port=service["external_port"]
        )
        fortigate_file.write("""
config firewall vip
    edit "{vip_name}"
        set extip "{extip}"
        set extintf "{extintf}"
        set portforward enable
        set mappedip "{mappedip}"
        set protocol {protocol}
        set extport {extport}
        set mappedport {mappedport}
    next
end
""".format(
    vip_name=vip_name,
    extip=vips[vipspec]["external_ip"],
    extintf=vips[vipspec]["external_interface"],
    mappedip=vips[vipspec]["internal_ip"],
    protocol=service["protocol"],
    extport=service["external_port"],
    mappedport=service["internal_port"]
))

        # fortigate / policy
        fortigate_file.write("""
config firewall policy
    edit 0
        set name "{vip_name}"
        set srcintf "{extintf}"
        set dstintf "{intintf}"
        set srcaddr "all"
        set dstaddr "{vip_name}"
        set action accept
        set schedule "always"
        set service "{service_name}"
        set logtraffic all
    next
end
""".format(
    vip_name=vip_name,
    intintf=vips[vipspec]["internal_interface"],
    extintf=vips[vipspec]["external_interface"],
    service_name=proto_port_service_map[service["protocol"]][service["internal_port"]]
))

netcat_file.close()
fortigate_file.close()

print("Done\n")