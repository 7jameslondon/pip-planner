import sys


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"design", "genomes"}:
        from pip_planner.cli import main

        raise SystemExit(main(sys.argv[1:]))

    from pip_planner.web import main

    raise SystemExit(main())
