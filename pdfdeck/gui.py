"""Tkinter desktop front-end for pdfdeck -- the no-install app for a
non-technical user (a pathology instructor).

Design constraints that shape this module:

* **Import order is load-bearing.** `pdfdeck.config.settings` is a module-level
  pydantic-settings singleton built at import time; it reads credentials from
  the process environment. So this module keeps its top-level imports to the
  stdlib only, and does NOT import `pdfdeck.pipeline` until `main()` has loaded
  the keys into `os.environ` (frozen build) and attached the log handler. All
  `pdfdeck.*` imports are deferred inside functions.
* **Windowed build has no console.** Under PyInstaller `--windowed`,
  `sys.stderr`/`sys.stdout` are `None`. We attach a rotating file handler to the
  "pdfdeck" logger *before* importing the pipeline; this both gives us a log to
  debug remotely and suppresses `telemetry.get_logger`'s StreamHandler (its
  guard skips when the logger already has a handler), which would otherwise try
  to write to a `None` stream.
* **The pipeline blocks on the network.** `iter_convert` is driven on a daemon
  worker thread; events cross back to the Tk main thread through a
  `queue.Queue` polled by `root.after`.

Run unfrozen for development: ``python -m pdfdeck.gui`` (uses the repo `.env`).
Run the offline packaging self-test: ``python -m pdfdeck.gui --selftest``.
"""

from __future__ import annotations

import logging
import logging.handlers
import multiprocessing
import os
import queue
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

APP_TITLE = "PDF → Sunum (pdfdeck 2.0)"
CONFIG_FILENAME = "pdfdeck.config.txt"
LOG_FILENAME = "pdfdeck.log"

# All user-facing text in one place. Bilingual: Turkish first, English in
# parentheses. Flip to Turkish-only later by dropping the parenthetical.
STRINGS = {
    "choose_pdf": "PDF dosyası (PDF file):",
    "browse": "Gözat… (Browse…)",
    "language": "Dil (Language):",
    "lang_en": "İngilizce (English)",
    "lang_tr": "Türkçe (Turkish)",
    "lang_both": "İngilizce + Türkçe (Both)",
    "convert": "Dönüŝtür (Convert)",
    "open_deck": "Sunumu Aç (Open deck)",
    "open_tr_deck": "Türkçe sunumu aç (Open Turkish deck)",
    "open_folder": "Klasörü Aç (Open folder)",
    "ready": "Hazır. Bir PDF seçin. (Ready. Choose a PDF.)",
    "pick_pdf_first": "Önce bir PDF dosyası seçin.\n(Please choose a PDF file first.)",
    "save_title": "Sunumu kaydet (Save presentation as)",
    "working": "Çalıŝıyor… (Working…)",
    "verifying_fig": "Şekil {n} doğrulanıyor… (Verifying figure {n}…)",
    "both_sibling_note": "Not: Türkçe sunum aynı klasöre \"{name}\" olarak kaydedilecek.\n"
                          "(A Turkish deck will be saved next to it as \"{name}\".)",
    "done": "Bitti! (Done!)",
    "summary": "{slides} slayt, {figures} şekil · tahmini maliyet ${cost:.2f}"
               "  ({slides} slides, {figures} figures · est. ${cost:.2f})",
    "summary_besteffort": "  · {n} şekil sınırlı doğrulandı (best-effort)",
    "error_title": "Bir hata oluŝtu (An error occurred)",
    "error_body": "Dönüŝüm başarısız oldu.\n(The conversion failed.)\n\n"
                  "Lütfen şu günlük dosyasını Kutlu'ya gönderin:\n"
                  "(Please send this log file to Kutlu:)\n{log}",
    "no_azure_title": "Çeviri ayarlanmamıŝ (Translation not configured)",
    "no_azure_body": "Türkçe çeviri için gerekli ayar bulunamadı; sunum İngilizce "
                     "oluŝturulacak.\n(Turkish translation is not configured; the deck "
                     "will be produced in English.)\n\nDevam edilsin mi? (Continue?)",
    "missing_config_title": "Ayar dosyası eksik (Settings missing)",
    "missing_config_body": "Gerekli ayar dosyası (" + CONFIG_FILENAME + ") bulunamadı "
                           "veya API anahtarı boŝ.\n(The required settings file is missing "
                           "or the API key is empty.)\n\nProgram çalıŝamıyor — "
                           "lütfen Kutlu'yu arayın.\n(The program cannot run — please "
                           "call Kutlu.)",
    "close_while_running": "Dönüŝüm sürüyor. Yine de kapatılsın mı?\n"
                           "(A conversion is running. Close anyway?)",
}


# --------------------------------------------------------------------------
# Paths, config, logging  (all stdlib -- safe to run before importing pdfdeck)
# --------------------------------------------------------------------------

def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_dir() -> Path:
    """Directory the app runs from: next to the .exe when frozen, else the
    repo root (this file is pdfdeck/gui.py -> parents[1] is the repo root)."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    """Per-user writable area for run artifacts and logs (never cwd-relative)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "pdfdeck"


def _log_path() -> Path:
    return _data_dir() / "logs" / LOG_FILENAME


def _load_keys_or_die() -> None:
    """Frozen build only: load credentials from the config file next to the
    exe into os.environ, before pdfdeck.config's Settings singleton is built.
    In dev (unfrozen) we rely on the repo .env exactly as the CLI does."""
    if not _is_frozen():
        return

    from dotenv import load_dotenv  # bundled dependency

    cfg = _app_dir() / CONFIG_FILENAME
    if cfg.exists():
        load_dotenv(cfg, override=True)

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        # No usable key: show a dead-end dialog and exit. Nothing else can work.
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(STRINGS["missing_config_title"], STRINGS["missing_config_body"])
        root.destroy()
        sys.exit(2)


def _setup_logging() -> logging.Logger:
    """Attach a rotating file handler to the 'pdfdeck' logger. Must run before
    importing pdfdeck.pipeline so telemetry.get_logger sees a handler already
    present and does not add its own (stderr-bound) StreamHandler."""
    logs = _data_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (_data_dir() / "runs").mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("pdfdeck")
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        handler = logging.handlers.RotatingFileHandler(
            _log_path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    return logging.getLogger("pdfdeck.gui")


# --------------------------------------------------------------------------
# Offline self-test  (exercises every PyInstaller collection hazard)
# --------------------------------------------------------------------------

def run_selftest() -> int:
    """Import everything the frozen app needs and touch the one piece of
    package data (python-pptx's default template) -- no network, no API key.
    Returns a process exit code."""
    log = logging.getLogger("pdfdeck.gui")
    try:
        import pdfdeck.pipeline  # noqa: F401  (drags in config, graph, models)
        import pdfdeck.agents.llm  # noqa: F401
        import pdfdeck.agents.vision_verifier  # noqa: F401
        import pdfdeck.agents.content_agent  # noqa: F401
        import pdfdeck.translation.service  # noqa: F401
        import fitz  # noqa: F401  (PyMuPDF native libs)
        import pymupdf4llm  # noqa: F401
        from scipy import ndimage  # noqa: F401  (native extension)
        from PIL import Image, ImageDraw  # noqa: F401
        import langchain_anthropic  # noqa: F401
        import anthropic  # noqa: F401
        import langgraph  # noqa: F401
        from langchain_core.callbacks import get_usage_metadata_callback  # noqa: F401
        from pptx import Presentation
        Presentation()  # hazard #1: needs pptx's bundled default template data

        # hazard #4: pymupdf4llm activates pymupdf.layout at import, which loads
        # ONNX models from package data and may spawn a multiprocessing Pool.
        # Exercise the real to_markdown path on a throwaway PDF so a missing
        # model file or a broken frozen-multiprocessing setup fails HERE, at
        # build time, not on the user's machine.
        tmp = os.path.join(tempfile.gettempdir(), "pdfdeck_selftest.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "pdfdeck self-test. Tissue repair overview.")
        doc.save(tmp)
        doc.close()
        md = pymupdf4llm.to_markdown(tmp, page_chunks=True)
        assert md, "to_markdown returned nothing"
        try:
            os.remove(tmp)
        except OSError:
            pass

        log.info("SELFTEST OK")
        return 0
    except Exception:  # noqa: BLE001 -- report any collection gap
        log.error("SELFTEST FAILED\n%s", traceback.format_exc())
        return 1


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

class PdfDeckApp:
    def __init__(self, root, iter_convert, node_labels):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = root
        self._iter_convert = iter_convert
        self._node_labels = node_labels
        self.log = logging.getLogger("pdfdeck.gui")

        self._pdf_path = tk.StringVar()
        self._lang = tk.StringVar(value="en")
        self._status = tk.StringVar(value=STRINGS["ready"])
        self._summary = tk.StringVar(value="")
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._running = False
        self._fig_count = 0
        self._result = None
        self._save_path = None

        root.title(APP_TITLE)
        root.minsize(560, 300)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        frm = ttk.Frame(root, padding=16)
        frm.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        # Row 0: PDF picker
        ttk.Label(frm, text=STRINGS["choose_pdf"]).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._pdf_entry = ttk.Entry(frm, textvariable=self._pdf_path, state="readonly")
        self._pdf_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=(0, 8))
        self._browse_btn = ttk.Button(frm, text=STRINGS["browse"], command=self._browse)
        self._browse_btn.grid(row=0, column=2, sticky="e", pady=(0, 8))

        # Row 1: language radios
        ttk.Label(frm, text=STRINGS["language"]).grid(row=1, column=0, sticky="w", pady=(0, 8))
        langbox = ttk.Frame(frm)
        langbox.grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 8))
        self._radios = []
        for i, (val, key) in enumerate((("en", "lang_en"), ("tr", "lang_tr"), ("en+tr", "lang_both"))):
            rb = ttk.Radiobutton(langbox, text=STRINGS[key], value=val, variable=self._lang)
            rb.grid(row=0, column=i, sticky="w", padx=(0, 14))
            self._radios.append(rb)

        # Row 2: convert
        self._convert_btn = ttk.Button(frm, text=STRINGS["convert"], command=self._start)
        self._convert_btn.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 10))

        # Row 3: progress + status
        self._progress = ttk.Progressbar(frm, mode="indeterminate")
        self._progress.grid(row=3, column=0, columnspan=3, sticky="ew")
        ttk.Label(frm, textvariable=self._status).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(frm, textvariable=self._summary, foreground="#2a7").grid(
            row=5, column=0, columnspan=3, sticky="w")

        # Row 6: post-completion open buttons (hidden until done)
        self._open_box = ttk.Frame(frm)
        self._open_box.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self._open_deck_btn = ttk.Button(self._open_box, text=STRINGS["open_deck"],
                                         command=self._open_deck)
        self._open_tr_btn = ttk.Button(self._open_box, text=STRINGS["open_tr_deck"],
                                       command=self._open_tr_deck)
        self._open_folder_btn = ttk.Button(self._open_box, text=STRINGS["open_folder"],
                                           command=self._open_folder)

    # -- actions ----------------------------------------------------------

    def _browse(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title=STRINGS["choose_pdf"],
            filetypes=[("PDF", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._pdf_path.set(path)
            self._summary.set("")
            self._status.set(STRINGS["ready"])
            for b in (self._open_deck_btn, self._open_tr_btn, self._open_folder_btn):
                b.grid_forget()

    def _start(self):
        from tkinter import filedialog, messagebox

        pdf = self._pdf_path.get().strip()
        if not pdf:
            messagebox.showinfo(APP_TITLE, STRINGS["pick_pdf_first"])
            return

        lang = self._lang.get()
        wants_tr = lang in ("tr", "en+tr")
        if wants_tr and not os.environ.get("AZURE_TRANSLATOR_KEY", "").strip():
            if not messagebox.askokcancel(STRINGS["no_azure_title"], STRINGS["no_azure_body"]):
                return

        stem = Path(pdf).stem
        save_path = filedialog.asksaveasfilename(
            title=STRINGS["save_title"],
            defaultextension=".pptx",
            initialfile=f"{stem}.pptx",
            filetypes=[("PowerPoint", "*.pptx")],
        )
        if not save_path:
            return
        self._save_path = save_path

        if lang == "en+tr":
            base, ext = os.path.splitext(save_path)
            self._status.set(STRINGS["both_sibling_note"].format(
                name=os.path.basename(f"{base}_tr{ext}")))
        else:
            self._status.set(STRINGS["working"])

        # target_language / extra_languages per the language choice.
        target_language, extra = {
            "en": (None, None),
            "tr": ("tr", None),
            "en+tr": (None, ["tr"]),
        }[lang]

        run_dir = str(_data_dir() / "runs" / datetime.now().strftime("%Y%m%d_%H%M%S"))

        self._set_running(True)
        self._fig_count = 0
        self._summary.set("")
        self._result = None
        for b in (self._open_deck_btn, self._open_tr_btn, self._open_folder_btn):
            b.grid_forget()

        t = threading.Thread(
            target=self._worker,
            args=(pdf, target_language, extra, save_path, run_dir),
            daemon=True,
        )
        t.start()
        self.root.after(100, self._poll)

    def _worker(self, pdf, target_language, extra, save_path, run_dir):
        try:
            for event in self._iter_convert(
                pdf,
                target_language=target_language,
                vision_enabled=True,
                output_path=save_path,
                run_dir=run_dir,
                extra_languages=extra,
            ):
                self._queue.put(event)
        except Exception:  # noqa: BLE001 -- surface as a friendly dialog
            self.log.error("conversion failed\n%s", traceback.format_exc())
            self._queue.put(("error", None))

    def _poll(self):
        from tkinter import messagebox
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "node":
                    if payload == "process_region":
                        self._fig_count += 1
                        self._status.set(STRINGS["verifying_fig"].format(n=self._fig_count))
                    else:
                        self._status.set(self._node_labels.get(payload, payload))
                elif kind == "done":
                    self._result = payload
                    self._finish_ok()
                    return
                elif kind == "error":
                    self._set_running(False)
                    self._status.set(STRINGS["error_title"])
                    messagebox.showerror(
                        STRINGS["error_title"],
                        STRINGS["error_body"].format(log=str(_log_path())),
                    )
                    return
        except queue.Empty:
            pass
        if self._running:
            self.root.after(100, self._poll)

    def _finish_ok(self):
        self._set_running(False)
        self._status.set(STRINGS["done"])
        r = self._result
        report = getattr(r, "report", None)
        cost = getattr(report, "cost_estimate_usd", 0.0) if report else 0.0
        besteffort = len(getattr(report, "best_effort_figures", []) or []) if report else 0
        text = STRINGS["summary"].format(
            slides=len(getattr(r, "slides", []) or []),
            figures=len(getattr(r, "figures", []) or []),
            cost=cost,
        )
        if besteffort:
            text += STRINGS["summary_besteffort"].format(n=besteffort)
        self._summary.set(text)

        self._open_deck_btn.grid(row=0, column=0, padx=(0, 8))
        col = 1
        if r is not None and getattr(r, "extra_outputs", None) and r.extra_outputs.get("tr"):
            self._open_tr_btn.grid(row=0, column=col, padx=(0, 8))
            col += 1
        self._open_folder_btn.grid(row=0, column=col)

    def _open_deck(self):
        self._startfile(self._save_path)

    def _open_tr_deck(self):
        r = self._result
        if r is not None and r.extra_outputs.get("tr"):
            self._startfile(r.extra_outputs["tr"])

    def _open_folder(self):
        if self._save_path:
            self._startfile(os.path.dirname(os.path.abspath(self._save_path)))

    def _startfile(self, path):
        try:
            os.startfile(path)  # Windows-only; the app targets Windows
        except OSError:
            self.log.error("could not open %s\n%s", path, traceback.format_exc())

    # -- helpers ----------------------------------------------------------

    def _set_running(self, running: bool):
        self._running = running
        state = "disabled" if running else "normal"
        self._convert_btn.configure(state=state)
        self._browse_btn.configure(state=state)
        for rb in self._radios:
            rb.configure(state=state)
        if running:
            self._progress.start(12)
        else:
            self._progress.stop()

    def _on_close(self):
        from tkinter import messagebox
        if self._running:
            if not messagebox.askokcancel(APP_TITLE, STRINGS["close_while_running"]):
                return
        self.root.destroy()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    # 0) frozen multiprocessing safety (no-op unless this is a spawned child).
    #    pymupdf's layout analyzer may use a Pool; on Windows/frozen that
    #    re-executes this program, so guard before anything else runs.
    multiprocessing.freeze_support()

    # 1) logging handler on the 'pdfdeck' logger BEFORE importing the pipeline
    #    (so telemetry.get_logger does not add a stderr StreamHandler, which is
    #    None in a windowed build).
    log = _setup_logging()
    sys.excepthook = lambda et, ev, tb: log.error(
        "uncaught exception\n%s", "".join(traceback.format_exception(et, ev, tb))
    )

    # 2) --selftest is a key-independent packaging check: it must run even when
    #    the config file is missing (that is exactly when you reach for it).
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())

    # 3) credentials into os.environ (frozen) BEFORE the pipeline import builds
    #    the pydantic-settings singleton.
    _load_keys_or_die()

    # 4) now it is safe to import the pipeline (builds the Settings singleton)
    from pdfdeck.pipeline import NODE_LABELS, iter_convert

    import tkinter as tk

    root = tk.Tk()
    PdfDeckApp(root, iter_convert, NODE_LABELS)
    log.info("GUI started (frozen=%s)", _is_frozen())
    root.mainloop()


if __name__ == "__main__":
    main()
