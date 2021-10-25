import configparser
import ipaddress

# read config file
config = configparser.ConfigParser()
config.read("mikrotik.conf")

# mail Server
if {"server", "mail from"} <= set(config.options("SMTP")):
    cmd = "# mail server\n/tool e-mail {{\n    set address={smtp_server} from=\"{mail_from}\"".format(
        smtp_server=config["SMTP"]["server"],
        mail_from=config["SMTP"]["mail from"]
    )

    if {"smtp username", "smtp password"} <= set(config.options("SMTP")):
        cmd += " user=\"{smtp_username}\" password=\"{smtp_password}\"".format(
            smtp_username=config["SMTP"]["smtp username"],
            smtp_password=config["SMTP"]["smtp password"]
        )

    if "tls" in config.options("SMTP"):
        cmd += " start-tls={tls}".format(
            tls=config["SMTP"]["tls"]
        )

    cmd += "\n}\n"
    print(cmd)

    smtp_configured = True
else:
    smtp_configured = False

# backup script
if smtp_configured is True:
    if config.has_option("Backup", "to"):
        to = config["Backup"]["to"]
        if config.has_option("Backup", "cc"):
            cc = config["Backup"]["cc"]
        else:
            cc = ""

        cmd = r"""/system script
    add comment="automated backup via mail" dont-require-permissions=no name=mail-backup owner=admin policy=ftp,read,write,policy,test,password,sensitive source=":local mailto \"%s\"\r\
    \n:local mailcc \"%s\"\r\
    \n\r\
    \n# replace slashes in the date\r\
    \n:local tmpdate [/system clock get date]\r\
    \n:local date \"\";\r\
    \n:for i from=0 to=([:len \$tmpdate]-1) do={ :local tmp [:pick \$tmpdate \$i];\r\
    \n    :if (\$tmp !=\"/\") do={ :set date \"\$date\$tmp\" } else={ :set date \"\$date-\"}\r\
    \n}\r\
    \n\r\
    \n# check for spaces in system identity to replace with underscores\r\
    \n:local sysname [/system identity get name]\r\
    \n:if ([:find \$sysname \" \"] !=0) do={\r\
    \n    :local name \$sysname;\r\
    \n    :local newname \"\";\r\
    \n    :for i from=0 to=([:len \$name]-1) do={ :local tmp [:pick \$name \$i];\r\
    \n        :if (\$tmp !=\" \") do={ :set newname \"\$newname\$tmp\" } else={ :set newname \"\$newname_\" }\r\
    \n    }\r\
    \n    :set sysname \$newname\r\
    \n}\r\
    \n\r\
    \n# create export and backup\r\
    \n:local rscfilename\r\
    \n:local backupfilename\r\
    \n:set rscfilename (\"\$date-\$sysname.rsc\")\r\
    \n:set backupfilename (\"\$date-\$sysname.backup\")\r\
    \n:execute [/export file=\$rscfilename]\r\
    \n:execute [/system backup save name=\$backupfilename]\r\
    \n\r\
    \n# send email\r\
    \n:local allfiles { \$rscfilename; \$backupfilename }\r\
    \n\r\
    \n:log info \"sending configuration backup email to: \$mailto, cc: \$mailcc\"\r\
    \n/tool e-mail send to=\$mailto cc=\$mailcc subject=\"[configuration backup] \$sysname \$date\" file=\$allfiles"

""" % (to, cc)

    cmd += """/system scheduler
add interval=1w name=sched-backup on-event=mail-backup policy=\
ftp,reboot,read,write,policy,test,password,sniff,sensitive,romon \
start-date=jan/01/1970 start-time=00:00:00"""

    print(cmd)

# firewall core
print("""
# firewall core config

# non-routeable addresses
/ip firewall address-list {
     add address=0.0.0.0/8 comment="This host on this network" list=RFC6890
     add address=10.0.0.0/8 comment="Private-Use" list=RFC6890
     add address=100.64.0.0/10 comment="Shared Address Space" list=RFC6890
     add address=127.0.0.0/8 comment="Loopback" list=RFC6890
     add address=169.254.0.0/16 comment="Link Local" list=RFC6890
     add address=172.16.0.0/12 comment="Private-Use" list=RFC6890
     add address=192.0.0.0/24 comment="IETF Protocol Assignments" list=RFC6890
     add address=192.0.2.0/24 comment="Documentation (TEST-NET-1)" list=RFC6890
     add address=192.168.0.0/16 comment="Private-Use" list=RFC6890
     add address=192.88.99.0/24 comment="6to4 Relay Anycast" list=RFC6890
     add address=198.18.0.0/15 comment="Benchmarking" list=RFC6890
     add address=198.51.100.0/24 comment="Documentation (TEST-NET-2)" list=RFC6890
     add address=203.0.113.0/24 comment="Documentation (TEST-NET-3)" list=RFC6890
     add address=224.0.0.0/4 comment="Multicast" list=RFC6890
     add address=240.0.0.0/4 comment="Reserved" list=RFC6890
}

# established and related connections (input and forward)
/ip firewall filter {
    add chain=input comment="Accept established and related packets" connection-state=established,related
    add chain=forward comment="Accept established and related packets" connection-state=established,related
    add action=drop chain=forward comment="Drop invalid packets" connection-state=invalid    
}

/ip firewall filter {
    add action=jump chain=input comment="WAN IN" in-interface-list=wan_interfaces jump-target=wan_in
    add action=drop chain=wan_in comment="Drop invalid packets" connection-state=invalid
    add action=drop chain=wan_in comment="Drop all packets which are not destined to the router's IP addresses" dst-address-type=!local
    add action=drop chain=wan_in comment="Drop all packets which does not have unicast source IP address" src-address-type=!unicast
    add action=drop chain=wan_in comment="Drop all packets from public internet which should not exist in public network" src-address-list=RFC6890
    add action=jump chain=forward comment="WAN forward in" in-interface-list=wan_interfaces jump-target=wan_fwdin
    add action=jump chain=forward comment="WAN forward out" out-interface-list=wan_interfaces jump-target=wan_fwdout 
    add action=drop chain=wan_fwdin comment="Drop all packets from public internet which should not exist in public network" src-address-list=RFC6890
    add action=accept chain=wan_fwdin comment="Allow dst-natted packets" connection-nat-state=dstnat
    add action=drop chain=wan_fwdout comment="Drop all packets from local network to internet which should not exist in public network" dst-address-list=RFC6890  
    add action=accept chain=wan_fwdout comment="Allow all other connections"
}""")

lans = [ x.strip() for x in config["DEFAULT"]["LanInterfaces"].split(",") ]
lan_networks = [ ipaddress.ip_network(x.strip()) for x in config["DEFAULT"]["LanNetworks"].split(",")]

wans = list()

for wan in [ x.strip() for x in config["DEFAULT"]["WanInterfaces"].split(",") ]:
    if config.has_section(wan):
        wans.append({
            "interface": config[wan]["interface"],
            "ip": ipaddress.IPv4Interface(config[wan]["ip"]),
            "gateway": config[wan]["gateway"],
            "monitor": config[wan]["link monitor"],
            "weight": int(config[wan]["weight"])
        })

# calculate weights
weight_sum = 0

for wan in wans:
    if "weight" in wan:
        weight_sum += wan["weight"]
    else:
        weight_sum += 1

# interface lists

print("""
# interface lists
/interface list add name=wan_interfaces
/interface list add name=lan_interfaces""")

print ("# interface lists / lan")
for interface in lans:
    print(f"/interface list member add interface={interface} list=lan_interfaces")

print("\n# interface lists / wan")
for interface in wans:
    print(f"/interface list member add interface={interface['interface']} list=wan_interfaces")

# local networks
print("# local networks")
for lan_network in lan_networks:
    print("/ip firewall address-list add address={lan_network} list=internal".format(
        lan_network=lan_network
    ))

print("""
/ip firewall mangle {
add action=mark-connection chain=prerouting comment="exclude internal traffic from wan load balancing" connection-mark=no-mark dst-address-list=internal new-connection-mark=internal src-address-list=internal
}

""")

# pcc
pcc_count=0
pcc_method=config["DEFAULT"]["PCCMethod"]
gateway=list()

for wan in wans:
    # gateway
    gateway.append(wan["monitor"])

    # via rules
    print("# default via rules\n/ip firewall address-list add address={network} list=via_{interface}\n".format(
        network=wan["ip"].network,
        interface=wan["interface"]
    ))

    # mangle rules
    print(f"#\n# wan load balancing for {wan['interface']}\n#\n")
    print("/ip firewall mangle {""")
    
    print(f"    add chain=prerouting in-interface={wan['interface']} connection-mark=no-mark action=mark-connection new-connection-mark={wan['interface']}_conn")
    print(f"    add chain=prerouting in-interface-list=lan_interfaces connection-mark=no-mark dst-address-list=via_{wan['interface']} action=mark-connection new-connection-mark={wan['interface']}_conn")
    weight = wan["weight"] if "weight" in wan else 1
    print(f"    # pcc weight {weight}")

    for i in range(weight):
        print(f"    add chain=prerouting in-interface-list=lan_interfaces connection-mark=no-mark dst-address-type=!local per-connection-classifier={pcc_method}:{weight_sum}/{pcc_count} action=mark-connection new-connection-mark={wan['interface']}_conn")
        pcc_count += 1

    print(f"    add chain=prerouting connection-mark={wan['interface']}_conn in-interface-list=lan_interfaces action=mark-routing new-routing-mark={wan['interface']}_route")
    print(f"    add chain=output connection-mark={wan['interface']}_conn action=mark-routing new-routing-mark={wan['interface']}_route")
    print("}")

    # masquerade
    print(f"\n# masquerade\n/ip firewall nat add chain=srcnat out-interface={wan['interface']} action=masquerade")

    # routes
    print("\n# routing\n/ip route {")
    print(f"    add distance=1 dst-address={wan['monitor']}/32 gateway={wan['gateway']} scope=10")
    print(f"    # primary route")
    print(f"    add check-gateway=ping distance=1 gateway={wan['monitor']} routing-mark={wan['interface']}_route")

    print(f"    # secondary routes")
    distance=2
    for sec_wan in wans:
        if wan["interface"] != sec_wan["interface"]:
            print(f"    add check-gateway=ping distance={distance} gateway={sec_wan['monitor']} routing-mark={wan['interface']}_route")
            distance += 1
    print("}\n")

# default gateway
print("# default route\n/ip route add distance=1 gateway={gateways}".format(gateways=",".join(gateway)))

