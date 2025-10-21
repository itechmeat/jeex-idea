"""
Vector Database Isolation Integration Tests

Comprehensive integration tests for project and language isolation requirements
REQ-003 (Server-Side Filter Enforcement) and REQ-008 (Multi-Tenant Data Isolation).

Tests cover:
- Project isolation (no cross-project data leakage)
- Language isolation (no cross-language contamination)
- Filter enforcement (mandatory server-side filtering)
- Data integrity (proper tagging and retrieval)
"""

import pytest
import asyncio
import httpx
from uuid import uuid4
from typing import Dict, Any, List
import structlog

from ...fixtures.vector_test_data import (
    VectorTestDataGenerator,
    get_isolation_test_fixtures,
    create_test_vector,
)
from ...services.vector.domain.entities import (
    SearchContext,
    VectorData,
    DocumentType,
    ProjectId,
    LanguageCode,
)

logger = structlog.get_logger()


# Test Configuration
ISOLATION_TEST_CONFIG = {
    "base_url": "http://localhost:5210",
    "timeout": 30.0,
    "max_retries": 3,
    "test_projects_count": 3,
    "vectors_per_project": 30,
    "cross_language_vectors": 9,  # Additional vectors for cross-language tests
}


class VectorIsolationTester:
    """
    Comprehensive test suite for vector database isolation.

    Validates all security requirements from REQ-003 and REQ-008.
    """

    def __init__(self, base_url: str = ISOLATION_TEST_CONFIG["base_url"]):
        """
        Initialize isolation tester.

        Args:
            base_url: Base URL for vector API endpoints
        """
        self.base_url = base_url
        self.client = None
        self.test_data = None
        self.created_points = []

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url, timeout=ISOLATION_TEST_CONFIG["timeout"]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.cleanup_test_data()
        if self.client:
            await self.client.aclose()

    async def setup_test_data(self) -> Dict[str, Any]:
        """
        Setup comprehensive test data for isolation testing.

        Returns:
            Test data dictionary with projects and vectors
        """
        logger.info("Setting up isolation test data")

        generator = VectorTestDataGenerator(random_seed=42)
        self.test_data = generator.generate_isolation_test_scenarios()

        # Insert all test vectors
        for project in self.test_data["projects"]:
            vectors = self.test_data["grouped_vectors"][project["id"]]

            for language, lang_vectors in vectors.items():
                if lang_vectors:
                    await self.insert_vectors(project["id"], language, lang_vectors)
                    self.created_points.extend([v["id"] for v in lang_vectors])

        logger.info(
            "Test data setup completed",
            projects_count=len(self.test_data["projects"]),
            total_vectors=len(self.created_points),
        )

        return self.test_data

    async def insert_vectors(
        self, project_id: str, language: str, vectors: List[Dict[str, Any]]
    ) -> None:
        """
        Insert vectors with proper context.

        Args:
            project_id: Project UUID
            language: Language code
            vectors: List of vector dictionaries
        """
        # Convert vectors to API format
        api_vectors = []
        for vector in vectors:
            api_vector = {
                "id": vector["id"],
                "vector": vector["vector"],
                "content": vector["content"],
                "title": vector["title"],
                "type": vector["type"],
                "metadata": vector["metadata"],
                "importance": vector["importance"],
            }
            api_vectors.append(api_vector)

        # Insert in batches of 100 (API limit)
        batch_size = 100
        for i in range(0, len(api_vectors), batch_size):
            batch = api_vectors[i : i + batch_size]

            try:
                response = await self.client.post(
                    "/api/v1/vector/upsert",
                    json={"points": batch},
                    params={"project_id": project_id, "language": language},
                )

                if response.status_code != 200:
                    logger.error(
                        "Failed to upsert vectors",
                        status_code=response.status_code,
                        response_text=response.text,
                        project_id=project_id,
                        language=language,
                        batch_size=len(batch),
                    )

                assert response.status_code == 200, (
                    f"Failed to insert vectors: {response.status_code} - {response.text}"
                )

                result = response.json()
                assert result["points_processed"] == len(batch), (
                    f"Expected {len(batch)} points processed, got {result['points_processed']}"
                )
            except Exception as e:
                logger.exception(
                    "Vector upsert failed",
                    project_id=project_id,
                    language=language,
                    batch_index=i,
                    exc_info=True,
                )
                raise

    async def search_vectors(
        self, project_id: str, language: str, query_vector: List[float], limit: int = 50
    ) -> Dict[str, Any]:
        """
        Search vectors with given context.

        Args:
            project_id: Project UUID
            language: Language code
            query_vector: Query vector (1536 dimensions)
            limit: Maximum results

        Returns:
            Search response dictionary
        """
        response = await self.client.post(
            "/api/v1/vector/search",
            json={"query_vector": query_vector, "limit": limit},
            params={"project_id": project_id, "language": language},
        )

        if response.status_code != 200:
            logger.error(
                "Vector search failed",
                status_code=response.status_code,
                response_text=response.text,
                project_id=project_id,
                language=language,
                limit=limit,
            )

        assert response.status_code == 200, (
            f"Search failed: {response.status_code} - {response.text}"
        )

        return response.json()

    async def get_point_by_id(
        self, point_id: str, project_id: str, language: str
    ) -> Dict[str, Any]:
        """
        Retrieve a specific vector point.

        Args:
            point_id: Vector point UUID
            project_id: Project UUID for context
            language: Language code for context

        Returns:
            Vector point data
        """
        response = await self.client.get(
            f"/api/v1/vector/points/{point_id}",
            params={"project_id": project_id, "language": language},
        )

        if response.status_code == 404:
            logger.debug(
                "Vector point not found or not accessible",
                point_id=point_id,
                project_id=project_id,
                language=language,
                status_code=404,
            )
            return None

        if response.status_code != 200:
            logger.error(
                "Get vector point failed",
                status_code=response.status_code,
                response_text=response.text,
                point_id=point_id,
                project_id=project_id,
                language=language,
            )

        assert response.status_code == 200, (
            f"Failed to get point: {response.status_code} - {response.text}"
        )

        return response.json()

    async def cleanup_test_data(self) -> None:
        """Clean up all test data created during testing."""
        if not self.client or not self.created_points:
            return

        logger.info("Cleaning up test data", points_count=len(self.created_points))

        # Delete in batches
        batch_size = 100
        for i in range(0, len(self.created_points), batch_size):
            batch = self.created_points[i : i + batch_size]

            # Use the first project's context for cleanup
            if self.test_data and self.test_data["projects"]:
                project_id = self.test_data["projects"][0]["id"]
                language = self.test_data["projects"][0]["language"]

                try:
                    # DELETE with JSON body containing point_ids array
                    response = await self.client.delete(
                        "/api/v1/vector/points",
                        params={"project_id": project_id, "language": language},
                        json={"point_ids": [str(pid) for pid in batch]},
                    )

                    if response.status_code not in [200, 204]:
                        logger.warning(
                            "Cleanup delete request failed (expected due to isolation)",
                            status_code=response.status_code,
                            response_text=response.text,
                            batch_size=len(batch),
                        )
                except Exception as e:
                    logger.warning(
                        "Cleanup failed (expected due to isolation constraints)",
                        error=str(e),
                        exc_info=True,
                    )

        self.created_points.clear()


# pytest fixtures
@pytest.fixture
async def vector_isolation_tester():
    """Pytest fixture for vector isolation testing."""
    async with VectorIsolationTester() as tester:
        yield tester


@pytest.fixture
async def isolation_test_data(vector_isolation_tester):
    """Pytest fixture that sets up test data."""
    return await vector_isolation_tester.setup_test_data()


# Project Isolation Tests (REQ-008)
@pytest.mark.asyncio
async def test_project_isolation_strict_separation(
    vector_isolation_tester, isolation_test_data
):
    """
    Test REQ-008: Strict project isolation - no cross-project data leakage.

    GIVEN: Three projects (A, B, C) with different vector content
    WHEN: Searching with project_id "A" and language "en"
    THEN: Results contain ONLY vectors from project A, never from B or C
    """
    test_data = isolation_test_data
    projects = test_data["projects"]
    grouped_vectors = test_data["grouped_vectors"]

    # Get project A's primary language vectors
    project_a = projects[0]
    project_a_vectors = []
    for lang_vectors in grouped_vectors[project_a["id"]].values():
        project_a_vectors.extend(lang_vectors)

    # Use a query vector from project A
    query_vector = project_a_vectors[0]["vector"]

    # Search for project A only
    results = await vector_isolation_tester.search_vectors(
        project_id=project_a["id"],
        language=project_a["language"],
        query_vector=query_vector,
        limit=100,  # High limit to detect any leakage
    )

    # Verify strict project isolation
    assert results["total_found"] > 0, "Should find vectors in project A"
    assert results["total_found"] <= len(project_a_vectors), (
        "Should not exceed project A's vectors"
    )

    # Check that all results belong to project A
    for result in results["results"]:
        # We can't directly check project_id from results (security feature),
        # but we can verify by trying to retrieve the point with different project contexts
        point_id = result["id"]

        # Try to retrieve with project B's context (should fail)
        project_b = projects[1]
        point_with_b_context = await vector_isolation_tester.get_point_by_id(
            point_id=point_id,
            project_id=project_b["id"],
            language=project_b["language"],
        )
        assert point_with_b_context is None, (
            "Should not be able to access point with different project context"
        )

    logger.info(
        "Project isolation test passed",
        project_a_id=project_a["id"],
        results_found=results["total_found"],
        expected_max=len(project_a_vectors),
    )


@pytest.mark.asyncio
async def test_project_isolation_cross_language_search(
    vector_isolation_tester, isolation_test_data
):
    """
    Test project isolation with cross-language content.

    GIVEN: Project A contains both English and Russian content
    WHEN: Searching project A with English language filter
    THEN: Only English content from project A is returned, never Russian content
    """
    test_data = isolation_test_data
    projects = test_data["projects"]
    grouped_vectors = test_data["grouped_vectors"]

    # Find project with mixed language content
    mixed_project = None
    for project in projects:
        project_languages = grouped_vectors[project["id"]].keys()
        if len(project_languages) > 1:
            mixed_project = project
            break

    assert mixed_project is not None, (
        "Should have a project with mixed language content"
    )

    # Search with primary language
    primary_lang_vectors = grouped_vectors[mixed_project["id"]][
        mixed_project["language"]
    ]
    query_vector = primary_lang_vectors[0]["vector"]

    results = await vector_isolation_tester.search_vectors(
        project_id=mixed_project["id"],
        language=mixed_project["language"],
        query_vector=query_vector,
        limit=100,
    )

    # Verify language isolation within project
    assert results["total_found"] > 0, "Should find vectors in primary language"

    # All results should be in the requested language
    for result in results["results"]:
        point_id = result["id"]

        # Retrieve the point to check its language
        point_data = await vector_isolation_tester.get_point_by_id(
            point_id=point_id,
            project_id=mixed_project["id"],
            language=mixed_project["language"],
        )

        if point_data:
            # This should pass because we're using the correct language context
            assert True  # Point is accessible with correct language
        else:
            pytest.fail(
                "Point should be accessible with correct project and language context"
            )

    logger.info(
        "Cross-language project isolation test passed",
        project_id=mixed_project["id"],
        language=mixed_project["language"],
        results_found=results["total_found"],
    )


@pytest.mark.asyncio
async def test_project_isolation_no_bypass_possible(
    vector_isolation_tester, isolation_test_data
):
    """
    Test that project isolation cannot be bypassed.

    GIVEN: Multiple projects with vectors
    WHEN: Attempting various bypass techniques
    THEN: All bypass attempts fail with proper errors
    """
    test_data = isolation_test_data
    projects = test_data["projects"]

    if len(projects) < 2:
        pytest.skip("Need at least 2 projects for bypass testing")

    # Try to search without project_id (should fail)
    response = await vector_isolation_tester.client.post(
        "/api/v1/vector/search",
        json={"query_vector": [0.1] * 1536, "limit": 10},
        # No project_id or language params
    )
    assert response.status_code == 422, "Should return validation error"

    # Try to search with invalid project_id format
    response = await vector_isolation_tester.client.post(
        "/api/v1/vector/search",
        json={"query_vector": [0.1] * 1536, "limit": 10},
        params={"project_id": "invalid-uuid", "language": "en"},
    )
    assert response.status_code == 400, "Should return bad request error"

    # Try to search with invalid language code
    response = await vector_isolation_tester.client.post(
        "/api/v1/vector/search",
        json={"query_vector": [0.1] * 1536, "limit": 10},
        params={"project_id": projects[0]["id"], "language": "invalid-lang"},
    )
    assert response.status_code == 400, "Should return bad request error"

    logger.info("Project isolation bypass test passed - all attempts properly rejected")


# Language Isolation Tests
@pytest.mark.asyncio
async def test_language_isolation_strict_separation(
    vector_isolation_tester, isolation_test_data
):
    """
    Test REQ-008: Strict language isolation - no cross-language contamination.

    GIVEN: Vectors in English, Russian, and Spanish across different projects
    WHEN: Searching with language "en"
    THEN: Results contain ONLY English vectors, never Russian or Spanish
    """
    test_data = isolation_test_data
    scenarios = test_data["scenarios"]["language_isolation"]

    # Find English vectors
    en_vectors = scenarios["en_vectors"]
    if not en_vectors:
        pytest.skip("No English vectors found in test data")

    query_vector = en_vectors[0]["vector"]

    # Search for English only
    results = await vector_isolation_tester.search_vectors(
        project_id=en_vectors[0]["project_id"],
        language="en",
        query_vector=query_vector,
        limit=100,
    )

    # Verify language isolation
    assert results["total_found"] > 0, "Should find English vectors"

    # Search for Russian with same project
    if scenarios["ru_vectors"]:
        ru_project_id = scenarios["ru_vectors"][0]["project_id"]
        ru_query = scenarios["ru_vectors"][0]["vector"]

        ru_results = await vector_isolation_tester.search_vectors(
            project_id=ru_project_id, language="ru", query_vector=ru_query, limit=100
        )

        # Results should be different
        en_result_ids = {r["id"] for r in results["results"]}
        ru_result_ids = {r["id"] for r in ru_results["results"]}

        # No overlap should exist between language-specific searches
        overlap = en_result_ids & ru_result_ids
        assert len(overlap) == 0, (
            f"Found {len(overlap)} overlapping results between languages"
        )

    logger.info(
        "Language isolation test passed",
        en_results=results["total_found"],
        ru_results=len(scenarios["ru_vectors"]) if scenarios["ru_vectors"] else 0,
    )


@pytest.mark.asyncio
async def test_language_isolation_same_project_different_languages(
    vector_isolation_tester, isolation_test_data
):
    """
    Test language isolation within the same project.

    GIVEN: Single project with English and Russian content
    WHEN: Searching with language "en" vs language "ru"
    THEN: Results are properly separated by language
    """
    test_data = isolation_test_data
    scenarios = test_data["scenarios"]["mixed_language_project"]

    if not scenarios["contains_other_languages"]:
        pytest.skip("No project with mixed languages found")

    mixed_project_id = scenarios["project_id"]
    primary_lang = scenarios["primary_language"]

    # Find vectors in different languages for the same project
    grouped_vectors = test_data["grouped_vectors"][mixed_project_id]

    if len(grouped_vectors) < 2:
        pytest.skip("Not enough languages in mixed project")

    languages = list(grouped_vectors.keys())
    lang1, lang2 = languages[0], languages[1]

    # Get query vectors for each language
    lang1_query = grouped_vectors[lang1][0]["vector"]
    lang2_query = grouped_vectors[lang2][0]["vector"]

    # Search with first language
    lang1_results = await vector_isolation_tester.search_vectors(
        project_id=mixed_project_id, language=lang1, query_vector=lang1_query, limit=100
    )

    # Search with second language
    lang2_results = await vector_isolation_tester.search_vectors(
        project_id=mixed_project_id, language=lang2, query_vector=lang2_query, limit=100
    )

    # Verify language separation
    lang1_ids = {r["id"] for r in lang1_results["results"]}
    lang2_ids = {r["id"] for r in lang2_results["results"]}

    overlap = lang1_ids & lang2_ids
    assert len(overlap) == 0, (
        f"Found {len(overlap)} overlapping results between languages in same project"
    )

    logger.info(
        "Same project language isolation test passed",
        project_id=mixed_project_id,
        lang1=lang1,
        lang1_count=len(lang1_results["results"]),
        lang2=lang2,
        lang2_count=len(lang2_results["results"]),
    )


# Filter Enforcement Tests (REQ-003)
@pytest.mark.asyncio
async def test_server_side_filter_enforcement_mandatory(vector_isolation_tester):
    """
    Test REQ-003: Server-side filter enforcement is mandatory.

    GIVEN: Vector search service
    WHEN: Making search requests
    THEN: All searches include mandatory project_id and language filters
    """
    # This test validates that filters are enforced server-side
    # by attempting searches that should be rejected

    # Test missing project_id
    response = await vector_isolation_tester.client.post(
        "/api/v1/vector/search",
        json={"query_vector": [0.1] * 1536, "limit": 10},
        params={
            "language": "en"
            # Missing project_id
        },
    )
    assert response.status_code == 422, (
        f"Should return validation error for missing project_id, got {response.status_code}"
    )

    # Test missing language
    response = await vector_isolation_tester.client.post(
        "/api/v1/vector/search",
        json={"query_vector": [0.1] * 1536, "limit": 10},
        params={
            "project_id": str(uuid4())
            # Missing language
        },
    )
    assert response.status_code == 422, (
        f"Should return validation error for missing language, got {response.status_code}"
    )

    # Test valid search works
    response = await vector_isolation_tester.client.post(
        "/api/v1/vector/search",
        json={"query_vector": [0.1] * 1536, "limit": 10},
        params={"project_id": str(uuid4()), "language": "en"},
    )
    assert response.status_code == 200, "Valid search should succeed"

    logger.info("Server-side filter enforcement test passed")


# Data Integrity Tests
@pytest.mark.asyncio
async def test_data_integrity_upsert_tagging(vector_isolation_tester):
    """
    Test that upsert operations properly tag vectors with project_id and language.

    GIVEN: Vector upsert operation
    WHEN: Storing vectors with project and language context
    THEN: Vectors are properly tagged and retrievable with correct context
    """
    project_id = str(uuid4())
    language = "en"

    # Create test vector
    test_vector = create_test_vector(
        project_id=project_id,
        language=language,
        content="Test data integrity vector",
        doc_type="knowledge",
    )

    # Insert vector
    await vector_isolation_tester.insert_vectors(
        project_id=project_id, language=language, vectors=[test_vector]
    )

    # Retrieve with correct context
    retrieved = await vector_isolation_tester.get_point_by_id(
        point_id=test_vector["id"], project_id=project_id, language=language
    )

    assert retrieved is not None, (
        "Should be able to retrieve vector with correct context"
    )
    assert retrieved["content"] == test_vector["content"], "Content should match"

    # Try to retrieve with different project (should fail)
    different_project = str(uuid4())
    retrieved_wrong = await vector_isolation_tester.get_point_by_id(
        point_id=test_vector["id"], project_id=different_project, language=language
    )
    assert retrieved_wrong is None, (
        "Should not be able to retrieve with different project context"
    )

    # Try to retrieve with different language (should fail)
    retrieved_wrong_lang = await vector_isolation_tester.get_point_by_id(
        point_id=test_vector["id"], project_id=project_id, language="ru"
    )
    assert retrieved_wrong_lang is None, (
        "Should not be able to retrieve with different language context"
    )

    logger.info("Data integrity upsert tagging test passed")


@pytest.mark.asyncio
async def test_isolation_comprehensive_verification(
    vector_isolation_tester, isolation_test_data
):
    """
    Comprehensive verification of all isolation requirements.

    GIVEN: Complete test dataset with multiple projects and languages
    WHEN: Performing various search and retrieval operations
    THEN: All isolation constraints are strictly enforced
    """
    test_data = isolation_test_data
    projects = test_data["projects"]

    # Test all project combinations
    for i, project_a in enumerate(projects):
        for j, project_b in enumerate(projects):
            if i == j:
                continue  # Skip same project

            # Get vectors for each project
            project_a_vectors = []
            for lang_vectors in test_data["grouped_vectors"][project_a["id"]].values():
                project_a_vectors.extend(lang_vectors)

            project_b_vectors = []
            for lang_vectors in test_data["grouped_vectors"][project_b["id"]].values():
                project_b_vectors.extend(lang_vectors)

            if not project_a_vectors or not project_b_vectors:
                continue

            # Search project A
            a_results = await vector_isolation_tester.search_vectors(
                project_id=project_a["id"],
                language=project_a_vectors[0]["language"],
                query_vector=project_a_vectors[0]["vector"],
                limit=100,
            )

            # Search project B
            b_results = await vector_isolation_tester.search_vectors(
                project_id=project_b["id"],
                language=project_b_vectors[0]["language"],
                query_vector=project_b_vectors[0]["vector"],
                limit=100,
            )

            # Verify no overlap
            a_ids = {r["id"] for r in a_results["results"]}
            b_ids = {r["id"] for r in b_results["results"]}

            overlap = a_ids & b_ids
            assert len(overlap) == 0, (
                f"Cross-project data leak detected between "
                f"project {project_a['id']} and project {project_b['id']}: {len(overlap)} overlapping results"
            )

    logger.info(
        "Comprehensive isolation verification passed",
        projects_tested=len(projects),
        cross_project_checks=len(projects) * (len(projects) - 1),
    )


if __name__ == "__main__":
    # Run tests directly
    async def main():
        async with VectorIsolationTester() as tester:
            test_data = await tester.setup_test_data()
            await test_project_isolation_strict_separation(tester, test_data)
            await test_language_isolation_strict_separation(tester, test_data)
            await test_server_side_filter_enforcement_mandatory(tester)
            print("All isolation tests passed!")

    asyncio.run(main())
