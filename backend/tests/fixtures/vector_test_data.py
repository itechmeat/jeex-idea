"""
Test data fixtures for vector database integration testing.

Provides realistic test vectors and structured test data for comprehensive
project and language isolation testing following the EARS requirements.
"""

import random
from uuid import uuid4
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta


class VectorTestDataGenerator:
    """
    Generates realistic test data for vector database integration tests.

    Creates vectors with proper isolation metadata for testing REQ-003
    and REQ-008 security requirements.
    """

    # Predefined test content in different languages
    TEST_CONTENT = {
        "en": {
            "knowledge": [
                "Machine learning algorithms require large datasets for training and validation.",
                "Neural networks can process various types of data including images, text, and audio.",
                "Deep learning models often benefit from transfer learning techniques.",
                "Natural language processing has advanced significantly with transformer models.",
                "Computer vision applications range from object detection to image segmentation.",
            ],
            "memory": [
                "User preferences show pattern recognition capabilities in recommendation systems.",
                "Historical interaction data improves personalization algorithms.",
                "Session continuity requires proper state management in distributed systems.",
                "User behavior analytics can identify emerging trends and patterns.",
                "Adaptive interfaces respond to individual user learning curves.",
            ],
            "agent_context": [
                "Active learning strategies reduce labeling costs in supervised learning.",
                "Reinforcement learning optimizes decision-making through reward mechanisms.",
                "Ensemble methods combine multiple models for improved prediction accuracy.",
                "Feature engineering significantly impacts model performance and interpretability.",
                "Cross-validation techniques prevent overfitting in complex models.",
            ],
        },
        "ru": {
            "knowledge": [
                "Машинное обучение требует больших наборов данных для обучения и проверки.",
                "Нейронные сети могут обрабатывать различные типы данных, включая изображения, текст и аудио.",
                "Глубокое обучение часто использует трансферное обучение для повышения эффективности.",
                "Обработка естественного языка значительно продвинулась с моделями трансформеров.",
                "Приложения компьютерного зрения варьируются от обнаружения объектов до сегментации изображений.",
            ],
            "memory": [
                "Пользовательские предпочтения демонстрируют возможности распознавания образов в системах рекомендаций.",
                "Данные о прошлых взаимодействиях улучшают алгоритмы персонализации.",
                "Непрерывность сеанса требует правильного управления состоянием в распределенных системах.",
                "Аналитика поведения пользователей может выявлять новые тенденции и закономерности.",
                "Адаптивные интерфейсы реагируют на индивидуальные кривые обучения пользователей.",
            ],
            "agent_context": [
                "Стратегии активного обучения снижают затраты на разметку в контролируемом обучении.",
                "Обучение с подкреплением оптимизирует принятие решений через механизмы вознаграждения.",
                "Ансамблевые методы комбинируют несколько моделей для улучшения точности прогнозирования.",
                "Инжиниринг признаков значительно влияет на производительность и интерпретируемость моделей.",
                "Методы перекрестной проверки предотвращают переобучение в сложных моделях.",
            ],
        },
        "es": {
            "knowledge": [
                "Los algoritmos de aprendizaje automático requieren grandes conjuntos de datos para entrenamiento y validación.",
                "Las redes neuronales pueden procesar varios tipos de datos incluyendo imágenes, texto y audio.",
                "El aprendizaje profundo a menudo se beneficia de técnicas de aprendizaje por transferencia.",
                "El procesamiento del lenguaje natural ha avanzado significativamente con los modelos transformer.",
                "Las aplicaciones de visión por computadora van desde la detección de objetos hasta la segmentación de imágenes.",
            ],
            "memory": [
                "Las preferencias de usuario muestran capacidades de reconocimiento de patrones en sistemas de recomendación.",
                "Los datos de interacción histórica mejoran los algoritmos de personalización.",
                "La continuidad de sesión requiere gestión de estado adecuada en sistemas distribuidos.",
                "El análisis del comportamiento del usuario puede identificar tendencias y patrones emergentes.",
                "Las interfaces adaptativas responden a las curvas de aprendizaje individuales del usuario.",
            ],
            "agent_context": [
                "Las estrategias de aprendizaje activo reducen los costos de etiquetado en el aprendizaje supervisado.",
                "El aprendizaje por refuerzo optimiza la toma de decisiones a través de mecanismos de recompensa.",
                "Los métodos de conjunto combinan múltiples modelos para una mayor precisión de predicción.",
                "La ingeniería de características impacta significativamente el rendimiento y la interpretabilidad del modelo.",
                "Las técnicas de validación cruzada previenen el sobreajuste en modelos complejos.",
            ],
        },
    }

    def __init__(self, random_seed: int = 42):
        """
        Initialize test data generator with optional random seed.

        Args:
            random_seed: Seed for reproducible test data generation
        """
        random.seed(random_seed)

    def generate_vector_1536d(self) -> List[float]:
        """
        Generate a normalized 1536-dimensional vector for testing.

        Returns:
            List of 1536 float values normalized between -1 and 1
        """
        # Generate random values between -1 and 1
        vector = [random.uniform(-0.8, 0.8) for _ in range(1536)]

        # Normalize to unit vector (optional for cosine similarity)
        import math

        magnitude = math.sqrt(sum(x * x for x in vector))
        if magnitude > 0:
            vector = [x / magnitude for x in vector]

        return vector

    def generate_test_projects(self, num_projects: int = 3) -> List[Dict[str, Any]]:
        """
        Generate test project data with UUIDs and languages.

        Args:
            num_projects: Number of projects to generate

        Returns:
            List of project dictionaries with id, name, and language
        """
        projects = []
        languages = ["en", "ru", "es"]

        for i in range(num_projects):
            project = {
                "id": str(uuid4()),
                "name": f"Test Project {chr(65 + i)}",  # A, B, C, ...
                "language": languages[i % len(languages)],
            }
            projects.append(project)

        return projects

    def generate_vector_points(
        self, project_id: str, language: str, count_per_type: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Generate vector points for a specific project and language.

        Args:
            project_id: UUID of the project
            language: Language code (en, ru, es)
            count_per_type: Number of vectors to generate per document type

        Returns:
            List of vector point dictionaries ready for upsert
        """
        points = []
        content_pool = self.TEST_CONTENT.get(language, self.TEST_CONTENT["en"])

        for doc_type, content_list in content_pool.items():
            for i in range(count_per_type):
                # Cycle through content if we need more than available
                content = content_list[i % len(content_list)]

                # Add variation to content for uniqueness
                variation = f" (Sample {i + 1})"
                varied_content = content + variation

                point = {
                    "id": str(uuid4()),
                    "vector": self.generate_vector_1536d(),
                    "content": varied_content,
                    "title": f"{doc_type.title()} Document {i + 1}",
                    "type": doc_type,
                    "metadata": {
                        "source": "test_generator",
                        "category": "automated_test",
                        "index": i,
                        "batch": datetime.utcnow().isoformat(),
                    },
                    "importance": round(random.uniform(0.3, 1.0), 2),
                    "project_id": project_id,
                    "language": language,
                }
                points.append(point)

        return points

    def generate_cross_language_dataset(
        self,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Generate comprehensive test dataset for isolation testing.

        Creates:
        - 3 projects (A, B, C) with different languages
        - Mixed language content within projects
        - Total of ~90 vector points for comprehensive testing

        Returns:
            Tuple of (projects_list, all_vectors_list)
        """
        projects = self.generate_test_projects(3)
        all_vectors = []

        # Each project gets vectors in its primary language
        for project in projects:
            vectors = self.generate_vector_points(
                project_id=project["id"],
                language=project["language"],
                count_per_type=10,
            )
            all_vectors.extend(vectors)

        # Add cross-language contamination tests (should be isolated)
        # Project A gets some Russian content (should not appear in English searches)
        if len(projects) >= 1:
            cross_vectors = self.generate_vector_points(
                project_id=projects[0]["id"],
                language="ru",  # Different from project's primary language
                count_per_type=3,
            )
            all_vectors.extend(cross_vectors)

        return projects, all_vectors

    def generate_performance_test_vectors(
        self, project_id: str, language: str, count: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Generate vectors for performance testing.

        Args:
            project_id: UUID of the project
            language: Language code
            count: Number of vectors to generate

        Returns:
            List of vector points for performance testing
        """
        points = []
        content_pool = self.TEST_CONTENT.get(language, self.TEST_CONTENT["en"])
        all_content = []
        for content_list in content_pool.values():
            all_content.extend(content_list)

        for i in range(count):
            content = all_content[i % len(all_content)]

            point = {
                "id": str(uuid4()),
                "vector": self.generate_vector_1536d(),
                "content": f"{content} (Perf Test {i + 1})",
                "title": f"Performance Test Document {i + 1}",
                "type": random.choice(["knowledge", "memory", "agent_context"]),
                "metadata": {"performance_test": True, "batch_size": count, "index": i},
                "importance": round(random.uniform(0.1, 1.0), 2),
                "project_id": project_id,
                "language": language,
            }
            points.append(point)

        return points

    def generate_isolation_test_scenarios(self) -> Dict[str, Any]:
        """
        Generate complete test scenarios for isolation testing.

        Returns:
            Dictionary containing all test data for comprehensive isolation tests
        """
        projects, vectors = self.generate_cross_language_dataset()

        # Group vectors by project and language for easy test access
        grouped_vectors = {}
        for vector in vectors:
            project_id = vector["project_id"]
            language = vector["language"]

            if project_id not in grouped_vectors:
                grouped_vectors[project_id] = {}
            if language not in grouped_vectors[project_id]:
                grouped_vectors[project_id][language] = []

            grouped_vectors[project_id][language].append(vector)

        return {
            "projects": projects,
            "all_vectors": vectors,
            "grouped_vectors": grouped_vectors,
            "scenarios": {
                "project_isolation": {
                    "project_a_id": projects[0]["id"] if len(projects) > 0 else None,
                    "project_b_id": projects[1]["id"] if len(projects) > 1 else None,
                    "project_c_id": projects[2]["id"] if len(projects) > 2 else None,
                },
                "language_isolation": {
                    "en_vectors": [v for v in vectors if v["language"] == "en"],
                    "ru_vectors": [v for v in vectors if v["language"] == "ru"],
                    "es_vectors": [v for v in vectors if v["language"] == "es"],
                },
                "mixed_language_project": {
                    "project_id": projects[0]["id"] if len(projects) > 0 else None,
                    "primary_language": projects[0]["language"]
                    if len(projects) > 0
                    else None,
                    "contains_other_languages": len(
                        [
                            v
                            for v in vectors
                            if v["project_id"] == projects[0]["id"]
                            and v["language"] != projects[0]["language"]
                        ]
                    )
                    > 0
                    if len(projects) > 0
                    else False,
                },
            },
        }


# Test data fixtures for common use cases
def get_isolation_test_fixtures() -> Dict[str, Any]:
    """
    Get pre-configured test fixtures for isolation testing.

    Returns:
        Dictionary with test data ready for pytest fixtures
    """
    generator = VectorTestDataGenerator(random_seed=42)
    return generator.generate_isolation_test_scenarios()


def get_performance_test_fixtures() -> Dict[str, Any]:
    """
    Get performance test fixtures for load testing.

    Returns:
        Dictionary with performance test data
    """
    generator = VectorTestDataGenerator(random_seed=123)

    project_id = str(uuid4())
    language = "en"

    return {
        "project_id": project_id,
        "language": language,
        "vectors_100": generator.generate_performance_test_vectors(
            project_id, language, 100
        ),
        "vectors_1000": generator.generate_performance_test_vectors(
            project_id, language, 1000
        ),
        "query_vectors": [generator.generate_vector_1536d() for _ in range(10)],
    }


def create_test_vector(
    project_id: str,
    language: str,
    content: str = "Test content",
    doc_type: str = "knowledge",
) -> Dict[str, Any]:
    """
    Create a single test vector with given parameters.

    Args:
        project_id: UUID of the project
        language: Language code
        content: Vector content
        doc_type: Document type

    Returns:
        Single vector point dictionary
    """
    generator = VectorTestDataGenerator()

    return {
        "id": str(uuid4()),
        "vector": generator.generate_vector_1536d(),
        "content": content,
        "title": f"Test {doc_type.title()} Document",
        "type": doc_type,
        "metadata": {"test": True},
        "importance": 0.8,
        "project_id": project_id,
        "language": language,
    }
