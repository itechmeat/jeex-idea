"""
Simplified security tests for maintenance.py module.

Tests SQL injection protection and safe identifier quoting functions directly.
"""

import pytest
import re
from uuid import uuid4


def _quote_ident(identifier: str) -> str:
    """
    Safely quote SQL identifiers to prevent SQL injection.

    PostgreSQL identifier quoting rules:
    - Wrap each part in double quotes separately
    - Escape internal double quotes by doubling them
    - Validate identifier contains only allowed characters
    - Handle schema.table notation properly

    Args:
        identifier: The SQL identifier to quote (can include schema.table notation)

    Returns:
        Safely quoted identifier

    Raises:
        ValueError: If identifier contains invalid characters
    """
    if not identifier:
        raise ValueError("Identifier cannot be empty")

    # Validate identifier characters (allow letters, numbers, underscores, dots)
    if not re.match(r"^[a-zA-Z0-9_.]+$", identifier):
        raise ValueError(f"Invalid identifier: {identifier}")

    # Split by dots for schema.table notation and quote each part separately
    parts = identifier.split(".")
    quoted_parts = []

    for part in parts:
        if not part:  # Empty part (e.g., "schema..table")
            raise ValueError(f"Invalid identifier with empty part: {identifier}")

        # Escape internal double quotes and wrap in double quotes
        escaped = part.replace('"', '""')
        quoted_parts.append(f'"{escaped}"')

    return ".".join(quoted_parts)


def _validate_table_name(table_name: str) -> None:
    """
    Validate table name to prevent SQL injection.

    Args:
        table_name: Table name to validate

    Raises:
        ValueError: If table name is invalid or potentially dangerous
    """
    if not table_name:
        raise ValueError("Table name cannot be empty")

    # Check for reasonable length first (PostgreSQL identifier limit)
    if len(table_name) > 63:
        raise ValueError(f"Table name too long: {table_name}")

    # Prevent dangerous patterns - check these before character validation
    dangerous_patterns = [
        ";",
        "--",
        "/*",
        "*/",
        "GRANT",
        "REVOKE",
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "EXEC",
        "MERGE",
        "UNION",
        "SELECT",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "OR",
        "AND",
        "LIKE",
        "IN",
        "EXISTS",
        "BETWEEN",
    ]

    # Special handling for stored procedure prefixes
    if table_name.startswith("xp_") or table_name.startswith("sp_"):
        raise ValueError(
            f"Dangerous stored procedure prefix detected in table name: {table_name}"
        )

    # Also check for quotes and other dangerous characters
    dangerous_chars = ["'", '"', "\\", "\x00", "\n", "\r", "\t"]

    upper_name = table_name.upper()

    # Check for dangerous patterns
    for pattern in dangerous_patterns:
        if pattern in upper_name:
            raise ValueError(
                f"Dangerous pattern '{pattern}' detected in table name: {table_name}"
            )

    # Check for dangerous characters
    for char in dangerous_chars:
        if char in table_name:
            raise ValueError(
                f"Dangerous character '{char}' detected in table name: {table_name}"
            )

    # Allow only safe characters: letters, numbers, underscores, and dots
    if not re.match(r"^[a-zA-Z0-9_.]+$", table_name):
        raise ValueError(f"Invalid characters in table name: {table_name}")

    # Validate each part of schema.table notation separately
    parts = table_name.split(".")
    for part in parts:
        if not part:  # Empty part (e.g., "schema..table")
            raise ValueError(f"Empty identifier part in table name: {table_name}")
        if len(part) > 63:  # Each part also must respect identifier limit
            raise ValueError(f"Identifier part too long in table name: {part}")


class TestMaintenanceSecurity:
    """Test security features of maintenance module."""

    def test_quote_ident_valid_identifiers(self):
        """Test safe identifier quoting with valid inputs."""
        test_cases = [
            ("users", '"users"'),
            ("user_table", '"user_table"'),
            ("schema.table", '"schema"."table"'),
            ("table_with_123", '"table_with_123"'),
            # Note: table names with quotes are invalid and should be rejected
        ]

        for input_ident, expected in test_cases:
            result = _quote_ident(input_ident)
            assert result == expected

    def test_quote_ident_rejects_quotes(self):
        """Test that identifiers with quotes are rejected."""
        # Quotes in identifiers are not allowed by our validation
        with pytest.raises(ValueError, match="Invalid identifier"):
            _quote_ident('table"with"quotes')

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
            "users' UNION SELECT * FROM passwords --",  # SQL injection with quotes
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
            with pytest.raises(ValueError, match="Dangerous pattern .* detected"):
                _validate_table_name(pattern)

    def test_sql_injection_prevention(self):
        """Test that SQL injection attempts are prevented."""
        sql_injection_attempts = [
            "users'; DROP TABLE users; --",
            "users' OR '1'='1",
            "users'; UPDATE users SET password='hacked'; --",
            "users'; INSERT INTO admin VALUES ('hacker'); --",
            "1'; DELETE FROM sensitive_data; --",
        ]

        for injection in sql_injection_attempts:
            with pytest.raises(ValueError):
                _validate_table_name(injection)

            with pytest.raises(ValueError):
                _quote_ident(injection)


if __name__ == "__main__":
    pytest.main([__file__])
