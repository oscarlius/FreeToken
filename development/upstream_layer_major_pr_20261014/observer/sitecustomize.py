"""Opt-in instrumentation for a measurement service; never part of the PR."""
import os

if os.environ.get("FT_UPSTREAM_NATIVE_IDS"):
    from freetoken.message import DetokenizeMsg, PromptAdmittedMsg
    from freetoken.scheduler.io import SchedulerIOMixin
    from native_observer import install

    install(SchedulerIOMixin, DetokenizeMsg, os.environ["FT_UPSTREAM_NATIVE_IDS"], PromptAdmittedMsg)
