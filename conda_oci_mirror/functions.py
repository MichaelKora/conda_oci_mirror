def get_all_packages(repodata):
    found_packages = []
    for key in repodata["packages"]:
        found_packages.append(key)
    return found_packages
