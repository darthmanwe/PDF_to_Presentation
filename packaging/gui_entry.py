"""PyInstaller entry point. Kept trivial so the frozen app's startup logic
lives in the package (pdfdeck.gui.main), where it is also testable unfrozen.

multiprocessing.freeze_support() MUST be the very first thing that runs:
pymupdf's layout analyzer (activated by pymupdf4llm at import) can spawn a
multiprocessing Pool, and on Windows frozen apps use the 'spawn' start method,
which re-executes this exe for each worker. Without freeze_support() those
workers would re-enter main() and open extra GUI windows / fork-bomb."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from pdfdeck.gui import main
    main()
