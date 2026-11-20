"""Entry point of the packaged executable (PyInstaller needs a script, not `python -m app`)."""
import multiprocessing

from app.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()   # the worker processes of the field profiles start through here
    main()
