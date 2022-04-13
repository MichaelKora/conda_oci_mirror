import json
import logging
import pathlib
from datetime import datetime

# from conda_oci_mirror.oci import OCI
from conda_oci_mirror.oras import ORAS, Layer

# from pathlib import Path


# oci = OCI("https://ghcr.io", "MichaelKora")

all_sub_dirs = [
    "linux-64",
    "osx-64",
    "osx-arm64",
    "win-64",
    "linux-aarch64",
    "linux-ppc64le",
    "noarch",
]


def get_all_packages(repodata):
    found_packages = []
    for key in repodata["packages"]:
        found_packages.append(key)
    return found_packages


def upload_index_json(global_index, channel, remote_loc):
    for key in global_index:
        # itterate throughevery pkg. e.g: zlib
        subdir = global_index["info"]["subdir"]
        index_file = {"info": {"subdir": {}}}
        index_file["info"]["subdir"] = subdir

        if key != "info":
            index_file["name"] = key

            # go through all the versions of a specific package. eg: zlib-12.0-1. zlib-12.0-2
            for pkg in global_index[key]:
                pkg_name = pkg["name"] + "-" + pkg["version"] + "-" + pkg["build"]
                index_file[pkg_name] = pkg

            dir_index = pathlib.Path(channel) / subdir / key
            dir_index.mkdir(mode=511, parents=True, exist_ok=True)

            json_object = json.dumps(index_file, indent=4)

            index_path = dir_index / "index.json"

            with open(index_path, "w") as write_file:
                json.dump(json_object, write_file)

            logging.warning("upload the index.json file...")
            upload_path = channel + "/" + subdir + "/" + index_file["name"] + "/index.json"

            now = datetime.now()
            tag = now.strftime("%d%m%Y%H%M%S")
            oras = ORAS(base_dir=dir_index)
            media_type = "application/json"
            layers = [Layer("index.json", media_type)]
            logging.warning(f"upload the json file for <<{key}>>")

            oras.push(
                f"{remote_loc}/{upload_path}", tag, layers
            )
            oras.push(
                f"{remote_loc}/{upload_path}", "latest", layers
            )

            logging.warning(f"index.json successfuly uploaded for {key}!")
            print(json_object)
