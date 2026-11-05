"""meeting-crosswalk: reconcile two meeting recorders and the calendars, then plan corrections.

Python 3 standard library only. The planner never writes; apply.py executes a
plan against an adapter and verifies by reading back.
"""
from .apply import ApplyReport, ScopeError, apply_plan
from .config import Config
from .drift import Drift, measure, parity
from .ledger import Ledger
from .match import Match, match_capture, parse_instant
from .model import Capture, Event, Inference, Library, Note, Rulings, load_inferences, load_library, load_rulings
from .plan import Op, Plan, build_plan, make_batches, write_outputs
from .titles import choose_title, is_generic

__version__ = "1.0.0"
