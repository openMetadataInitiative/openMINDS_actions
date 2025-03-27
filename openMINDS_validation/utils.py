import logging
import os
import shutil
import json
import urllib.request
import urllib.error

from git import Repo

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

class VocabManager:
    def __init__(self, path_vocab_types, path_vocab_properties):
        # TODO handle dev
        download_file("https://raw.githubusercontent.com/openMetadataInitiative/openMINDS/refs/heads/main/vocab/properties.json", path_vocab_properties)
        download_file(
            "https://raw.githubusercontent.com/openMetadataInitiative/openMINDS/refs/heads/main/vocab/types.json",
            path_vocab_types)
        self.vocab_types = load_json(path_vocab_types)
        self.vocab_properties = load_json(path_vocab_properties)


class Versions:
    def __init__(self, path_versions):
        # TODO handle dev, update it to download schema sources for improved validation
        download_file(
            "https://raw.githubusercontent.com/openMetadataInitiative/openMINDS/refs/heads/pipeline/versions.json",
            path_versions)
        self.versions = load_json(path_versions)

def load_json(path):
    with open(path) as f:
        json_file = json.load(f)
    return json_file

def download_file(url, path):
    try:
        urllib.request.urlretrieve(url, path)
    except (urllib.error.URLError, IOError) as e:
        logging.error(e)

def clone_sources_with_specs(modules, openMINDS_version):
    if os.path.exists(f"sources/{openMINDS_version}"):
        shutil.rmtree(f"sources/{openMINDS_version}")

    for module, spec in modules.items():
        repo = Repo.clone_from(spec["repository"], f"sources/{openMINDS_version}/{module}", no_checkout=True)
        repo.git.checkout()

def clone_specific_source_with_specs(module_name, module, openMINDS_version):
    if os.path.exists(f"sources/{openMINDS_version}"):
        shutil.rmtree(f"sources/{openMINDS_version}")

    repo = Repo.clone_from(module["repository"], f"sources/{openMINDS_version}/{module_name}", no_checkout=True)
    if 'commit' in module:
        repo.git.checkout(module['commit'])
    else:
        repo.git.checkout()

def version_key(version: str)->float:
    """ Returns a key for sorting versions in inverse order (except the last version defined as the default value) """
    if version == 'latest':
        # Place "latest" at the end
        return float('inf')
    else:
        return -float(version[1:])
