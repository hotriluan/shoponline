"""Robot errors. The worker maps each one to a job status."""


class RobotError(Exception):
    """Base class; the job ends FAILED (read) or UNKNOWN (write) unless handled more precisely."""


class WrongSystem(RobotError):
    """The open SAP session is not the system, client or user the job targets."""


class SessionUnavailable(RobotError):
    """No usable SAP session and logging in again did not give one."""


class SapMessageError(RobotError):
    """SAP showed an error or abort message in the status bar."""


class NoReportData(RobotError):
    """The report ran but SAP found nothing for the filters ("No data to display")."""


class UnknownPopup(RobotError):
    """A dialog not listed in config/sap_popups.yaml; the robot presses nothing."""


class ScreenConfigMissing(RobotError):
    """An element name is missing from config/sap_screens.yaml."""


class GuardViolation(RobotError):
    """The T-code guard stopped the robot: a T-code, key or call outside the allowed lists.

    The job ends FAILED and the robot pauses until an admin resumes it. `session` is the guarded
    session that tripped, kept so the worker can take a screenshot.
    """

    def __init__(self, message: str, session=None):
        super().__init__(message)
        self.session = session
