import json
from pathlib import Path


def compare_checksums(base, all_subdirs):
    differences = {"linux-64": [], "osx-64": [], "osx-arm64": [], "win-64": [], "linux-aarch64": [], "linux-ppc64le": [], "noarch": []}
    for subdir in all_subdirs:
        location = Path(base) / subdir
        if location.exists():
            repodata_checksums_path = location / "repodata_checksums.json"
            manifests_checksums_path = location / "manifest_checksums.json"

            with open(repodata_checksums_path) as fi:
                dict_repo_checksums = json.load(fi)

            with open(manifests_checksums_path) as fi:
                dict_manfst_checksums = json.load(fi)

            for key in dict_repo_checksums.keys():
                for sub_key in dict_repo_checksums[key].keys():
                    repo_check = dict_repo_checksums[key][sub_key]
                    manfst_check = dict_manfst_checksums[key][sub_key]
                    if repo_check != manfst_check:
                        differences[subdir].append(sub_key)

    return differences


def dict_is_empty(dict):
    for key in dict:
        if len(dict[key]) != 0:
            return False
    return True