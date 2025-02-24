import os
import shutil
import json
import urllib.request
import urllib.error

from git import Repo


def load_json(path):
    with open(path) as f:
        json_file = json.load(f)
    return json_file

def download_file(url, path):
    try:
        urllib.request.urlretrieve(url, path)
    except (urllib.error.URLError, IOError) as e:
        print(e)

def clone_sources():
    # cloning central repo (for schemas)
    if os.path.exists("sources_schemas"):
        shutil.rmtree("sources_schemas")
    Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS.git", to_path="sources_schemas", depth=1)

    # cloning instances repo (for instances)
    if os.path.exists("sources_instances"):
        shutil.rmtree("sources_instances")
    Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS_instances.git", to_path="sources_instances", depth=1)

def clone_sources_with_specs(modules, version):
    print(f"Now building the version {version}")
    for module, spec in modules.items():
        print(f"Cloning module {module} in commit {spec.commit}")
        repo = Repo.clone_from(spec.repository, f"sources/{module}", no_checkout=True)
        repo.git.checkout(spec.commit)
