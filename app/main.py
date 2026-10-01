"""Entry point."""

import multiprocessing

from app.gui import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    run()
