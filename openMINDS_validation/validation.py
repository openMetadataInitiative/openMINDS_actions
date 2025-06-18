import re
import logging
import json
import urllib.request
import urllib.error
from pathlib import Path, PurePath

from openMINDS_validation.utils import VocabManager, Versions, load_json, get_latest_version_commit, version_key, \
    find_openminds_class, clone_central, expand_jsonld, fetch_remote_schema_extends

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

class SchemaTemplateValidator(object):
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

        location = 'remote' if self.schema['_extends'].startswith("/") else './schemas/'
        # _extends located in other repository
        if location == 'remote':
            # Needs optimization: finding the corresponding openMINDS version and module
            versions_spec = sorted(list(self.version_file.keys()), key=version_key)
            module_name_extends = self.schema['_extends'].split('/')[1]
            extends_url = None
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
                    extends_url = f"https://api.github.com/repos/openMetadataInitiative/{Path(module['repository']).stem}/contents/{'/'.join(self.schema['_extends'].split('/')[2:])}?ref={module['commit']}"
                    break

                # By default, '_extends' is compared against 'latest'
                elif version_number == 'latest':
                    commit = get_latest_version_commit(module)
                    extends_url = f'https://api.github.com/repos/openMetadataInitiative/{Path(module["repository"]).stem}/contents/{"/".join(self.schema["_extends"].split("/")[2:])}?ref={commit}'
                    break
            try:
                urllib.request.urlopen(extends_url)
            except urllib.error.HTTPError:
                logging.error(f'Schema not found for the property _extends "{self.schema["_extends"]}".')
        # _extends located in same repository
        else:
            # Checks for openMINDS_actions/schemas/_extends
            path_extends_schema = f"{location}{self.schema['_extends']}"
            try:
                open(path_extends_schema, 'r')
            except FileNotFoundError:
                logging.error(f'Schema not found for the property _extends at "{self.schema["_extends"]}".')

    def check_required(self):
        """
        Validates required properties against the properties defined in the schema definition.
        """
        def load_schema(path):
            if path.startswith("/"):
                return fetch_remote_schema_extends(path, self.version_file, self.openMINDS_build_version)
            return load_json(f'./schemas/{path}')

        def _check_required_extends(extends_path, required_property):
            schema = load_schema(extends_path)
            if required_property not in schema['properties']:
                if '_extends' in schema:
                    return _check_required_extends(schema['_extends'], required_property)
                logging.error(f'Missing required property "{required_property}" in the schema definition.')
            return

        def _retrieve_inherited_required_properties(extends_path):
            schema = load_schema(extends_path)
            inherited_properties_required = schema.get('required', [])
            if '_extends' in schema:
                inherited_properties_required.extend(_retrieve_inherited_required_properties(schema['_extends']))
            return inherited_properties_required

        if 'required' not in self.schema:
            return
        if '_type' not in self.schema and '_extends' not in self.schema:
            return

        required_properties = self.schema.get('required', [])
        if '_extends' in self.schema:
            required_properties.extend(_retrieve_inherited_required_properties(self.schema['_extends']))

        for required_property in required_properties:
            if required_property not in self.schema['properties'].keys():
                if '_extends' in self.schema:
                    _check_required_extends(self.schema['_extends'], required_property)
                    continue
                logging.error(f'Missing required property "{required_property}" in the schema definition.')

    def validate(self):
        """
        Runs all the tests defined in SchemaTemplateValidator.
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

    def _nested_instance(self, value, function, instance_type):
        if isinstance(value, dict):
            function(value, instance_type)

        elif isinstance(value, list):
            for item in value:
                self._nested_instance(item, function, instance_type)

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

    def check_property_existence(self, instance=None, instance_type=None):
        """
        Validates instance properties against the vocabulary for the given version and type.
        """
        instance = instance if instance is not None else self.instance
        instance_type = instance_type if instance_type is not None else instance.get('@type')

        # Skip validation if no type is defined
        if not instance_type:
            return

        for property in instance:
            if property in ('@context', '@id', '@type'):
                continue
            elif property not in self.vocab.vocab_properties:
                logging.error(f'Unknown property "{property}".')
                continue
            elif instance['@type'] not in self.vocab.vocab_properties[property]["usedIn"][self.version]:
                logging.error(f'Property "{property}" not available for type "{instance_type}" in version "{self.version}".')
                continue
            self._nested_instance(instance[property], self.check_property_existence, instance_type)

    def check_property_constraint(self, instance=None, instance_type=None, openminds_class=None):
        """
        Validates the presence and values of required and optional properties in the instance.
        """
        instance = instance if instance is not None else self.instance
        if '@type' in instance:
            instance_type = instance.get('@type').split('/')[-1]
        # Skip validation if no @type
        else:
            return

        openminds_class = find_openminds_class(self.version, instance_type)
        openminds_class_properties =  openminds_class["properties"].keys() if 'properties' in openminds_class else None
        required_properties = openminds_class["required"] if 'required' in openminds_class else None
        optional_properties = list(set(openminds_class_properties) - set(required_properties))

        if "@context" in instance:
            instance = expand_jsonld(instance)

        for required_property in required_properties:
            if required_property not in instance:
                logging.error(f'Missing required property "{required_property}".')
            elif required_property in instance and instance[required_property] in (None, '', ' '):
                logging.error(f'Required property "{required_property}" is not defined.')
            if required_property in instance:
                self._nested_instance(instance[required_property], self.check_property_constraint, instance_type)
        for optional_property in optional_properties:
            if optional_property not in instance:
                logging.error(f'Missing optional property "{optional_property}".')
            elif optional_property in instance and instance[optional_property] in ('', ' '):
                logging.warning(f'Unexpected value "{instance[optional_property]}" for "{optional_property}".')
            if optional_property in instance:
                self._nested_instance(instance[optional_property], self.check_property_constraint, instance_type)

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
        clone_central()
        self.check_minimal_jsonld_structure()
        self.check_atid_convention()
        self.check_missmatch_id_type()
        self.check_property_existence()
        self.check_property_constraint()
