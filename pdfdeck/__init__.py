"""pdfdeck package.

Load .env into the process environment at import so that variables read
directly from os.environ by third-party libs -- notably LangSmith tracing
(LANGSMITH_TRACING / LANGSMITH_API_KEY, read by langchain-core) -- are
picked up. pydantic-settings only maps its own declared fields, so without
this those vars would sit in .env but never reach os.environ.
"""

from dotenv import load_dotenv as _load_dotenv

_load_dotenv()  # no-op if no .env is found; does not override real env vars
