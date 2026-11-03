"""
Download Anything (DA) Exception Hierarchy
"""

class DAError(Exception):
    """Base exception for all Download Anything errors."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class UrlNotSupportedError(DAError):
    """Raised when no driver can handle the provided URL/input."""
    pass

class ExtractionError(DAError):
    """Raised when a driver fails to extract asset metadata or download links."""
    pass

class AuthenticationRequiredError(DAError):
    """Raised when operation requires authentication credentials (cookie/token) that are missing."""
    pass

class FileTooLargeError(DAError):
    """Raised when an asset exceeds the maximum allowed size limit (e.g. >500MB)."""
    pass

class DownloadError(DAError):
    """Raised when downloading file chunks fails or connection breaks unexpectedly."""
    pass

class VerificationError(DAError):
    """Raised when downloaded file fails integrity or magic bytes verification."""
    pass

class CloudDriveError(DAError):
    """Raised when cloud drive operations (save, share query, clean up) encounter errors."""
    pass
