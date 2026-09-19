import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog-check", help="Scan the catalog and report problems.")

    args = parser.parse_args(argv)

    if args.command == "catalog-check":
        from app.catalog.check import run_catalog_check

        issues = run_catalog_check()
        if not issues:
            print("No problems found.")
            return 0
        for issue in issues:
            print(issue)
        print(f"\n{len(issues)} problem(s) found.")
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
