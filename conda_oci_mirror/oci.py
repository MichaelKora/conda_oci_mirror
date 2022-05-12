import tarfile
import json
import pathlib

from io import BytesIO

import requests

from conda_oci_mirror import constants as C
from conda_oci_mirror.util import get_github_auth
from conda_oci_mirror.util import sha256sum


class OCI:
    def __init__(self, location, user_or_org):
        self.location = location
        self.user_or_org = user_or_org
        self.session_map = {}

    def full_package(self, package):
        if package.startswith(self.user_or_org + "/"):
            return package
        return f"{self.user_or_org}/{package}"

    def oci_auth(self, package, scope="pull"):
        package = self.full_package(package)
        if package in self.session_map:
            return self.session_map[package]

        url = f"{self.location}/token?scope=repository:{package}:{scope}"
        auth = get_github_auth()

        r = requests.get(url, auth=auth)
        j = r.json()

        oci_session = requests.Session()
        oci_session.headers = {"Authorization": f'Bearer {j["token"]}'}
        self.session_map[package] = oci_session
        return oci_session

    def get_blob(self, package, digest, stream=False):
        package = self.full_package(package)

        url = f"{self.location}/v2/{package}/blobs/{digest}"
        oci_session = self.oci_auth(self.location, package)
        res = oci_session.get(url, stream=stream)
        return res

    def get_tags(self, package, n_tags=10_000, prev_last=None):
        package = self.full_package(package)
        print(f"Getting tags for {package}")
        url = f"{self.location}/v2/{package}/tags/list?n={n_tags}"
        if prev_last:
            url += "&last=prev_last"
        oci_session = self.oci_auth(self.location, package)

        tags = []
        link = True
        # get all tags using the pagination
        while link:
            res = oci_session.get(url)
            if not res.ok:
                return []

            if res.headers.get("Link"):
                link = res.headers.get("Link")
                assert link.endswith('; rel="next"')
                next_link = link.split("<")[len(link.split("<")) - 1].split(">")[0]
                url = self.location + next_link
            else:
                link = None

            tags += res.json()["tags"]

        return tags

    def get_manifest(self, package, tag):
        package = self.full_package(package)

        url = f"{self.location}/v2/{package}/manifests/{tag}"

        oci_session = self.oci_auth(package)
        headers = {"accept": "application/vnd.oci.image.manifest.v1+json"}
        r = oci_session.get(url, headers=headers)

        return r.json()

    def _find_digest(self, package, tag, media_type):
        package = self.full_package(package)

        url = f"{self.location}/v2/{package}/manifests/{tag}"

        oci_session = self.oci_auth(package)
        headers = {"accept": "application/vnd.oci.image.manifest.v1+json"}
        r = oci_session.get(url, headers=headers)

        j = r.json()
        for x in j["layers"]:
            if x["mediaType"] == media_type:
                digest = x["digest"]
        return digest

    def get_info(self, package, tag):
        digest = self._find_digest(package, tag, C.info_archive_media_type)
        res = self.get_blob(package, digest, stream=False)
        return tarfile.open(fileobj=BytesIO(res.content), mode="r:gz")

    def get_index_json(self, package, tag):
        digest = self._find_digest(package, tag, C.info_index_media_type)
        return self.get_blob(package, digest).json()

    def push_image(self, _base_path,remote_location, package, _reference, description_annotation, _layers):

        manifest_dict = {"schemaVersion":2,"mediaType": "application/vnd.oci.image.manifest.v1+json","config":{}, "layers":[],"annotations":{}}    
        gh_session = self.oci_auth(package, scope="push,pull")
        pkg_name = package
        
        for layer in _layers:

            r = gh_session.post(f"https://ghcr.io/v2/{self.user_or_org}/{remote_location}/{pkg_name}/blobs/uploads/")
            headers = r.headers
            location = headers['location']
            layer_path = _base_path / layer.file

            #update the manifest
            _media_type = layer.media_type
            _size = pathlib.Path(layer_path).stat().st_size
            digest = sha256sum(layer_path)
            _digest = "sha256:" + digest
            
            annotations_dict = layer.annotations
            if annotations_dict:
                infos = {"mediaType":_media_type,"size":_size,"digest":_digest, "annotations": annotations_dict}
            else:
                infos = {"mediaType":_media_type,"size":_size,"digest":_digest}
            manifest_dict["layers"].append(infos)

            # push the layer
            push_url = f"https://ghcr.io{location}?digest={_digest}"
            _headers = { "Content-Length": str(_size),"Content-Type": "application/octet-stream"}
            with open(str(layer_path), "rb") as f:
                r2 = gh_session.put(push_url, data=f, headers=_headers)
                
        manifest_dict["annotations"] = description_annotation
        manifest_path = _base_path / "manifest.json"

        conf_path = _base_path / "config.json"
        config_dict = {}
        with open(conf_path, "w") as write_file:
            json.dump(config_dict, write_file)
        _conf_size = pathlib.Path(conf_path).stat().st_size
        _conf_sha = sha256sum(conf_path)
        _conf_digest = "sha256:" + _conf_sha
        conf = {"mediaType": "application/vnd.oci.image.config.v1+json","size": _conf_size, "digest": _conf_digest}
        manifest_dict ["config"] = conf

        with open(manifest_path, "w") as write_file:
            json.dump(manifest_dict, write_file)

        _mnfst_headers = { "Content-Type": "application/vnd.oci.image.manifest.v1+json"}
        ref = _reference
        mnfst_url = f"https://ghcr.io/v2/{self.user_or_org}/{remote_location}/{pkg_name}/manifests/{ref}"

        with open(str(manifest_path), "rb") as f:
            r_manfst = gh_session.put(mnfst_url, data=f, headers=_mnfst_headers)
            