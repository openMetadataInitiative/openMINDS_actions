import re
import logging
from pathlib import Path, PurePath

from openMINDS_validation.utils import VocabManager, Versions, load_json, clone_specific_source_with_specs, version_key, find_openminds_class

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

class SchemaValidator(object):
    def __init__(self, absolute_path, repository=None, branch=None):
        self.absolute_path = absolute_path
        self.schema = load_json(absolute_path)
        self.repository = repository
        self.branch = branch
        self.openMINDS_build_version = None

        self.version_file = Versions("./versions.json").versions

    def check_attype(self):
        """
        Validates the format of the _type in the schema definition:
            - First character of _type is in uppercase.
        """
        if '_type' in self.schema:
            type_schema_name = re.split("[:/]", self.schema['_type'])[-1]
            if not type_schema_name[0].isupper():
                logging.error(f'First character of _type "{type_schema_name}" should be uppercase.')

    def check_extends(self):
        """
        Validates the existence of schema for the _extends property.
        """
        if '_extends' not in self.schema:
            return

        path_prefix_extends = './sources' if self.schema['_extends'].startswith("/") else './schemas/'

        if path_prefix_extends == './sources':
            # Needs optimization: finding the corresponding openMINDS version and module
            versions_spec = sorted(list(self.version_file.keys()), key=version_key)
            module_name_extends = self.schema['_extends'].split('/')[1]
            for version_number in versions_spec:
                m = self.version_file[version_number]["modules"]
                self.openMINDS_build_version = version_number

                matched_extends_submodule = any(
                    submodule.get("repository") == self.repository and
                    submodule.get("branch") == self.branch
                    for submodule in m.values()
                )

                module = m.get(module_name_extends) or m.get(module_name_extends.upper())
                if matched_extends_submodule:
                    clone_specific_source_with_specs(module_name_extends, module, self.openMINDS_build_version)
                    break

                # By default, '_extends' is compared against 'latest'
                if version_number == 'latest':
                    clone_specific_source_with_specs(module_name_extends, module, self.openMINDS_build_version)

        path_extends_schema = f"{path_prefix_extends}/{self.openMINDS_build_version}{self.schema['_extends']}" if self.openMINDS_build_version else f"{path_prefix_extends}{self.schema['_extends']}"
        try:
            file = open(path_extends_schema, 'r')
        except FileNotFoundError:
            logging.error(f'Schema not found for the property _extends at "{path_extends_schema}".')

    def check_required(self):
        """
        Validates required properties against the properties defined in the schema definition.
        """
        def _check_required_extends(extends_value, required_property, openMINDS_build_version=self.openMINDS_build_version):
            path_prefix_extends = f"./sources/{openMINDS_build_version}" if extends_value.startswith("/") else './schemas/'
            path_extends_schema = path_prefix_extends + extends_value
            extended_schema = load_json(path_extends_schema)
            if required_property not in extended_schema['properties']:
                if '_extends' in extended_schema:
                    return _check_required_extends(extended_schema['_extends'], required_property)
                logging.error(f'Missing required property "{required_property}" in the schema definition.')
            return

        if 'required' not in self.schema:
            return

        for required_property in self.schema['required']:
            if required_property not in self.schema['properties'].keys():
                if '_extends' in self.schema:
                    _check_required_extends(self.schema['_extends'], required_property)
                    continue
                logging.error(f'Missing required property "{required_property}" in the schema definition.')

    def validate(self):
        """
        Runs all the tests defined in SchemaValidator.
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
        self._type_schema_name = None
        self._id_schema_name = None

    def check_atid_convention(self):
        """
        Validates against:
            - White space in @id and embedded @id.
            - Differences between file name and @id.
        """
        def _check_instance_id_convention(instance):
            if instance is not None and '@id' in instance:
                if ' ' in instance['@id']:
                    logging.error(f'White space detected for @id: "{instance["@id"]}".')
                if instance['@id'].count('/') != 5:
                    logging.error(f'Unexpected number of "/" for @id: "{instance["@id"]}".')

        # TODO use a dictionary of abbreviations and Upper case name
        _id_instance_name = self.instance['@id'].split('/')[-1]
        # TODO instead of using filename (abbreviations and other properties could be used)
        if _id_instance_name != self.file_name:
            logging.error(f'Mismatch between @id entity "{_id_instance_name}" and file name "{self.file_name}".')
        _check_instance_id_convention(self.instance)

        for property in self.instance:
            if self.instance[property] is not None and type(self.instance[property]) is dict and '@id' in self.instance[property]:
                _check_instance_id_convention(self.instance[property])
            if type(self.instance[property]) is list and len(self.instance[property]) > 0:
                for instance_element in self.instance[property]:
                    _check_instance_id_convention(instance_element)

    def check_missmatch_id_type(self):
        """
        Validates against:
            - missing @id/@type.
            - @type not found in vocab for the given version.
            - namespace of @type.
            - mismatch of @type and @id.
        """
        if self._type_schema_name not in self.vocab.vocab_types or self.version not in self.vocab.vocab_types[self._type_schema_name]['isPartOfVersion']:
            logging.error(f'@type "{self._type_schema_name}" not found for "{self.version}" version.')

        for _type_namespace_version in self.vocab.vocab_types[self._type_schema_name]['hasNamespace']:
            if self.version in _type_namespace_version['inVersions']:
                expected_type = _type_namespace_version['namespace'] + self._type_schema_name
                if expected_type != self.instance['@type']:
                    logging.error(f'Unexpected namespace for @type: "{self.instance["@type"]}".')
                break

        if self._id_schema_name in ['licenses', 'contentTypes']:
            # self._type_schema_name is not using plural
            expected_type_name = self._id_schema_name[0].upper() + self._id_schema_name[1:-1]
        else:
            expected_type_name = self._id_schema_name[0].upper() + self._id_schema_name[1:]
        if expected_type_name != self._type_schema_name:
            logging.error(f'Mismatch between @id schema name "{self._id_schema_name}" and @type schema name "{self._type_schema_name}".')

    def check_property_existence(self):
        """
        Validates instance properties against the vocabulary for the given version and type.
        """
        for property in self.instance:
            if property in ('@context', '@id', '@type'):
                continue

            if property not in self.vocab.vocab_properties:
                logging.error(f'Unknown property "{property}".')

            if self.instance['@type'] not in self.vocab.vocab_properties[property]["usedIn"][self.version]:
                logging.error(f'Property "{property}" not available for type "{self.instance["@type"]}" in version "{self.version}".')

    def check_property_constraint(self):
        """
        Validates the presence and values of required and optional properties in the instance.
        """
        # TODO check nested properties
        openminds_class = find_openminds_class(f"openminds.{self.version}", self._type_schema_name)
        openminds_class_properties = getattr(openminds_class, 'properties')
        required_properties = [p.path for p in openminds_class_properties if p.required == True]
        optional_properties = list(set([p.path for p in openminds_class_properties]) - set(required_properties))

        for required_property in required_properties:
            if required_property not in self.instance:
                logging.error(f'Missing required property "{required_property}".')
            if required_property in self.instance and self.instance[required_property] in (None, '', ' '):
                logging.error(f'Required property "{required_property}" is not defined.')
        for optional_property in optional_properties:
            if optional_property not in self.instance:
                logging.error(f'Missing optional property "{optional_property}".')
            if optional_property in self.instance and self.instance[optional_property] in ('', ' '):
                logging.info(f'Unexpected value "{self.instance[optional_property]}" for "{optional_property}".')

    def check_minimal_jsonld_structure(self):
        """
        Check if @id and @type are present in the instance.
        """
        # TODO Check @id in lists or instances when needed
        # Schemas will need to be used to ensure that the constraints are correctly applied
        if not all(key in self.instance for key in ('@id', '@type')):
            logging.error("Instance must contain both @id and @type.")

        self._type_schema_name = self.instance['@type'].split('/')[-1]
        self._id_schema_name = self.instance['@id'].split('/')[-2]

    def validate(self):
        """
        Run all the tests defined in InstanceValidator.
        """
        self.check_minimal_jsonld_structure()
        self.check_atid_convention()
        self.check_missmatch_id_type()
        self.check_property_existence()
        self.check_property_constraint()
