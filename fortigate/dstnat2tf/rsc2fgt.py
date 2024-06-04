# pylint: disable=C0103
# pylint: disable=C0209
# pylint: disable=C0301
"""Convert Mikrotik's NAT configuration to a FortiGate Terraform template."""
import argparse
import csv
import logging
import os
import shlex
import sys

from collections import defaultdict

from rich.console import Console

from helpers import InterfaceMap, NetworkMap

console = Console(emoji_variant="emoji", tab_size=2, highlighter=None)

CSV_FILE = "destination_nat.csv"
TERRAFORM_VARS = "terraform.tfvars"
TERRAFORM_OUTPUT = "destination_nat.tf"

network_to_interface = {}
interface_translation = {}

def abort (error: str, exit_code: int=-1):
    """Print an error message and exit."""
    console.print(f"[bold red]aborted:[/bold red] {error}")
    sys.exit(exit_code)

# command line
parser = argparse.ArgumentParser(
    prog="rsc2fgt",
    description="Converts from mikrotik configuration to a FortiGate terraform template."
)
parser.add_argument(
    "--config",
    required=True,
    help="Mikrotik configuration file."
)
parser.add_argument(
    "--sdwan",
    action="store_true",
    default=False,
    help="use the SDWAN interface on internet policies."
)
parser.add_argument(
    "--map-network",
    action="append",
    help="IP/MASK=interface. Maps an IP range to an interface name."
)
parser.add_argument(
    "--translate",
    action="append",
    help="SOURCE=TARGET. Maps a Mikrotik (SOURCE) interface to a FortiGate (TARGET) interface."
)
parser.add_argument(
    "--default-lan",
    help="Default LAN interface to use in FortiGate if we're unable to detect it."
)
parser.add_argument(
    "--default-wan",
    help="Default WAN interface to use in FortiGate if we're unable to detect it."
)
parser.add_argument(
    "--fortigate",
    required=True,
    help="IP:[PORT]. FortiGate IP address and port."
)
parser.add_argument(
    "--user",
    required=True,
    help="FortiGate user with admin privileges."
)
args = parser.parse_args()

# start
console.print("[bold]RSC2TF[/bold] convert Mikrotik NAT configuration to a FortiGate Terraform template.\n")
console.print(f"[bold]Configuration file    [/bold]: {args.config}")
console.print("[bold]Default LAN interface [/bold]: {default_lan}".format(
    default_lan=args.default_lan if args.default_lan is not None else "[bold red]not specified[/bold red]"
))
console.print("[bold]Default WAN interface [/bold]: {default_wan}".format(
    default_wan=args.default_wan if args.default_wan is not None else "[bold red]not specified[/bold red]"
))
console.print("[bold]Use SDWAN             [/bold]: {sdwan}".format(
    sdwan="Yes" if args.sdwan else "No"
))
console.print(f"[bold]FortiGate address     [/bold]: {args.fortigate}")
console.print(f"[bold]FortiGate username    [/bold]: {args.user}")

# config file
if os.path.exists(args.config):
    if not os.path.isfile(args.config):
        abort(f"'{args.config}' is not a file")
else:
    abort(f"configuration file '{args.config}' not found")

# interface to interface map
interface_map = InterfaceMap()

if args.translate is not None:
    console.print("\nProcessing [bold]interface to interface[/bold] translations.")
    for mapping in args.translate:
        try:
            (source, target) = interface_map.add_spec(mapping)
        except ValueError as exception:
            abort(exception)

        console.print(f"\t> added interface translation: '{source}' -> '{target}'")

# network to interface map
network_map = NetworkMap()
if args.map_network is not None:
    console.print("\nProcessing [bold]network to interface[/bold] translations.")

    for mapping in args.map_network:
        try:
            (source, target) = network_map.add_spec(mapping)
        except ValueError as exception:
            abort(exception)

        tokens = mapping.split("=")
        if len(tokens) != 2:
            abort(f"invalid network to port map '{mapping}'")

        console.print(f"\t> added network to interface translation: '{source}' -> '{target}'")

# read configuration file
console.print(f"\nReading [bold]configuration file[/bold] '{args.config}'.")

if os.path.exists(args.config):
    if not os.path.isfile(args.config):
        abort(f"'{args.config}' is not a file.")
else:
    abort(f"configuration file '{args.config}' not found")

with open(args.config, encoding="utf-8") as f:
    rsc_content = f.read().replace("\\\n    ", "")
    config_lines = rsc_content.splitlines()

# search for NAT section
try:
    nat_config_index = config_lines.index("/ip firewall nat")
except ValueError:
    abort(f"configuration file '{args.config}' doesn't appear to have a NAT configuration")

console.print("\nParsing NAT section.")
nat_seen_fields = set()
nat_rules = []
nat_rule_index = 1

for line in config_lines[nat_config_index+1:]:
    if line[0] == "/":
        break

    tokens = shlex.split(line)
    if tokens[0] == "add":
        rule = defaultdict(lambda: None)
        for token in tokens[1:]:
            (k, v) = token.split("=", maxsplit=1)
            rule[k] = v

        if rule["action"] == "dst-nat":
            nat_seen_fields.update(rule.keys())
            rule["index"] = nat_rule_index
            nat_rules.append(rule)
            nat_rule_index += 1


nat_seen_fields = list(nat_seen_fields)
nat_seen_fields.sort()

console.print(f"\t> [bold]{nat_rule_index}[/bold] destination NAT rule(s) found")

logging.debug(
    "seen firewall fields: %s",
    ", ".join(nat_seen_fields)
)

# create terraform.tfvars file
try:
    console.print(f"\nCreating [bold]'{TERRAFORM_VARS}'[/bold].")
    with open(TERRAFORM_VARS, mode="w", newline="", encoding="utf-8") as output:
        output.write(f"""fortigate_host     = "{args.fortigate}"
fortigate_username = "{args.user}"
#fortigate_password = """"")
except OSError as e:
    abort(f"unable to create file '{TERRAFORM_VARS}': {e}")

