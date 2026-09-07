"""``python -m tron`` — cross the rooftops in a terminal."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="roderick-tron",
        description="Roderick Tron - terminal version.",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="fix the run, for a reproducible one",
    )
    parser.add_argument(
        "--play", action="store_true",
        help="skip the title screen and start on the rooftops",
    )
    args = parser.parse_args()

    # Imported here, not at module scope, so --help works without the engine
    # or its terminal extra installed.
    from tron.app import run

    run(args.seed, args.play)


if __name__ == "__main__":
    main()
