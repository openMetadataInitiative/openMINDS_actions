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

def clone_sources_with_specs(modules):
    if os.path.exists("sources"):
        shutil.rmtree("sources")

    for module, spec in modules.items():
        repo = Repo.clone_from(spec["repository"], f"sources/{module}", no_checkout=True)
        repo.git.checkout()
