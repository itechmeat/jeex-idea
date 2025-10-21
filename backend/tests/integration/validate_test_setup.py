#!/usr/bin/env python3
"""
Validate Vector Integration Test Setup

Quick validation script to ensure all integration test files are properly
structured and can be imported without errors.
"""

import sys
import importlib.util
from pathlib import Path


def validate_import(module_path, module_name):
    """Validate that a module can be imported without errors."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None:
            return False, f"Could not create spec for {module_name}"

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True, f"✅ {module_name} imported successfully"
    except Exception as e:
        return False, f"❌ {module_name} import failed: {e}"


def main():
    """Validate all integration test modules."""
    print("🔍 Validating Vector Integration Test Setup")
    print("=" * 60)

    test_dir = Path(__file__).parent
    required_files = [
        ("conftest.py", "conftest"),
        ("test_vector_isolation.py", "test_vector_isolation"),
        ("test_vector_security.py", "test_vector_security"),
        ("run_vector_isolation_tests.py", "run_vector_isolation_tests"),
    ]

    required_fixtures = [
        ("../fixtures/vector_test_data.py", "vector_test_data"),
    ]

    all_valid = True

    print("\n📋 Checking integration test files...")
    for file_name, module_name in required_files:
        file_path = test_dir / file_name
        if not file_path.exists():
            print(f"❌ Missing file: {file_name}")
            all_valid = False
            continue

        success, message = validate_import(file_path, module_name)
        print(f"  {message}")
        if not success:
            all_valid = False

    print("\n🔧 Checking test fixtures...")
    for file_name, module_name in required_fixtures:
        file_path = test_dir / file_name
        if not file_path.exists():
            print(f"❌ Missing fixture: {file_name}")
            all_valid = False
            continue

        success, message = validate_import(file_path, module_name)
        print(f"  {message}")
        if not success:
            all_valid = False

    print("\n📝 Checking test class structure...")
    try:
        # Check that test classes exist
        from test_vector_isolation import VectorIsolationTester
        from test_vector_security import VectorSecurityTester

        print("  ✅ VectorIsolationTester class found")
        print("  ✅ VectorSecurityTester class found")
    except Exception as e:
        print(f"  ❌ Test class validation failed: {e}")
        all_valid = False

    print("\n🧮 Checking test fixtures...")
    try:
        import importlib.util
        import sys

        # Load the fixture file dynamically using importlib
        # NOTE: We use dynamic import here to avoid modifying sys.path and to maintain
        # test isolation. This approach allows us to load modules from absolute paths
        # without affecting Python's module search path or creating potential conflicts
        # with other test modules. This is particularly important for CI/CD environments
        # where test isolation is critical.
        spec = importlib.util.spec_from_file_location(
            "vector_test_data",
            "/Users/techmeat/www/projects/jeex-idea/backend/tests/fixtures/vector_test_data.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["vector_test_data"] = module
        spec.loader.exec_module(module)

        VectorTestDataGenerator = module.VectorTestDataGenerator
        generator = VectorTestDataGenerator()
        test_data = generator.generate_isolation_test_scenarios()

        # Validate structure
        assert "projects" in test_data
        assert "all_vectors" in test_data
        assert "scenarios" in test_data
        assert len(test_data["projects"]) >= 3

        print("  ✅ VectorTestDataGenerator works correctly")
        print(f"  ✅ Generated {len(test_data['projects'])} test projects")
        print(f"  ✅ Generated {len(test_data['all_vectors'])} test vectors")
    except Exception as e:
        print(f"  ❌ Test fixture validation failed: {e}")
        all_valid = False

    print("\n🔗 Checking imports...")
    try:
        # Test critical imports that tests depend on
        import httpx
        import pytest
        import structlog
        from uuid import uuid4

        print("  ✅ httpx imported")
        print("  ✅ pytest imported")
        print("  ✅ structlog imported")
        print("  ✅ uuid imported")
    except ImportError as e:
        print(f"  ❌ Import validation failed: {e}")
        all_valid = False

    print("\n" + "=" * 60)
    if all_valid:
        print("🎉 All validations passed! Test setup is ready.")
        print("\nNext steps:")
        print("1. Start the vector service: make dev-up")
        print("2. Run tests: python tests/integration/run_vector_isolation_tests.py")
        return 0
    else:
        print("❌ Some validations failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
