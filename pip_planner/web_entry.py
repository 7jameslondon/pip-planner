import sys


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "design":
        from pip_planner.cli import main

        raise SystemExit(main(sys.argv[1:]))

    from pip_planner.web import main

    raise SystemExit(main())
