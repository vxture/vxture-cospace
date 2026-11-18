"""Native parser entry point for the isolated IFC worker environment."""
import sys

from packages.data.ifc_structure import inspect_ifc_structure


def main():
    source, output, expected_sha256 = sys.argv[1:]
    inspect_ifc_structure(source, output, expected_sha256=expected_sha256)


if __name__ == '__main__':
    main()
