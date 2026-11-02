import enum


class WorkerStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ShiftStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class CameraSource(str, enum.Enum):
    POV = "POV"
    WALL_CAM = "WALL_CAM"


class EventCategory(str, enum.Enum):
    VIOLATION = "VIOLATION"
    COMPLIANT = "COMPLIANT"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
