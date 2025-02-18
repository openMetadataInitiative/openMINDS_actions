from pathlib import Path, PurePath

from openMINDS_validation.utils import load_json
from openMINDS_validation.models import VocabManager, Versions


class SchemaValidator(object):
    def __init__(self, absolute_path):
        self.absolute_path = absolute_path
        self.schema = load_json(absolute_path)

    def check_required(self, schema):
        """
        Validate required properties against the properties defined in the schema definition.
        """
        if 'required' in schema:
            for required in schema['required']:
                if required not in schema['properties'].keys():
                    raise SyntaxError(f'Missing required property: "{required}".')

    def check_attype(self, schema):
        if '_type' in schema:
            _type = schema['_type'].split(':|/')[-1]
            if not _type[0].isupper():
                raise ValueError(f'First character of @type "{_type}" should be uppercase.')


class InstanceValidator(object):
    def __init__(self, absolute_path):
        self.absolute_path = absolute_path
        self._tuple_path = PurePath(absolute_path).parts
        self.version = self._tuple_path[1]
        self.subfolder = self._tuple_path[2] if self._tuple_path[2] != 'terminologies' else self._tuple_path[3]
        self.file_name = Path(absolute_path).stem
        self.namespaces = Versions("./versions.json").versions[self.version]['namespaces']
        self.vocab = VocabManager("./types.json", "./properties.json")
        self.instance = load_json(absolute_path)

    def check_subfolder(self):
        # Probably not needed because it is already checked between @id and @type in check_missmatch_id_type
        instance_folder = self.instance['@id'].split('/')[-2]
        plural_instance_folder = instance_folder + 's' if not instance_folder.endswith('s') else instance_folder
        if self.subfolder != plural_instance_folder:
            raise ValueError(f'Instance in wrong subfolder, it should be in "{plural_instance_folder}".')

    def check_missmatch_id_type(self):
        # TODO Not able to check @id in list or instances
        # Schemas will need to be used to ensure the constraints are correctly applied
        if not all(key in self.instance for key in ('@id', '@type')):
            raise SyntaxError("Instance must contain both '@id' and '@type'.")

        _type_value = self.instance['@type'].split('/')[-1]
        _id_value = self.instance['@id'].split('/')[-1]

        if _type_value not in self.vocab.vocab_types or self.version not in self.vocab.vocab_types[_type_value]['isPartOfVersion']:
            raise ValueError(f'@type "{_type_value}" not found for "{self.version}" version.')

        for _type_namespace_version in self.vocab.vocab_types[_type_value]['hasNamespace']:
            if self.version in _type_namespace_version['inVersions']:
                if _type_namespace_version['namespace'] + _type_value != self.instance['@type']:
                    raise ValueError(f'Malformed @type: "{self.instance["@type"]}".')
                break

        _id = self.namespaces['instances']
        type_to_instance = {
            'ContentType':  f"{_id}contentTypes/{_id_value}",
            'License': f"{_id}licenses/{_id_value}",
        }
        default_id = f"{_id}{_type_value[0].lower()}{_type_value[1:]}/{_id_value}"

        expected_id = type_to_instance.get(_type_value, default_id)
        if self.instance['@id'] != expected_id:
            raise ValueError(f'Mismatch between @id "{self.instance["@id"]}" and @type "{self.instance["@type"]}".')

    def check_atid_convention(self):

        def _check_instance_id_convention(value):
            if value is not None and '@id' in value:
                if ' ' in value['@id']:
                    raise ValueError(f'White space detected for @id: "{value["@id"]}".')

        # TODO use a dictionary of abbreviations and Upper case name
        if '@id' in self.instance:
            _id_value = self.instance['@id'].split('/')[-1]
            # TODO instead of using filename (abbreviations and other properties should be used)
            if _id_value != self.file_name:
                raise ValueError(f'@id entity {_id_value} does not match the file name {self.file_name}.')
            _check_instance_id_convention(self.instance)

        for property in self.instance:
            if self.instance[property] is not None and type(self.instance[property]) is dict and '@id' in self.instance[property]:
                _check_instance_id_convention(self.instance[property])
            if type(self.instance[property]) is list and len(self.instance[property]) > 0:
                for instance_element in self.instance[property]:
                    _check_instance_id_convention(instance_element)

    def check_property(self):
        """
        Validate instance properties against the vocabulary for the current version.
        """
        for property in self.instance:
            if property in ('@context', '@id', '@type'):
                continue

            if property not in self.vocab.vocab_properties:
                raise ValueError(f'Unknown property "{property}".')

            if self.instance['@type'] not in self.vocab.vocab_properties[property]["usedIn"][self.version]:
                raise ValueError(f'Property "{property}" not available for type "{self.instance["@type"]}" in version {self.version}.')

    def validate(self):
        self.check_subfolder()
        self.check_missmatch_id_type()
        self.check_atid_convention()
        self.check_property()
