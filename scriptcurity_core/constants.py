import os
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class Constants(BaseModel):
    """
    Configuration constants for the application.
    """

    # Environment settings
    TESTNET: bool = Field(
        default_factory=lambda: os.getenv("TESTNET", "0").strip().lower()
        in ("1", "true", "yes"),
        description="Flag to indicate if running in testnet mode.",
    )

    # Versioning
    VERSION: str = Field(
        default="0.0.1",
        description="Version of the application in 'major.minor.patch' format.",
    )
    SPEC_VERSION: int = Field(
        default=0,
        description="Specification version calculated from the version string.",
    )

    # Challenge settings
    N_CHALLENGES_PER_EPOCH: int = Field(
        default=10, description="Number of challenges per epoch."
    )
    SCORING_HOUR: int = Field(
        default=14, description="Hour of the day when scoring occurs (0-23)."
    )
    POINT_DECAY_RATE: float = Field(
        default=1 / 14, description="Daily point decay rate."
    )

    # Network settings
    CHALLENGE_DOCKER_PORT: int = Field(
        default=10001, description="Port used for challenge Docker containers."
    )
    MINER_DOCKER_PORT: int = Field(
        default=10002, description="Port used for miner Docker containers."
    )

    # Time intervals (in seconds)
    REVEAL_INTERVAL: int = Field(
        default=3600 * 24, description="Time interval for revealing commits."
    )
    EPOCH_LENGTH: int = Field(
        default=3600, description="Length of an epoch in seconds."
    )
    MIN_VALIDATOR_STAKE: int = Field(
        default=1_000_000, description="Minimum validator stake required."
    )

    # Query settings
    QUERY_TIMEOUT: int = Field(default=4, description="Timeout for queries in seconds.")

    class Config:
        validate_assignment = True

    @field_validator("SPEC_VERSION", pre=True, always=True)
    def calculate_spec_version(cls, v, values):
        """
        Calculates the specification version as an integer based on the version string.

        Args:
            v: The current value of spec_version (unused).
            values: Dictionary of field values.

        Returns:
            int: The calculated specification version.
        """
        version_str = values.get("VERSION", "0.0.1")
        try:
            major, minor, patch = (int(part) for part in version_str.split("."))
            return (1000 * major) + (10 * minor) + patch
        except ValueError as e:
            raise ValueError(
                f"Invalid version format '{version_str}'. Expected 'major.minor.patch'."
            ) from e

    @model_validator(pre=True)
    def adjust_for_testnet(cls, values):
        """
        Adjusts certain constants based on whether TESTNET mode is enabled.

        Args:
            values: Dictionary of field values.

        Returns:
            dict: The adjusted values dictionary.
        """
        testnet = values.get("TESTNET", False)
        if testnet:
            values["REVEAL_INTERVAL"] = 30
            values["EPOCH_LENGTH"] = 30
            values["MIN_VALIDATOR_STAKE"] = -1
        return values

    def is_scoring_time(self, current_time: Optional[datetime] = None) -> bool:
        """
        Determines if the current time is the scoring time.

        Args:
            current_time (Optional[datetime]): The current datetime. Uses now() if None.

        Returns:
            bool: True if it's the scoring hour, False otherwise.
        """
        if current_time is None:
            current_time = datetime.now()
        return current_time.hour == self.SCORING_HOUR

    def decay_points(self, point: float, days_passed: int) -> float:
        """
        Applies decay to the given points based on the number of days passed.

        Args:
            point (float): The original point value.
            days_passed (int): The number of days since the point was awarded.

        Returns:
            float: The decayed point value.
        """
        decay_factor = 1 - min(self.POINT_DECAY_RATE * days_passed, 1)
        return point * decay_factor


constants = Constants()
