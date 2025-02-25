import re
from pathlib import Path, PurePath

from openMINDS_validation.utils import load_json, clone_sources_with_specs
from openMINDS_validation.models import VocabManager, Versions


class SchemaValidator(object):
    def __init__(self, absolute_path):
        self.absolute_path = absolute_path
        self.schema = load_json(absolute_path)

        self.version_file = Versions("./versions.json").versions

    def check_required(self):
        """
        Validate required properties against the properties defined in the schema definition.
        """
        def _check_required_extends(extends_value, required_property):
            path_prefix_extends = './sources' if extends_value.startswith("/") else './schemas/'
            path_extends_schema = path_prefix_extends + extends_value
            extended_schema = load_json(path_extends_schema)
            if required_property not in extended_schema['properties']:
                if '_extends' in extended_schema:
                    return _check_required_extends(extended_schema['_extends'], required_property)
                raise SyntaxError(f'Missing required property "{required_property}" in the schema definition.')
            return

        if 'required' not in self.schema:
            return

        for required_property in self.schema['required']:
            if required_property not in self.schema['properties'].keys():
                if '_extends' in self.schema:
                    _check_required_extends(self.schema['_extends'], required_property)
                    continue
                raise SyntaxError(f'Missing required property "{required_property}" in the schema definition.')

    def check_attype(self):
        """
        Validate the format of the _type in the schema definition:
            - First character of _type is in uppercase.
        """
        if '_type' in self.schema:
            type_schema_name = re.split("[:/]", self.schema['_type'])[-1]
            if not type_schema_name[0].isupper():
                raise ValueError(f'First character of _type "{type_schema_name}" should be uppercase.')

    def check_extends(self):
        """
        Validate existence of schema for the _extends property.
        """
        if '_extends' not in self.schema:
            return

        path_prefix_extends = './sources' if self.schema['_extends'].startswith("/") else './schemas/'
        path_extends_schema = path_prefix_extends + self.schema['_extends']

        if path_prefix_extends == './sources':
            clone_sources_with_specs(self.version_file["latest"]["modules"])

        try:
            file = open(path_extends_schema, 'r')
        except FileNotFoundError:
            raise ValueError(f'Schema not found for the property _extends at "{path_extends_schema}".')

    def validate(self):
        """
        Run all the tests defined in SchemaValidator.
        """
        self.check_attype()
        self.check_extends()
        self.check_required()

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

        self._type_schema_name = self.instance['@type'].split('/')[-1]
        self._id_schema_name = self.instance['@id'].split('/')[-2]

    def check_id_schema_name_exception(self):
        """
        Validate that the schema name in the @id matches the expected @type for the exceptions 'License' and 'ContentType' types.
        """
        if self._type_schema_name in ['License', 'ContentType']:
            if self._id_schema_name not in ['licenses', 'contentTypes']:
                raise ValueError(f'Wrong @id schema name, it should be "licences" or "contentTypes" instead of "{self._id_schema_name}".')

    def check_missmatch_id_type(self):
        """
        Validate against:
            - missing @id/@type.
            - @type not found in vocab for the given version.
            - namespace of @type.
            - mismatch of @type and @id.
        """
        # TODO Not able to check @id in list or instances
        # Schemas will need to be used to ensure the constraints are correctly applied
        if not all(key in self.instance for key in ('@id', '@type')):
            raise SyntaxError("Instance must contain both @id and @type.")

        if self._type_schema_name not in self.vocab.vocab_types or self.version not in self.vocab.vocab_types[self._type_schema_name]['isPartOfVersion']:
            raise ValueError(f'@type "{self._type_schema_name}" not found for "{self.version}" version.')

        for _type_namespace_version in self.vocab.vocab_types[self._type_schema_name]['hasNamespace']:
            if self.version in _type_namespace_version['inVersions']:
                expected_type = _type_namespace_version['namespace'] + self._type_schema_name
                if expected_type != self.instance['@type']:
                    raise ValueError(f'Unexpected namespace for @type: "{self.instance["@type"]}".')
                break

        if self._id_schema_name in ['licenses', 'contentTypes']:
            # self._type_schema_name is not using plural
            expected_type_name = self._id_schema_name[0].upper() + self._id_schema_name[1:-1]

        else:
            expected_type_name = self._id_schema_name[0].upper() + self._id_schema_name[1:]
        if expected_type_name != self._type_schema_name:
            raise ValueError(f'Mismatch between @id schema name "{self._id_schema_name}" and @type schema name "{self._type_schema_name}".')

    def check_atid_convention(self):
        """
        Validate against:
            - White space in @id and embedded @id.
            - Differences between file name and @id.
        """
        def _check_instance_id_convention(instance):
            if instance is not None and '@id' in instance:
                if ' ' in instance['@id']:
                    raise ValueError(f'White space detected for @id: "{instance["@id"]}".')

        # TODO use a dictionary of abbreviations and Upper case name
        if '@id' in self.instance:
            _id_instance_name = self.instance['@id'].split('/')[-1]
            # TODO instead of using filename (abbreviations and other properties could be used)
            if _id_instance_name != self.file_name:
                raise ValueError(f'Mismatch between @id entity "{_id_instance_name}" and file name "{self.file_name}".')
            _check_instance_id_convention(self.instance)

        for property in self.instance:
            if self.instance[property] is not None and type(self.instance[property]) is dict and '@id' in self.instance[property]:
                _check_instance_id_convention(self.instance[property])
            if type(self.instance[property]) is list and len(self.instance[property]) > 0:
                for instance_element in self.instance[property]:
                    _check_instance_id_convention(instance_element)

    # TODO check if required and optional properties are included and their values
    def check_property(self):
        """
        Validate instance properties against the vocabulary for the given version and type.
        """
        for property in self.instance:
            if property in ('@context', '@id', '@type'):
                continue

            if property not in self.vocab.vocab_properties:
                raise ValueError(f'Unknown property "{property}".')

            if self.instance['@type'] not in self.vocab.vocab_properties[property]["usedIn"][self.version]:
                raise ValueError(f'Property "{property}" not available for type "{self.instance["@type"]}" in version {self.version}.')

    def validate(self):
        """
        Run all the tests defined in InstanceValidator.
        """
        self.check_id_schema_name_exception()
        self.check_missmatch_id_type()
        self.check_property()
        self.check_atid_convention()
