import base64
import logging
import os
import re
import shutil
import json
import urllib.request
import urllib.error

from pathlib import Path
from git import Repo, Git
from packaging.utils import canonicalize_version
from packaging.version import Version

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

_remote_schema_cache = {}

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

def clone_central(refetch:bool=False):
    if refetch and os.path.exists("sources"):
        shutil.rmtree("sources")
    if not os.path.exists("sources"):
        Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS.git", "sources")
        shutil.rmtree("sources/.git")

def get_latest_version_commit(module):
    # Retrieves relevant commit for 'latest'
    git_instance = Git()
    branches = git_instance.ls_remote('--heads', module["repository"]).splitlines()
    semantic_to_branchname = {}
    branch_commit_map = {y[1]: y[0] for y in [x.split("\trefs/heads/") for x in branches] if
                        re.match("v[0-9]+.*", y[1])}
    for branch_name in list(branch_commit_map.keys()):
        semantic = canonicalize_version(branch_name)
        semantic = f"{semantic}.0" if "." not in semantic else semantic
        semantic_to_branchname[semantic] = branch_name
    version_numbers = list(semantic_to_branchname.keys())
    version_numbers.sort(key=Version, reverse=True)
    latest_branch_name = semantic_to_branchname[version_numbers[0]]
    return branch_commit_map[latest_branch_name]

def fetch_remote_schema_extends(extends_value, version_file, version):
    if extends_value in _remote_schema_cache:
        return _remote_schema_cache[extends_value]

    m = version_file[version]["modules"]
    module_name_extends = extends_value.split('/')[1]
    module = m.get(module_name_extends) or m.get(module_name_extends.upper())

    if version == 'latest':
        commit = get_latest_version_commit(module)
    else:
        commit = module['commit']

    extends_url = f"https://api.github.com/repos/openMetadataInitiative/{Path(module['repository']).stem}/contents/{'/'.join(extends_value.split('/')[2:])}?ref={commit}"

    try:
        with urllib.request.urlopen(extends_url) as response:
            response_formatted = json.load(response)
            decoded = base64.b64decode(response_formatted["content"]).decode("utf-8")
            schema = json.loads(decoded)
            _remote_schema_cache[extends_value] = schema
            return schema
    except urllib.error.HTTPError as e:
        logging.error(f"Error loading remote schema: {e}")
        return None

def find_openminds_class(version, class_name):
    """
    Imports a class from any available submodule.
    """
    directory = Path(f"./sources/schemas/{version}/")
    camel_case = class_name[:1].lower() + class_name[1:]

    # Search for exact filename matches
    for case in [camel_case, class_name]:
        for file_path in directory.glob(f"**/{case}.schema.omi.json"):
            return json.loads(file_path.read_text())
    return None

def expand_jsonld(data, context=None):
    """
    Recursively expands JSON-LD.
    """
    if isinstance(data, list):
        return [expand_jsonld(item, context) for item in data]
    elif not isinstance(data, dict):
        return data

    if not context:
        context = data.get('@context', {})

    for prop in data.copy().keys():
        value = expand_jsonld(data[prop], context)
        if prop.startswith("@"):
            continue
        elif (prefix := prop.split(':',1)[0]) in context.keys():
            data[context[prefix] + prop] = value
            del data[prop]
        else:
            data[context['@vocab'] + prop] = value
            del data[prop]

    if '@context' in data:
        del data['@context']
    return data

def version_key(version: str)->float:
    """
    Returns a key for sorting versions in inverse order (except the last version defined as the default value).
    """
    if version == 'latest':
        # Place "latest" at the end
        return float('inf')
    else:
        return -float(version[1:])
