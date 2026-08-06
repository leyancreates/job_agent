"""Safe errors for resume loading and extraction."""


class ResumeFileError(ValueError):
    """Base error whose message is safe to show in the Streamlit UI."""


class UnsupportedResumeFileError(ResumeFileError):
    pass


class EmptyResumeError(ResumeFileError):
    pass


class CorruptedResumeFileError(ResumeFileError):
    pass
