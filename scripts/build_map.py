"""Build the existing GeoJSON layers. Use --check for read-only validation."""
import argparse
import sys
from travel_core import ROOT, TravelError, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        from project_lock import project_lock
        with project_lock(ROOT):
            print(build(check_only=args.check))
        return 0
    except (TravelError, OSError, KeyError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
