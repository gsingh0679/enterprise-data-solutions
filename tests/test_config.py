"""Unit tests for the configuration management module.

Tests cover ConfigManager singleton functionality, configuration loading
from YAML files and environment variables, and PlatformConfig immutability
and validation.
"""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.config import ConfigManager, PlatformConfig, VaultConfig


class TestPlatformConfig:
    """Test suite for PlatformConfig dataclass."""

    def test_init_with_defaults(self):
        """Test PlatformConfig initialization with default values."""
        config = PlatformConfig()
        assert config.app_env == "local"
        assert config.storage_path == "./data"
        assert isinstance(config.vault_config, VaultConfig)
        assert config.vault_config.provider == "mock"
        assert config.vault_config.ttl_seconds is None

    def test_init_with_custom_values(self):
        """Test PlatformConfig initialization with custom values."""
        config = PlatformConfig(app_env="dev", storage_path="/var/data")
        assert config.app_env == "dev"
        assert config.storage_path == "/var/data"
        assert isinstance(config.vault_config, VaultConfig)

    def test_immutability(self):
        """Test that frozen PlatformConfig cannot be modified."""
        config = PlatformConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.app_env = "prod"

    def test_immutability_storage_path(self):
        """Test that frozen PlatformConfig storage_path cannot be modified."""
        config = PlatformConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.storage_path = "/new/path"

    def test_immutability_vault_config(self):
        """Test that frozen PlatformConfig vault_config cannot be modified."""
        config = PlatformConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.vault_config = VaultConfig(provider="aws_secrets")

    def test_validate_empty_app_env(self):
        """Test validation fails with empty app_env."""
        with pytest.raises(ValueError, match="app_env must be a non-empty string"):
            PlatformConfig(app_env="")

    def test_validate_empty_storage_path(self):
        """Test validation fails with empty storage_path."""
        with pytest.raises(
            ValueError, match="storage_path must be a non-empty string"
        ):
            PlatformConfig(storage_path="")

    def test_validate_invalid_app_env_characters(self):
        """Test validation fails with invalid characters in app_env."""
        with pytest.raises(
            ValueError, match="app_env must contain only alphanumeric"
        ):
            PlatformConfig(app_env="dev-prod")

    def test_validate_app_env_with_underscore(self):
        """Test that app_env with underscore is valid."""
        config = PlatformConfig(app_env="dev_prod")
        assert config.app_env == "dev_prod"

    def test_validate_non_string_app_env(self):
        """Test validation fails when app_env is not a string."""
        with pytest.raises(ValueError, match="app_env must be a non-empty string"):
            PlatformConfig(app_env=123)  # type: ignore

    def test_validate_non_string_storage_path(self):
        """Test validation fails when storage_path is not a string."""
        with pytest.raises(ValueError, match="storage_path must be a non-empty string"):
            PlatformConfig(storage_path=456)  # type: ignore


class TestConfigManager:
    """Test suite for ConfigManager singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        ConfigManager.reset()

    def teardown_method(self):
        """Reset singleton after each test."""
        ConfigManager.reset()

    def test_singleton_instance(self):
        """Test that ConfigManager returns same instance."""
        mgr1 = ConfigManager()
        mgr2 = ConfigManager()
        assert mgr1 is mgr2

    def test_load_with_defaults(self):
        """Test loading configuration with default values."""
        mgr = ConfigManager()
        with mock.patch.dict(os.environ, {}, clear=True):
            config = mgr.load()
        assert config.app_env == "local"
        assert config.storage_path == "./data"

    def test_load_from_environment_variables(self):
        """Test loading configuration from environment variables."""
        mgr = ConfigManager()
        with mock.patch.dict(
            os.environ,
            {"APP_ENV": "prod", "STORAGE_PATH": "/data/prod"},
            clear=True,
        ):
            config = mgr.load()
        assert config.app_env == "prod"
        assert config.storage_path == "/data/prod"

    def test_load_from_yaml_file(self):
        """Test loading configuration from YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("app_env: dev\nstorage_path: /var/data\n")

            mgr = ConfigManager()
            config = mgr.load(str(config_file))

            assert config.app_env == "dev"
            assert config.storage_path == "/var/data"

    def test_load_from_yaml_with_partial_fields(self):
        """Test loading YAML with missing fields uses defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("app_env: staging\n")

            mgr = ConfigManager()
            config = mgr.load(str(config_file))

            assert config.app_env == "staging"
            assert config.storage_path == "./data"

    def test_load_from_empty_yaml_file(self):
        """Test loading from empty YAML file uses defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("")

            mgr = ConfigManager()
            config = mgr.load(str(config_file))

            assert config.app_env == "local"
            assert config.storage_path == "./data"

    def test_load_file_not_found(self):
        """Test loading from non-existent file raises FileNotFoundError."""
        mgr = ConfigManager()
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            mgr.load("/nonexistent/config.yaml")

    def test_load_invalid_yaml_syntax(self):
        """Test loading invalid YAML raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("invalid: yaml: content: [")

            mgr = ConfigManager()
            with pytest.raises(ValueError, match="Invalid YAML"):
                mgr.load(str(config_file))

    def test_load_yaml_with_invalid_app_env(self):
        """Test loading YAML with invalid app_env raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("app_env: prod-env\n")

            mgr = ConfigManager()
            with pytest.raises(ValueError, match="Invalid configuration"):
                mgr.load(str(config_file))

    def test_load_yaml_with_non_dict_content(self):
        """Test loading YAML with non-dict content raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("- item1\n- item2\n")

            mgr = ConfigManager()
            with pytest.raises(ValueError, match="Expected YAML to contain a dictionary"):
                mgr.load(str(config_file))

    def test_reset_singleton(self):
        """Test that reset() clears singleton instance."""
        mgr1 = ConfigManager()
        ConfigManager.reset()
        mgr2 = ConfigManager()
        assert mgr1 is not mgr2

    def test_load_from_yaml_private_method(self):
        """Test _load_from_yaml method directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("app_env: test\nstorage_path: /tmp/test\n")

            mgr = ConfigManager()
            config = mgr._load_from_yaml(str(config_file))

            assert config.app_env == "test"
            assert config.storage_path == "/tmp/test"

    def test_load_from_yaml_file_not_found_direct(self):
        """Test _load_from_yaml raises FileNotFoundError for missing file."""
        mgr = ConfigManager()
        with pytest.raises(FileNotFoundError):
            mgr._load_from_yaml("/nonexistent/file.yaml")

    def test_integration_singleton_with_yaml_load(self):
        """Test singleton behavior across multiple load operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("app_env: integration_test\n")

            mgr1 = ConfigManager()
            config1 = mgr1.load(str(config_file))

            mgr2 = ConfigManager()
            assert mgr1 is mgr2

            config2 = mgr2.load(str(config_file))
            assert config1.app_env == config2.app_env

    def test_configuration_immutability_after_load(self):
        """Test that loaded configuration is immutable."""
        mgr = ConfigManager()
        with mock.patch.dict(os.environ, {}, clear=True):
            config = mgr.load()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.app_env = "modified"


class TestVaultConfig:
    """Test suite for VaultConfig dataclass."""

    def test_vault_config_defaults(self):
        """Test VaultConfig initialization with default values."""
        vault_config = VaultConfig()
        assert vault_config.provider == "mock"
        assert vault_config.ttl_seconds is None

    def test_vault_config_with_ttl(self):
        """Test VaultConfig initialization with TTL."""
        vault_config = VaultConfig(provider="mock", ttl_seconds=3600)
        assert vault_config.provider == "mock"
        assert vault_config.ttl_seconds == 3600

    def test_vault_config_aws_provider(self):
        """Test VaultConfig with AWS provider."""
        vault_config = VaultConfig(provider="aws_secrets")
        assert vault_config.provider == "aws_secrets"

    def test_vault_config_hashicorp_provider(self):
        """Test VaultConfig with HashiCorp provider."""
        vault_config = VaultConfig(provider="hashicorp")
        assert vault_config.provider == "hashicorp"

    def test_vault_config_invalid_provider(self):
        """Test VaultConfig validation fails with invalid provider."""
        with pytest.raises(ValueError, match="provider must be one of"):
            VaultConfig(provider="invalid_provider")

    def test_vault_config_negative_ttl(self):
        """Test VaultConfig validation fails with negative TTL."""
        with pytest.raises(ValueError, match="ttl_seconds must be non-negative"):
            VaultConfig(provider="mock", ttl_seconds=-1)

    def test_vault_config_non_int_ttl(self):
        """Test VaultConfig validation fails with non-integer TTL."""
        with pytest.raises(ValueError, match="ttl_seconds must be int or None"):
            VaultConfig(provider="mock", ttl_seconds="3600")  # type: ignore

    def test_vault_config_zero_ttl(self):
        """Test VaultConfig accepts zero TTL."""
        vault_config = VaultConfig(provider="mock", ttl_seconds=0)
        assert vault_config.ttl_seconds == 0

    def test_vault_config_immutability(self):
        """Test that frozen VaultConfig cannot be modified."""
        vault_config = VaultConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            vault_config.provider = "aws_secrets"

    def test_platform_config_with_custom_vault_config(self):
        """Test PlatformConfig with custom VaultConfig."""
        vault_config = VaultConfig(provider="aws_secrets", ttl_seconds=7200)
        config = PlatformConfig(
            app_env="prod", storage_path="/data", vault_config=vault_config
        )
        assert config.vault_config.provider == "aws_secrets"
        assert config.vault_config.ttl_seconds == 7200
