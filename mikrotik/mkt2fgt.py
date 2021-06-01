import argparse
import shlex
import ipaddress

import pprint

from collections import defaultdict
from os.path import isfile
from sys import exit

# helpers
def valid_ip(str_ip):
    try:
        ip=ipaddress.ip_address(str_ip)
    except:
        ip=None
    
    return(ip)

def valid_network(str_network):
    try:
        network=ipaddress.ip_network(str_network)
    except:
        network=None
    
    return(network)


# command line
parser = argparse.ArgumentParser(description="Converts mikrotik configuration sections to fortigate")
parser.add_argument("--mikrotik-config", help="mikrotik config file", required=True)
parser.add_argument("--fortigate-config", help="output forgitate config file", required=True)
parser.add_argument("--map-interfaces", nargs="*", help="[MKT_IF:FGT_IF ... ]. replace mikrotik interfaces with its fortigate counterparts.")
parser.add_argument("--addresses", nargs="*", help="[INTERFACE ...] generate interface address configuration for INTERFACE, * for all", default=False, )
parser.add_argument("--dhcp-servers", nargs="*", help="[SERVER ...]. dhcp servers to migrate, * for all")
parser.add_argument("--ppp-users", help="convert ppp users to local users", default=False, action='store_true')

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
            print("*** ERROR: you shouldn't specify multiple interfaces and use \"*\"")
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
            if cmd != "add" or ("disabled" in opt and opt["disabled"] == "yes"):
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
                
            o.write("end\n")
        else:
            print("!!! no interface addresses to migrate")
    else:
        print("!!! no interface addresses to migrate")

# dhcp servers
if args.dhcp_servers is not None:
    
    if "*" in args.dhcp_servers:
        if len(args.dhcp_servers) != 1:
            print("*** ERROR: you shouldn't specify multiple servers and use \"*\"")
            exit(-1)
        else:
            print(">>> migrating all dhcp servers")
            all_dhcp = True
    else:
        all_dhcp = False
        dhcp_servers = [x.casefold() for x in args.addresses]
        print(">>> migrating dhcp servers {dhcp_servers}".format(
            dhcp_servers=", ".join(dhcp_servers)
        ))

    # check for dhcp-server network and server

    # build dhcp networks list
    dhcp_networks = dict()
    for dhcp_network in config["/ip/dhcp-server/network"]:
        (cmd, opt) = dhcp_network
        
        if cmd != "add":
            continue

        # network
        network = { 
            "address": valid_network(opt["address"])
        }

        # valid network is required
        if network["address"] is None:
            continue

        # default_gateway
        if "gateway" in opt:
            network["gateway"] = valid_ip(opt["gateway"])

        # dns servers
        if "dns-server" in opt:
            dnslist = list()
            for dns in opt["dns-server"].split(","):
                dnssrv=ipaddress.ip_address(dns)
                if dnssrv is not None:
                    dnslist.append(dnssrv)
            
            network["dns"] = dnslist

        network["domain"] = opt["domain"] if "domain" in opt else None

        dhcp_networks[str(network["address"])] = network

    # build ip pool list
    ip_pools = dict()
    for ip_pool in config["/ip/pool"]:
        (cmd, opt) = ip_pool
        ranges=list()

        if cmd != "add" or ("disabled" in opt and opt["disabled"] == "yes"):
            continue

        ranges_tmp = opt["ranges"].split(",")
        for r in ranges_tmp:
            (s, e) = r.split("-")
            start_ip = valid_ip(s)
            end_ip = valid_ip(e)
            if start_ip is None or end_ip is None:
                print("*** ERROR invalid pool range {r} in pool {pool}".format(
                    r=r,
                    pool=opt["name"]
                ))

            ranges.append((start_ip, end_ip))
        
        ip_pools[opt["name"]] = ranges

    # build dhcp server list
    dhcp_servers = list()
    for dhcp_server in config["/ip/dhcp-server"]:
        (cmd, opt) = dhcp_server

        if cmd != "add" or ("disabled" in opt and opt["disabled"] == "yes"):
            continue

        name = opt["name"]
        print("--- analyzing dhcp server {server}".format(
            server=opt["name"]
        ))
        dhcp_server = dict()

        # try to find out which dhcp network matches this server by using the interface IPs
        interface = ifmap[opt["interface"]] if opt["interface"] in ifmap else opt["interface"]
        dhcp_server["interface"] = interface
        dhcp_server["name"] = opt["name"]

        if interface in ifaddress:
            found = False
            for i in ifaddress[interface]:
                (ip, network) = i
                for n in dhcp_networks:
                    if ip in dhcp_networks[n]["address"]:
                        found = True
                        print("--- found dhcp server options for server {server}".format(
                            server=opt["name"]
                        ))
                        dhcp_server["network"] = dhcp_networks[n]["address"]
                        dhcp_server["dns"] = dhcp_networks[n]["dns"] if "dns" in dhcp_networks[n] else None
                        dhcp_server["gateway"] = dhcp_networks[n]["gateway"] if "gateway" in dhcp_networks[n] else None
                        dhcp_server["domain"] = dhcp_networks[n]["domain"] if "domain" in dhcp_networks[n] else None
                        break

                if found:
                    break

        else:
            print("!!! did not find dhcp options for server {server}".format(
                server=opt["name"]
            ))
        
        if opt["address-pool"] in ip_pools.keys():
            dhcp_server["pool"] = ip_pools[opt["address-pool"]]
            print("--- found ip pool for dhcp server {server}".format(
                server=opt["name"]
            ))

        dhcp_servers.append(dhcp_server)
    
    
    o.write("\nconfig system dhcp server\n")
    for dhcp_server in dhcp_servers:
        o.write("    edit 0\n")
        # domain
        if dhcp_server["domain"] is not None:
            o.write("        set domain \"{domain}\"\n".format(
                domain=dhcp_server["domain"]
            ))        
        # gateway
        if dhcp_server["gateway"] is not None:
            o.write("        set default-gateway {gateway}\n".format(
                gateway=dhcp_server["gateway"]
            ))

        # network
        if dhcp_server["network"] is not None:
            o.write("        set netmask {netmask}\n".format(
                netmask=dhcp_server["network"].netmask
            ))

        # interface
        o.write("        set interface \"{interface}\"\n".format(
            interface=dhcp_server["interface"]
        ))

        if len(dhcp_server["pool"]) > 0:
            o.write("        config ip-range\n")

            for (s,e) in dhcp_server["pool"]:
                o.write("            edit 0\n")
                o.write("                set start-ip {ip}\n".format(ip=s))
                o.write("                set end-ip {ip}\n".format(ip=s))
                o.write("            next\n")

            o.write("        end\n")
        o.write("    next\n")
        print("--- configured dhcp server for interface {interface}".format(
            interface=dhcp_server["interface"]
        ))

        # reserved addresses
        limit = 200 
        o.write("    config reserved-address\n")
        for rsvadr in config["/ip/dhcp-server/lease"]:
            (cmd, opt) = rsvadr
            if cmd != "add":
                continue

            if "server" not in opt or dhcp_server["name"] != opt["server"] or "address" not in opt or "mac-address" not in opt or "server" not in opt:
                continue

            ip=valid_ip(opt["address"])
            if ip is None:
                continue
        
            o.write("        edit 0\n")
            o.write("            set ip {ip}\n".format(
                ip=ip
            ))
            o.write("            set mac {mac}\n".format(
                mac=opt["mac-address"].casefold()
            ))

            if "comment" in opt:
                o.write("            set description \"{comment}\"\n".format(
                    comment=opt["comment"]
                ))

            o.write("        next\n")
            limit -= 1
            if limit <= 0:
                print("!!! output truncated: max 200 dhcp leases per network")
                break


        o.write("    end\n")


    o.write("end\n")





            

        


#
o.close()
print("--- done")