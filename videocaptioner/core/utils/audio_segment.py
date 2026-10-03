"""pydub media IO with hidden, credential-scrubbed child processes."""

import subprocess
from typing import Any, cast

from pydub import AudioSegment
from pydub import audio_segment as _audio_segment
from pydub import utils as _utils

from .subprocess_helper import _NO_WINDOW, SECRET_ENV_PREFIXES, child_environment

__all__ = ["AudioSegment"]


def _popen(*args, **kwargs):
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | _NO_WINDOW
    environment = kwargs.get("env")
    kwargs["env"] = child_environment() if environment is None else {
        key: value for key, value in environment.items()
        if not key.upper().startswith(SECRET_ENV_PREFIXES)
    }
    return subprocess.Popen(*args, **kwargs)


class _MediaSubprocess:
    Popen = staticmethod(_popen)

    def __getattr__(self, name):
        return getattr(subprocess, name)


# pydub has no public subprocess-options hook. Replace only its local bindings;
# never replace subprocess.Popen globally or modify the installed dependency.
cast(Any, _audio_segment).subprocess = _MediaSubprocess()
cast(Any, _utils).Popen = _popen
