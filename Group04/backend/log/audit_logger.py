from enum import StrEnum, auto

from accounts.models import AuditLog

class LogType(StrEnum):
    '''
    Enum for different types of log entries.
    '''

    LOGIN = auto()
    LOGOUT = auto()
    PASSWORD_CHANGE = auto()
    PASSWORD_RESET = auto()
    EMAIL_CHANGE = auto()
    ROLE_CHANGE = auto()
    APPLICATION_DECISION = auto()
    ACCOUNT_STATE = auto()

class LogResult(StrEnum):
    '''
    Enum for the result of a logged action.
    '''

    SUCCESS = auto()
    FAILED = auto()

class Logger:
    '''
    A logger for auditing user activities. Entries are stored in the AuditLog table, which only allows new records to be added.
    '''

    def log(self, data: dict) -> None:
        '''
        Store a log entry created by create_log_entry in the audit log. The database sets the timestamp, in UTC.
        '''

        AuditLog.objects.create(
            actor=data.get("actor"),
            target=data.get("target"),
            action=data["action"],
            result=data["result"],
            reason=data.get("reason", "")
        )

    def read_log_day(self, day: str) -> list:
        '''
        Read the audit logs for a specific day (UTC), from newest to oldest.
        '''

        return self.read_log_range(day, day)

    def read_log_range(self, start_day: str, end_day: str) -> list:
        '''
        Read the audit logs for a range of days, specified by start_day and end_day in ISO format (YYYY-MM-DD), from newest to oldest.
        '''

        logs = AuditLog.objects.filter(timestamp__date__range=(start_day, end_day))

        return list(logs.values("timestamp", "actor", "target", "action", "result", "reason"))

    def create_log_entry(self, type: LogType, data: dict) -> dict:
        '''
        Create a log entry with the specified type and details.

        data format:
        {
            "actor": user_id, or None when unknown,
            "target": target_id, or None when unknown,
            "result": LogResult (required),
            "reason": "reason for the action"
        }
        '''

        actor = data.get("actor", None)
        target = data.get("target", None)
        action = LogType(type).value
        result = LogResult(data["result"]).value
        reason = data.get("reason", "")

        return {
            "actor": actor,
            "target": target,
            "action": action,
            "result": result,
            "reason": reason
        }

# How to create a log entry:

# This creates the log entry dictionary, but does not store it in the database yet.
# The structure is as follows:
#     "actor": user_id,  # The ID of the user performing the action,
#     "target": target_id,  # The ID of the target user or object,
#     "action": LogType.value,  # The type of action being logged,
#     "result": LogResult.SUCCESS.value,  # The result of the action (success or failure),
#     "reason": "User logged in successfully."  # Optional reason for the action

# audit_logger.create_log_entry( a value for LogType, {
#     "actor": user.pk or None when unknown,
#     "target": user.pk or None when unknown,
#     "result": LogResult.SUCCESS or LogResult.FAILED,
#     "reason": "Description of the action or reason for failure."
# })

# Example usage:
# log_entry = audit_logger.create_log_entry(LogType.LOGIN, {
#     "actor": user.pk,
#     "target": user.pk,
#     "result": LogResult.SUCCESS,
#     "reason": "User logged in successfully."
# })

# This stores the log entry in the database:
# audit_logger.log(log_entry)

# A complete example of logging a successful login action:
# log_entry = audit_logger.create_log_entry(LogType.LOGIN, {
#     "actor": user.pk,
#     "target": user.pk,
#     "result": LogResult.SUCCESS,
#     "reason": "User logged in successfully."
# })
# audit_logger.log(log_entry)