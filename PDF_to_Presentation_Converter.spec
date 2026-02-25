# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('app.py', '.'), ('config.py', '.'), ('pdf_processor.py', '.'), ('llm_agent.py', '.'), ('translation_service.py', '.'), ('presentation_builder.py', '.'), ('main_processor.py', '.'), ('.env', '.'), ('example', 'example')],
    hiddenimports=['streamlit', 'langchain', 'langchain_openai', 'azure.ai.translation.text', 'openai', 'python_pptx', 'PyPDF2', 'fitz', 'PIL', 'dotenv', 'requests', 'beautifulsoup4', 'lxml', 'pandas', 'numpy', 'altair', 'pydeck', 'watchdog', 'gitpython', 'rich', 'click', 'tornado', 'jinja2', 'markupsafe', 'pyyaml', 'sqlalchemy', 'aiohttp', 'dataclasses_json', 'jsonpatch', 'langsmith', 'pydantic', 'tiktoken', 'isodate', 'azure_core', 'xlsxwriter', 'pymupdfb', 'charset_normalizer', 'idna', 'urllib3', 'certifi', 'soupsieve', 'anyio', 'distro', 'httpx', 'jiter', 'sniffio', 'tqdm', 'aiohappyeyeballs', 'aiosignal', 'attrs', 'frozenlist', 'multidict', 'propcache', 'yarl', 'jsonschema', 'narwhals', 'six', 'colorama', 'marshmallow', 'typing_inspect', 'gitdb', 'httpcore', 'h11', 'zipp', 'jsonpointer', 'markdown_it_py', 'pygments', 'greenlet', 'regex', 'smmap', 'jsonschema_specifications', 'referencing', 'rpds_py', 'mdurl', 'mypy_extensions'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PDF_to_Presentation_Converter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
