import argparse
import ipaddress
import sys

parser = argparse.ArgumentParser(description="FortiSwitch VLAN interface generator")
parser.add_argument("--fortiswitch_interface", help="fortiswitch interface. default: fortilink", default="fortilink")
parser.add_argument("--interface", help="interface name", required=True)
parser.add_argument("--vlanid", help="vlan id", type=int, required=True)
parser.add_argument("--vdom", help="vdom", default="root")
parser.add_argument("--address_object", help="address objects, defaults to net-INTERFACE")
parser.add_argument("--ip", help="interface IP address in CIDR format")
parser.add_argument("--role", help="interface role. {lan|wan|dmz}", choices=["lan", "wan", "dmz"])
parser.add_argument("--description", help="interface description")
parser.add_argument("--allow_ping", help="allow ping", action="store_true")
parser.add_argument("--allow_https", help="allow https", action="store_true")
parser.add_argument("--allow_ssh", help="allow secure shell", action="store_true")
parser.add_argument("--allow_fgfm", help="allow fortimanager", action="store_true")
parser.add_argument("--allow_fabric", help="allow security fabric and capwap", action="store_true")
parser.add_argument("--enable_di", help="enable device identification", action="store_true")
parser.add_argument("--enable_ntp", help="enable ntp server on interface", action="store_true")
parser.add_argument("--enable_dhcp", help="enable dhcp server on interface", action="store_true")
parser.add_argument("--enable_dns", help="enable dns server on interface", action="store_true")
parser.add_argument("--dhcp_lease", help="dhcp lease time in seconds, default 1 day", type=int, default=86400)
parser.add_argument("--dhcp_dns_domain", help="domain dns name")
parser.add_argument("--dhcp_dns_server", help="{local|dns server [,dns_server, dns_server, dns_server]}")

args = parser.parse_args()

# 
interface = dict()
# interface
try:
    interface["ip"] = ipaddress.ip_address(args.ip.split("/")[0])
    interface["network"] = ipaddress.ip_network(args.ip, strict=False)
except ValueError:
    print("*ERROR* invalid IP address {ip}".format(ip=args.ip))
    sys.exit(-1)

# allow access
interface["allowaccess"] = list()
if args.allow_ping:
    interface["allowaccess"].append("ping")

if args.allow_https:
    interface["allowaccess"].append("https")

if args.allow_ssh:
    interface["allowaccess"].append("ssh")

if args.allow_fgfm:
    interface["allowaccess"].append("fgfm")

if args.allow_fabric:
    interface["allowaccess"].append("fabric")


# system/interface
print("config system interface")
print("    edit \"{interface}\"".format(
    interface=args.interface))
print("        set vdom \"root\"")
print("        set ip {ip} {mask}".format(
    ip=interface["ip"],
    mask=interface["network"].netmask
))
print("        set allowaccess {access}".format(
    access=" ".join(interface["allowaccess"])
))

if args.description is not None:
    print("        set description \"{description}\"".format(
        description=args.description
    ))

if args.enable_di:
    print("        set device-identification enable")

if args.role:
    print("        set role {role}".format(
        role=args.role
    ))

print("        set interface \"{fortilink}\"".format(
    fortilink=args.fortiswitch_interface
))

print("        set vlanid {vlanid}".format(
    vlanid=args.vlanid
))
print("    next")
print("end")

# firewall/address
address_object = args.address_object if args.address_object is not None else "net-" + args.interface
print("\nconfig firewall address")
print("    edit \"{address_object}\"".format(
    address_object=address_object
))
print("        set subnet {subnet} {mask}".format(
    subnet=interface["network"].network_address,
    mask=interface["network"].netmask
))
print("    next")
print("end")


# system/ntp
if args.enable_ntp:
    print("\nconfig system ntp")
    print("    set server-mode enable")
    print("    append interface \"{interface}\"".format(
        interface=args.interface
    ))
    print("end")

# system/dns-server
if args.enable_dns:
    print("\nconfig system dns-server")
    print("    edit \"{interface}\"".format(
        interface=args.interface
    ))
    print("    next")
    print("end")

# system/dhcp/server
if args.enable_dhcp:
    print("\nconfig system dhcp server")
    print("    edit 0")

    # lease time
    if args.dhcp_lease:
        print("        set lease-time {dhcp_lease}".format(
            dhcp_lease=args.dhcp_lease
        ))

    # ntp
    if args.enable_ntp:
        print("        set ntp-service local")
    
    # dns servers
    if args.dhcp_dns_server == "local" or (args.dhcp_dns_server is None and args.enable_dns):
        print("        set dns-service local")
    elif args.dhcp_dns_server is not None:
        dns_servers_list=args.dhcp_dns_server.split(",")
        dns_servers=list()
        for dns in dns_servers_list:
            try:
                dns_servers.append(ipaddress.ip_address(dns))
            except ValueError:
                print("**ERROR** invalid dns server IP {ip}".format(
                    ip=dns
                ))
                sys.exit(-1)
        print("        set dns-service specify")
        for i in range(len(dns_servers[:4])):
            print("        set dns-server{i} {ip}".format(
                i=i+1,
                ip=dns_servers[i]
            ))

    # dns domain
    if args.dhcp_dns_domain:
        print("        set domain \"{domain}\"".format(
            domain=args.dhcp_dns_domain
        ))

    # default gateway
    print("        set default-gateway {ip}".format(
        ip=interface["ip"]
    ))
        
    print("        set netmask {netmask}".format(
        netmask=interface["network"].netmask
    ))

    print("        set interface \"{interface}\"".format(
        interface=args.interface
    ))

    # ip ranges
    ranges=list()
    # first ip address 
    if interface["network"][1] == interface["ip"]:
        ranges.append((interface["network"][2], interface["network"][-2]))
    # last
    elif interface["network"][-2] == interface["ip"]:
        ranges.append((interface["network"][1], interface["network"][-3]))
    # something in the middle
    else:
        gw_offset = list(interface["network"]).index(interface["ip"])
        ranges.append((interface["network"][1], interface["network"][gw_offset-1]))
        ranges.append((interface["network"][gw_offset+1], interface["network"][-2]))

    print("        config ip-range")
    for (s, e) in ranges:
        print("            edit 0")
        print("                set start-ip {start}".format(
            start=s
        ))
        print("                set end-ip {end}".format(
            end=e
        ))
        print("            next")
    print("        end")

    print("    next")
    print("end")