"""Makes `from harness import ...` work from any test folder, and puts the
shared fixtures where pytest looks for them."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from harness import venue  # noqa: F401,E402  — a fixture, used by name
