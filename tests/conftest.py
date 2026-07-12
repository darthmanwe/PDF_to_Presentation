"""Test session setup.

Force LangSmith tracing OFF for the whole test session, regardless of the
developer's .env. Tests must be hermetic: they should not emit traces, depend
on a LangSmith key, or slow down / flake on tracing-endpoint failures. This
runs at conftest import (before any test module imports pdfdeck), so
pdfdeck's load_dotenv (override=False) will not turn it back on.
"""

import os

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"  # legacy var name, belt-and-suspenders
