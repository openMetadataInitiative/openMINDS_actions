import logging
import sys

from openMINDS_validation.validation import InstanceValidator


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logging.error("Usage: python validate_instance.py <src_file>")
        sys.exit(1)

    InstanceValidator(sys.argv[1]).validate()
