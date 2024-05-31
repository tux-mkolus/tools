"""Convert destination NAT rules to a FortiGate Terraform template."""
import argparse
import os
import sys
import json
from nat import NetworkMap, InterfaceMap, Services, format_iptables
from rich.console import Console
from rich.table import Table
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

import pandas as pd

SCRIPT_PATH = sys.path[0]
DEFAULT_SERVICES_FILE = f"{SCRIPT_PATH}{os.sep}default-services.json"

parser = argparse.ArgumentParser(
    prog="dstnat2tf",
    description="Converts destination NAT rules to a FortiGate Terraform template."
)

parser.add_argument(
    "--input",
    required=True,
    help="Input file."
)

parser.add_argument(
    "--input-format",
    required=True,
    choices=["iptables", "mikrotik", "csv"],
    help="Input file format."
)

parser.add_argument(
    "--output-basename",
    required=True,
    help="Output base name for files. Ie: 'test' will generate 'test.tf' and 'test.xlsx'."
)

parser.add_argument(
    "--map-network",
    action="append",
    help="Map a network address to interface, format ADDRESS:INTERFACE"
)

parser.add_argument(
    "--map-interface",
    action="append",
    help="Map an interface name to a destination interface name SOURCE_INTERFACE:TARGET_INTERFACE"
)

parser.add_argument(
    "--default-internal",
    help="Default internal (ie: LAN) interface name"
)

parser.add_argument(
    "--default-external",
    help="Default external (ie: ISP) interface name"
)

parser.add_argument(
    "--ignore-issues",
    help="Ignore rules with issues.",
    action="store_true",
    default=False
)

parser.add_argument(
    "--use-sdwan",
    help="Create policies with an SD-WAN zone instead of an interface.",
    action="store_true",
    default=False
)

parser.add_argument(
    "--sdwan-zone",
    help="SD-WAN zone for internet (def: virtual-wan-link)",
    default="virtual-wan-link"
)

console = Console(emoji_variant="emoji", tab_size=2, highlighter=None)
console.print("[yellow][bold]dstnat2tf[/bold] Convert destination NAT rules to a FortiGate Terraform template.\n")

args = parser.parse_args()
console.print(f"[bold][green]input file[/green][/bold]: {args.input}")
console.print(f"[bold][green]input file format[/green][/bold]: {args.input_format}")
console.print(f"[bold][green]output filename base[/green][/bold]: {args.output_basename}")

# init
network_map = NetworkMap()
interface_map = InterfaceMap()

ABORT = False

if args.default_internal:
    console.print(f"[bold][cyan]default internal interface[/cyan][/bold]: {args.default_internal}")

if args.default_external:
    console.print(f"[bold][cyan]default external interface[/cyan][/bold]: {args.default_external}")

if args.map_network:
    console.print("[bold]network to interface map[/bold]:")
    for map_spec in args.map_network:
        tokens = map_spec.split(":")
        if len(tokens) != 2:
            console.print(f"⛔ [bold]invalid spec '{map_spec}'")
            ABORT = True
        else:
            try:
                network_map.add(tokens[0], tokens[1])
                console.print(f"\t 🛜  {tokens[0]} => {tokens[1]}")
            except ValueError as e:
                console.print(f"⛔ [bold]invalid spec '{map_spec}':[/bold] {e}")
                ABORT = True

if args.map_interface:
    console.print("[bold]interface to interface map[/bold]:")
    for map_spec in args.map_interface:
        tokens = map_spec.split(":")
        if len(tokens) != 2:
            console.print(f"⛔ [bold]invalid spec '{map_spec}'")
            ABORT = True
        else:
            try:
                interface_map.add(tokens[0], tokens[1])
                console.print(f"\t ⏩ {tokens[0]} => {tokens[1]}")
            except ValueError as e:
                console.print(f"⛔ [bold]invalid spec '{map_spec}':[/bold] {e}")
                ABORT = True

# initialize jinja2 environment and load templates
j2_env = Environment(
    loader = FileSystemLoader(SCRIPT_PATH + os.sep + "templates"),
    trim_blocks = True,
    lstrip_blocks = True
)

try:
    vip_template = j2_env.get_template("vip.j2")
    policy_template = j2_env.get_template("policy.j2")
    services_template = j2_env.get_template("service.j2")
except TemplateNotFound as e:
    print(f"⛔ [bold]template not found:[/bold] {e}")
    ABORT = True

if ABORT:
    sys.exit(-1)

if not os.path.isfile(args.input):
    console.print(f"⛔ [bold]invalid input file '{args.input}', aborting.")
    sys.exit(-1)

try:
    output_file =open(args.output_basename + ".tf", "w", encoding="utf-8")
except OSError as e:
    console.print(f"⛔ [bold]can't create output file '{args.output_basename}.tf', aborting: {e}")
    sys.exit(-1)

# load port to default services map
services = Services()

## usar PWD

if os.path.isfile(DEFAULT_SERVICES_FILE):
    console.print("📃 loading [bold]default services[/bold] file.")
    with open(DEFAULT_SERVICES_FILE, encoding="utf-8") as f:
        temp_services=json.load(f)

        for service in temp_services:
            services.add(
                name=service,
                tcp_portrange=temp_services[service]["tcp-portrange"] if "tcp-portrange" in temp_services[service] else None,
                udp_portrange=temp_services[service]["udp-portrange"] if "udp-portrange" in temp_services[service] else None,
                built_in=True
            )
else:
    console.print("⚠️ no [bold]default services[/bold] file found.")

formats = {
    "iptables": format_iptables
}

nat_rules = []

with open(args.input, encoding="utf-8") as input_file:
    formats[args.input_format](nat_rules, input_file.readlines(), network_map)

dstnat_table = Table(title="Destination NAT rules")
dstnat_table.add_column("#")
dstnat_table.add_column("ok")
dstnat_table.add_column("protocol", justify="center")
dstnat_table.add_column("external if")
dstnat_table.add_column("external ip", justify="right")
dstnat_table.add_column("external port", justify="right")
dstnat_table.add_column("internal if")
dstnat_table.add_column("internal ip", justify="right")
dstnat_table.add_column("internal port", justify="right")

ix = 0
service_ix = 1
nat_rules_with_issues = []
rules_df_dict = {
    "id": [],
    "protocol": [],
    "extintf": [],
    "extips": [],
    "extports": [],
    "intintf": [],
    "intips": [],
    "intports": [],
    "fos_service": [],
    "comments": []
}

for nat_rule in nat_rules:

    RULE_STATUS = None

    # use default external interface?
    if nat_rule.external_interface is not None:
        external_interface = nat_rule.external_interface
    else:
        if args.default_external:
            nat_rule.external_interface = args.default_external
            external_interface = f"[i]{args.default_external}[/i]"

        RULE_STATUS = "⚠️"

    # use default internal  interface?
    if nat_rule.internal_interface is not None:
        internal_interface = nat_rule.internal_interface
    else:
        if args.default_internal:
            nat_rule.internal_interface = args.default_internal
            internal_interface = f"[bright_black][i]{args.default_internal}[/i][/bright_black]"

        RULE_STATUS = "⚠️"

    # internal port defaults to external
    if nat_rule.protocol.id in [6,17]:
        if len(nat_rule.internal_ports) == 0:
            internal_ports = f"[bright_black][i]{nat_rule.external_ports}[/i][/bright_black]"
            nat_rule.internal_ports = nat_rule.external_ports
        else:
            internal_ports = str(nat_rule.internal_ports)

        rules_df_dict["intports"].append(nat_rule.internal_ports)
        rules_df_dict["extports"].append(nat_rule.external_ports)
        fos_service = services.lookup(nat_rule.protocol.name, nat_rule.internal_ports)
        if fos_service is None:
            service_name = f"SERVICE-{service_ix:03}"
            if nat_rule.protocol.id == 6:
                services.add(service_name, tcp_portrange=str(nat_rule.internal_ports))
            else:
                services.add(service_name, udp_portrange=str(nat_rule.internal_ports))

            rules_df_dict["fos_service"].append(service_name)
            service_ix += 1
        else:
            rules_df_dict["fos_service"]\
                .append(services.lookup(nat_rule.protocol.name, nat_rule.internal_ports))
    else:
        rules_df_dict["intports"].append(None)
        rules_df_dict["extports"].append(None)
        rules_df_dict["fos_service"].append(None)

    rule_ok = nat_rule.is_valid()
    if not rule_ok:
        RULE_STATUS = "⛔"
        nat_rules_with_issues.append(ix)
    elif RULE_STATUS is None:
        RULE_STATUS = "✅"

    ix += 1

    dstnat_table.add_row(
        str(ix),
        RULE_STATUS,
        nat_rule.protocol.name,
        external_interface,
        str(nat_rule.external_address),
        str(nat_rule.external_ports) if nat_rule.protocol.id in [6,17] else "",
        internal_interface,
        str(nat_rule.internal_address),
        internal_ports if nat_rule.protocol.id in [6,17] else "",
    )

    rules_df_dict["id"].append(ix)
    rules_df_dict["protocol"].append(nat_rule.protocol.name)
    rules_df_dict["extintf"].append(nat_rule.external_interface)
    rules_df_dict["extips"].append(nat_rule.external_address)
    rules_df_dict["intintf"].append(nat_rule.internal_interface)
    rules_df_dict["intips"].append(nat_rule.internal_address)
    rules_df_dict["comments"].append(nat_rule.comment)

console.print(dstnat_table)
console.print("[bold]*[/bold] [bright_black][i]default values[/i][/bright_black]")

if len(nat_rules_with_issues)!=0:
    console.print("\n[bold][red]NAT rules with issues:[/red][/bold]")

    for rule_id in nat_rules_with_issues:
        issues = nat_rules[rule_id].diagnose()

        console.print(f"\t⚠️  [bold]#{rule_id+1}[/bold] {nat_rules[rule_id]}")
        for issue in issues:
            console.print(f"\t\t⛔ {issue}")

console.print("\r")

if not args.ignore_issues:
    console.print("⛔  issues found, aborting.")
    sys.exit(-1)

console.print("⚠️  ignoring issues.")

# excel output
console.print(f"🧾 generating excel file [bold]{args.output_basename}.xlsx[/bold] file.")

df = pd.DataFrame.from_dict(rules_df_dict)
df.to_excel(args.output_basename + ".xlsx", sheet_name="dstnat", index=False)

# services output
console.print(f"🧾 generating services file [bold]{args.output_basename}-services.tf[/bold] file.")

with open (args.output_basename + "-services.tf", "w", encoding="utf-8") as services_tf:
    services_tf.write(services_template.render(services=services))

# policies and vips
console.print(f"🧾 generating policies and vips file [bold]{args.output_basename}.tf[/bold] file.")

with open(args.output_basename + ".tf", "w", encoding="utf-8") as output_tf:
    vip_ix = 1
    for nat_rule in nat_rules:
        if nat_rule.protocol.id not in [6,17]:
            vip_ix += 1

            continue

        vip_name = f"vip-{vip_ix:03}-"

        if not nat_rule.external_address.any:
            vip_name += f"{nat_rule.external_address}-"
        else:
            vip_name += "any-"

        vip_name += f"{nat_rule.protocol.name}/{nat_rule.external_ports}"

        if args.use_sdwan:
            external_interface = args.sdwan_zone
        else:
            external_interface = nat_rule.external_interface

        output_tf.write(vip_template.render(
            resource_name=f"vip-{vip_ix:03}",
            vip_name=vip_name,
            vip_protocol=nat_rule.protocol.name,
            vip_extintf=nat_rule.external_interface,
            vip_extip=nat_rule.external_address,
            vip_extport=nat_rule.external_ports,
            vip_mappedip=nat_rule.internal_address,
            vip_mappedport=nat_rule.internal_ports,
        ))

        service_name = services.lookup(nat_rule.protocol.name, nat_rule.internal_ports)
        if services.services[service_name]["built_in"]:
            service_name = f"\"{service_name}\""
        else:
            service_name = f"fortios_firewallservice_custom.{service_name}.name"

        output_tf.write(policy_template.render(
            resource_name=f"policy-{vip_ix:03}",
            policy_name=vip_name,
            vip_resource_name=f"vip-{vip_ix:03}",
            policy_extintf=external_interface,
            policy_intintf=nat_rule.internal_interface,
            policy_source="\"all\"",
            policy_service=service_name
        ))

        vip_ix += 1

console.print("👍 done.")
