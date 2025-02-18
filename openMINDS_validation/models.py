from openMINDS_validation.utils import load_json, download_file


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
