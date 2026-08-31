"""Configuration management module for the enterprise data platform.

This module provides a singleton ConfigManager for loading and managing
platform configuration, along with a frozen PlatformConfig dataclass
for immutable configuration storage.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformConfig:
    """Immutable platform configuration.

    This dataclass holds the platform configuration and is frozen to ensure
    immutability after initialization. Configuration is validated upon creation.

    Attributes:
        app_env (str): Application environment (e.g., "local", "dev", "prod").
            Defaults to "local".
        storage_path (str): Path to data storage directory. Defaults to "./data".

    Raises:
        ValueError: If validation fails during initialization.
    """

    app_env: str = "local"
    storage_path: str = "./data"

    def __post_init__(self) -> None:
        """Validate configuration after initialization.

        This method is called automatically by the dataclass after all fields
        are set. It validates the configuration and raises ValueError if any
        field is invalid.

        Raises:
            ValueError: If any field fails validation.
        """
        self.validate()

    def validate(self) -> None:
        """Validate configuration invariants.

        Checks that all configuration fields contain valid values and raises
        ValueError with descriptive messages if validation fails.

        Raises:
            ValueError: If app_env is empty, storage_path is empty, or if
                app_env contains invalid characters.
        """
        if not self.app_env or not isinstance(self.app_env, str):
            raise ValueError(
                f"app_env must be a non-empty string, got {self.app_env!r}"
            )

        if not self.storage_path or not isinstance(self.storage_path, str):
            raise ValueError(
                f"storage_path must be a non-empty string, "
                f"got {self.storage_path!r}"
            )

        # Validate app_env contains only alphanumeric and underscore
        if not all(c.isalnum() or c == "_" for c in self.app_env):
            raise ValueError(
                f"app_env must contain only alphanumeric characters and "
                f"underscore, got {self.app_env!r}"
            )

        logger.info(
            f"Configuration validated: app_env={self.app_env}, "
            f"storage_path={self.storage_path}"
        )


class ConfigManager:
    """Singleton manager for platform configuration.

    This class implements the singleton pattern to ensure only one instance
    of the configuration manager exists throughout the application lifecycle.
    It provides methods to load configuration from files and environment variables.

    Example:
        >>> config_mgr = ConfigManager()
        >>> config = config_mgr.load("config.yaml")
        >>> print(config.app_env)
        'dev'
    """

    _instance: Optional["ConfigManager"] = None

    def __new__(cls) -> "ConfigManager":
        """Create or return existing singleton instance.

        Ensures that only one ConfigManager instance exists by returning
        the cached instance if it already exists, or creating a new one.

        Returns:
            The singleton ConfigManager instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            logger.info("ConfigManager singleton instance created")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (testing only).

        Clears the cached singleton instance, allowing a new instance to be
        created on the next access. This method is intended for testing purposes
        only and should not be used in production code.

        Example:
            >>> ConfigManager.reset()  # In tests only
        """
        cls._instance = None
        logger.debug("ConfigManager singleton instance reset (testing)")

    def load(self, config_file: Optional[str] = None) -> PlatformConfig:
        """Load configuration from file or environment.

        Loads configuration from the specified file if provided, otherwise
        attempts to load from environment variables. Falls back to defaults
        if neither file nor environment variables are available.

        Args:
            config_file: Path to YAML configuration file. If None, attempts
                to load from environment variables.

        Returns:
            PlatformConfig: Validated and frozen configuration object.

        Raises:
            FileNotFoundError: If config_file is specified but file does not exist.
            ValueError: If configuration is invalid or malformed.

        Example:
            >>> mgr = ConfigManager()
            >>> config = mgr.load("config.yaml")
            >>> config.app_env
            'dev'
        """
        try:
            if config_file:
                logger.info(f"Loading configuration from file: {config_file}")
                return self._load_from_yaml(config_file)

            logger.info("Loading configuration from environment variables")
            app_env = os.getenv("APP_ENV", "local")
            storage_path = os.getenv("STORAGE_PATH", "./data")

            config = PlatformConfig(app_env=app_env, storage_path=storage_path)
            logger.info("Configuration loaded from environment variables")
            return config

        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {config_file}")
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}"
            ) from e
        except ValueError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration: {e}") from e

    def _load_from_yaml(self, path: str) -> PlatformConfig:
        """Load configuration from YAML file.

        Reads a YAML configuration file and returns a PlatformConfig object.
        The file must contain optional keys: app_env and storage_path.

        Args:
            path: Path to YAML configuration file.

        Returns:
            PlatformConfig: Configuration object loaded from YAML.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            ValueError: If the YAML is malformed or configuration is invalid.

        Example:
            >>> mgr = ConfigManager()
            >>> config = mgr._load_from_yaml("config.yaml")
        """
        path_obj = Path(path)

        if not path_obj.exists():
            logger.error(f"Configuration file does not exist: {path}")
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            logger.debug(f"Reading YAML file: {path}")
            with open(path_obj, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            if not isinstance(data, dict):
                raise ValueError(
                    f"Expected YAML to contain a dictionary, "
                    f"got {type(data).__name__}"
                )

            logger.debug(f"Parsed YAML data: {data}")

            app_env = data.get("app_env", "local")
            storage_path = data.get("storage_path", "./data")

            config = PlatformConfig(app_env=app_env, storage_path=storage_path)
            logger.info(f"Configuration loaded from YAML: {path}")
            return config

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {path}: {e}")
            raise ValueError(
                f"Invalid YAML in configuration file {path}: {e}"
            ) from e
        except ValueError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration in {path}: {e}") from e


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    mgr = ConfigManager()

    try:
        config = mgr.load()
        print(f"Default config loaded: {config}")
    except Exception as e:
        print(f"Error loading config: {e}")
