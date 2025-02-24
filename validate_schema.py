import sys

from openMINDS_validation.validation import SchemaValidator


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_instance.py <src_file>")
        sys.exit(1)

    SchemaValidator(sys.argv[1]).validate()
