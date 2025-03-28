import logging
import sys

from openMINDS_validation.validation import SchemaValidator


if __name__ == "__main__":
    if len(sys.argv) != 4:
        logging.error("Usage: python validate_instance.py <src_file> <src_repository> <src_branch>")
        sys.exit(1)

    SchemaValidator(sys.argv[1], sys.argv[2], sys.argv[3]).validate()
