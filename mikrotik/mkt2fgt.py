import argparse
import shlex

import pprint

from collections import defaultdict
from os.path import isfile
from sys import exit


# command line
parser = argparse.ArgumentParser(description="Converts mikrotik configuration sections to fortigate")
parser.add_argument("--mikrotik-config", help="mikrotik config file", required=True)
parser.add_argument("--fortigate-config", help="output forgitate config file", required=True)
parser.add_argument('--ppp-users', help="convert ppp users to local users", default=False, action='store_true')
args = parser.parse_args()

print(args)

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
        o.write("config user local\n")
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

#
o.close()
print("--- done")
