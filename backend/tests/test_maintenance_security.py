"""
Security tests for maintenance.py module.

Tests SQL injection protection, input validation, and safe identifier quoting.
"""

import pytest
from uuid import uuid4
from app.core.maintenance import _quote_ident, _validate_table_name


class TestMaintenanceSecurity:
    """Test security features of maintenance module."""

    def test_quote_ident_valid_identifiers(self):
        """Test safe identifier quoting with valid inputs."""
        test_cases = [
            ("users", '"users"'),
            ("user_table", '"user_table"'),
            ("schema.table", '"schema"."table"'),
            ("table_with_123", '"table_with_123"'),
            ('table"with"quotes', '"table""with""quotes"'),
        ]

        for input_ident, expected in test_cases:
            result = _quote_ident(input_ident)
            assert result == expected

    def test_quote_ident_invalid_identifiers(self):
        """Test that invalid identifiers raise ValueError."""
        invalid_inputs = [
            "",  # Empty string
            "table-with-dashes",  # Dashes not allowed
            "table with spaces",  # Spaces not allowed
            "table; DROP users;",  # SQL injection attempt
            "table' OR '1'='1",  # SQL injection attempt
            "table\x00null",  # Null byte
        ]

        for invalid_input in invalid_inputs:
            with pytest.raises(ValueError):
                _quote_ident(invalid_input)

    def test_validate_table_name_valid_names(self):
        """Test validation of valid table names."""
        valid_names = [
            "users",
            "user_profiles",
            "schema.table_name",
            "table123",
            "app_data.logs",
        ]

        for name in valid_names:
            # Should not raise exception
            _validate_table_name(name)

    def test_validate_table_name_invalid_names(self):
        """Test that invalid table names raise ValueError."""
        invalid_names = [
            "",  # Empty string
            "users; DROP TABLE users; --",  # SQL injection
            "users' UNION SELECT * FROM passwords --",  # SQL injection
            "users/* comment */",  # Comment injection
            "xp_cmdshell",  # Dangerous SQL Server command
            "sp_help",  # Dangerous stored procedure
            "a" * 64,  # Too long (>63 characters)
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ValueError):
                _validate_table_name(invalid_name)

    def test_table_name_length_limit(self):
        """Test table name length validation."""
        # PostgreSQL identifier limit is 63 characters
        valid_long_name = "a" * 63
        invalid_long_name = "a" * 64

        # Should not raise
        _validate_table_name(valid_long_name)

        # Should raise ValueError
        with pytest.raises(ValueError):
            _validate_table_name(invalid_long_name)

    def test_dangerous_patterns_detection(self):
        """Test detection of dangerous SQL patterns."""
        dangerous_patterns = [
            "users DROP TABLE",
            "users;DELETE FROM",
            "users UNION SELECT",
            "users CREATE TABLE",
            "users ALTER TABLE",
            "users EXEC sp_",
            "users -- comment",
            "users /* comment */",
        ]

        for pattern in dangerous_patterns:
            with pytest.raises(ValueError, match="Dangerous pattern detected"):
                _validate_table_name(pattern)


if __name__ == "__main__":
    pytest.main([__file__])
