"""Export exact synthetic component bytes; does not publish or install a package."""
import argparse
from pathlib import Path

from experiments.scripts.consume_scene_subset import load
from packages.views.agent.scene_exchange import write_exchange
from packages.views.agent.scene_subset import MAX_PACKAGE_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    write_exchange(load(args.package, args.input_root, MAX_PACKAGE_BYTES),
                   load(args.expected_source, args.input_root, 4096), args.output_dir)


if __name__ == '__main__':
    main()
