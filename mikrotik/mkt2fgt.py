import argparse
import shlex
import ipaddress

import pprint

from collections import defaultdict
from os.path import isfile
from sys import exit


# command line
parser = argparse.ArgumentParser(description="Converts mikrotik configuration sections to fortigate")
parser.add_argument("--mikrotik-config", help="mikrotik config file", required=True)
parser.add_argument("--fortigate-config", help="output forgitate config file", required=True)
parser.add_argument("--map-interfaces", nargs="*", help="[MKT_IF:FGT_IF ... ]. replace mikrotik interfaces with its fortigate counterparts.")
parser.add_argument("--ppp-users", help="convert ppp users to local users", default=False, action='store_true')
parser.add_argument("--addresses", nargs="*", help="[INTERFACE ...] generate interface address configuration", default=False, )
args = parser.parse_args()

# open mikrotik config file
if isfile(args.mikrotik_config):
    f = open(args.mikrotik_config)
    print("--- opened mikrotik config file {file}".format(
            file=args.mikrotik_config
        ))
else:
    print("*** ERROR: file '{file}' not found, exiting.".format(
        file=args.mikrotik_config
    ))
    exit(-1)

# create fortigate config file
try:
    o = open(args.fortigate_config, "w")
    print("--- created fortigate config file {file}".format(
            file=args.fortigate_config
        ))

except OSError as e:
    print("*** ERROR: cannot create file {file}: {exception}".format(
        file=args.fortigate_config,
        exception=e.strerror
    ))
    
# interface mapping
ifmap = dict()

for ifmapping in args.map_interfaces:
    v = ifmapping.split(":")
    if len(v) != 2:
        print("*** ERROR:invalid interface map {ifmapping}, exiting.".format(
            ifmapping=ifmapping
        ))
        exit(-1)
    
    ifmap[v[0]] = v[1]

# convert config to dict and lists
config = dict()
current_line = 1
current_section = None
for l in f.readlines():
    tokens = shlex.split(l)

    # comment
    if tokens[0][0] == "#":
        continue

    if tokens[0][0] == "/":
        current_section = tokens[0] + "/" + "/".join(tokens[1:])
    else:
        if current_section is not None:
            if current_section not in config:
                config[current_section] = list()

            cmd = tokens[0]
            params = dict()
            if len(tokens) >= 2:
                for param in tokens[1:]:
                    # for now, we ignore this
                    if param not in [ "[", "find", "]", "\n"]:
                        v = param.split("=", 1)
                        params[v[0]] = v[1] if len(v) == 2 else None
            config[current_section].append((cmd, params))
        else:
            print("{l:>5}: config options without section".format(
                l=l
            ))

    current_line += 1

# ppp users
if args.ppp_users == True:
    print (">>> creating local users from ppp users")
    if "/ppp/secret" in config and len(config["/ppp/secret"]) > 0:
        o.write("\nconfig user local\n")
        for user_cmd in config["/ppp/secret"]:
            (c,p) = user_cmd
            if c == "add":
                o.write("    edit \"{user}\"\n        set type password\n        set passwd \"{password}\"\n    next\n".format(
                    user=p["name"],
                    password=p["password"]
                ))
        o.write("end\n")
    else:
        print("!!! no users to migrate")

# addresses
if args.addresses is not None:
    
    if "*" in args.addresses:
        if len(args.addresses) != 1:
            print("*** ERROR: you shouldn't specify multiple and use \"*\"")
            exit(-1)
        else:
            print(">>> migrating addresses for all interfaces")
            all_interfaces = True
    else:
        all_interfaces = False
        interfaces = [x.casefold() for x in args.addresses]
        print(">>> migrating addresses for {ifs}".format(
            ifs=", ".join(interfaces)
        ))

    print (">>> configure interface addresses")
    if "/ip/address" in config and len(config["/ip/address"]):
        ifaddress = dict()
        for address in config["/ip/address"]:
            # disabled?
            (cmd, opt) = address
            if "disabled" in opt and opt["disabled"] == "yes":
                continue

            if all_interfaces is True or opt["interface"].casefold() in interfaces:
                # validate ip address
                try:
                    ip = ipaddress.ip_address(opt["address"].split("/")[0])
                    network = ipaddress.ip_network(opt["address"], strict=False)
                except:
                    print("*** ERROR: invalid IP address {ip} for interface {interface}, skipping.".format(
                        ip=opt["address"],
                        interface=opt["interface"]
                    ))
                    continue
                
                # interface mapping
                interface = ifmap[opt["interface"]] if opt["interface"] in ifmap else opt["interface"]

                if interface in ifaddress:
                    ifaddress[interface].append((ip, network))
                else:
                    ifaddress[interface] = [(ip, network)]
                
            else:
                print("--- skipped address {address} for interface {interface}".format(
                    address=opt["address"],
                    interface=opt["interface"]
                ))

        if len(ifaddress) > 0:
            o.write("\nconfig system interface\n")
            for interface in ifaddress.keys():
                # primary ip address
                (ip, network) = ifaddress[interface][0]
                o.write("    edit \"{interface}\"\n".format(
                    interface=interface
                ))
                o.write("        set ip {ip} {mask}\n".format(
                    ip=ip,
                    mask=network.netmask
                ))
                o.write("        set allowaccess ping\n")
                print("--- configured primary ip {ip} for interface {interface}".format(
                    ip=str(ip) + "/" + str(network.prefixlen),
                    interface=interface
                ))
                
                # secondary addresses
                if len(ifaddress[interface]) > 1:
                    o.write("        set secondary-IP enable\n        config secondaryip\n")
                    for sec in ifaddress[interface][1:]:
                        (ip, network) = sec
                        o.write("            edit 0\n                set ip {ip} {mask}\n".format(
                            ip=ip,
                            mask=network.netmask
                        ))
                        o.write("                set allowaccess ping\n            next\n")

                    o.write("        end\n")

                o.write("    next\n")
                
            o.write("end")
        else:
            print("!!! no interface addresses to migrate")
    else:
        print("!!! no interface addresses to migrate")

#
o.close()
print("--- done")