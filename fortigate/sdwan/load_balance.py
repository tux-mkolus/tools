import argparse
import csv
import ipaddress
import os
import sys

print("Generador de listado de sitios que no funcionan con balanceo en SD-WAN.\n")

parser = argparse.ArgumentParser(description='Genera objetos para impedir balanceo en SD-WAN')
parser.add_argument("--sites", help="archivo CSV con el listado de sitios", default="no balancear-sites.csv")
parser.add_argument("--output", help="archivo CONF de salida con el script de fortigate", default="sdwan.conf")
parser.add_argument("--addrgroup", help="nombre del address group", default="no balancear")

arg = parser.parse_args()

if not os.path.isfile(arg.sites):
    print("*ERROR* archivo de sitios {sites} no encontrado".format(
        sites=arg.sites
    ))
    sys.exit(-1)

try:
    o = open(arg.output, "w", encoding="utf-8", newline="")
except Exception as e:
    print("*ERROR* no se pudo crear el archivo {output}: {e}".format(
        output=arg.output,
        e=e
    ))
    sys.exit(-1)

o.write("config firewall address\n")

with open(arg.sites, encoding="utf-8", newline="") as f:
    csv_sites = csv.DictReader(f)
    sites = list()

    for site_row in csv_sites:

        # duplicate
        if site_row["address_name"] in sites:
            print("*ERROR* duplicated entry {address_name}".format(
                address_name=site_row["address_name"]
            ))
            sys.exit(-1)

        # ip validation
        try:
            subnet = ipaddress.ip_network(site_row["network"])
        except ValueError:
            print("*ERROR* invalid network address {subnet}, skipping.".format(
                subnet=site_row["network"]
            ))
            sys.exit(-1)
    
        o.write("    edit \"{address_name}\"\n".format(
            address_name=site_row["address_name"]
        ))
        o.write("        set subnet {subnet} {mask}\n".format(
            subnet=subnet.network_address,
            mask=subnet.netmask
        ))
        if site_row["comments"] is None or site_row["comments"] == "":
            comment="{asn}{owner}".format(
                    asn=(site_row["as"] + " - ") if site_row["as"] is not None else "",
                    owner=site_row["owner"]
                )
        else:
            comment = site_row["comments"]

        o.write("        set comment \"{comment}\"\n".format(
            comment=comment
        ))
        o.write("    next\n")

        sites.append(site_row["address_name"])
        print("> added {address_name}: {subnet}".format(
            address_name=site_row["address_name"],
            subnet=subnet.with_prefixlen
        ))

o.write("end\n\n")

# address group
members = [ "\"" + x + "\"" for x in sites]

o.write("config firewall addrgrp\n")
o.write("    edit \"{address_group}\"\n".format(
    address_group=arg.addrgroup
))
o.write("        set member {members}\n".format(
    members=" ".join(members)
))
o.write("    next\n")
o.write("end")

print("\ndone.")