"""
Комплексные тесты для проверки исправлений на основе ревью.

Проверяет все исправления:
1. memory_percentage исправления в performance_monitor.py
2. метрики памяти в redis_metrics.py
3. репозитории в cache_manager.py
4. project_id в cache_manager.py
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timedelta

from app.monitoring.performance_monitor import (
    RedisPerformanceMonitor,
    MemoryPerformanceStats,
    PerformanceLevel,
)
from app.monitoring.redis_metrics import (
    RedisMetricsCollector,
    RedisMemoryMetrics,
    RedisCommandType,
)
from app.services.cache.cache_manager import CacheManager
from app.domain.cache.entities import ProjectCache
from app.domain.cache.value_objects import TTL


class TestPerformanceMonitorMemoryPercentageFixes:
    """Тесты исправлений memory_percentage в performance_monitor.py"""

    @pytest.fixture
    def monitor(self):
        """Создать экземпляр монитора производительности."""
        return RedisPerformanceMonitor()

    @pytest.mark.asyncio
    async def test_memory_percentage_calculated_as_fraction(self, monitor):
        """Проверить что memory_percentage вычисляется как дробь 0..1."""
        # Мокаем Redis INFO ответ
        mock_memory_info = {
            "used_memory": 512 * 1024 * 1024,  # 512MB
            "maxmemory": 1024 * 1024 * 1024,  # 1GB
        }
        mock_stats_info = {
            "keyspace_hits": 80,
            "keyspace_misses": 20,
            "evicted_keys": 5,
            "expired_keys": 3,
        }
        mock_keyspace_info = {"db0": {"keys": 100}}

        mock_redis = AsyncMock()
        mock_redis.info.side_effect = [
            mock_memory_info,
            mock_stats_info,
            mock_keyspace_info,
        ]

        with patch(
            "app.monitoring.performance_monitor.redis_connection_factory.get_admin_connection"
        ) as mock_get_connection:
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await monitor._analyze_memory_performance()

            # Проверяем что в истории есть запись о памяти
            assert len(monitor._memory_history) > 0
            memory_stats = monitor._memory_history[-1]

            # Проверяем что memory_percentage является дробью 0..1
            expected_percentage = 0.5  # 512MB / 1GB = 0.5
            assert memory_stats.memory_percentage == expected_percentage
            assert 0 <= memory_stats.memory_percentage <= 1

    @pytest.mark.asyncio
    async def test_memory_percentage_thresholds_work_with_fractions(self, monitor):
        """Проверить что пороги работают с дробями."""
        # Тест пороговых значений
        test_cases = [
            (0.3, PerformanceLevel.EXCELLENT),  # 30% < 50% excellent
            (0.6, PerformanceLevel.GOOD),  # 60% < 70% good
            (0.75, PerformanceLevel.FAIR),  # 75% < 80% fair
            (0.85, PerformanceLevel.POOR),  # 85% < 90% poor
            (0.95, PerformanceLevel.CRITICAL),  # 95% > 90% critical
        ]

        for memory_percentage, expected_level in test_cases:
            level = monitor._get_performance_level(
                memory_percentage,
                [
                    monitor.excellent_memory_usage,
                    monitor.good_memory_usage,
                    monitor.fair_memory_usage,
                    monitor.poor_memory_usage,
                ],
            )
            assert level == expected_level

    @pytest.mark.asyncio
    async def test_memory_percentage_human_readable_messages_multiply_by_100(
        self, monitor
    ):
        """Проверить что human-readable сообщения умножают на 100."""
        # Создаем тестовые данные
        memory_stats = MemoryPerformanceStats(
            used_memory_mb=512,
            max_memory_mb=1024,
            memory_percentage=0.75,  # 75% как дробь
            fragmentation_ratio=1.2,
            hit_rate=0.85,
            eviction_rate=0.1,
            key_count=100,
            expire_count=5,
        )

        # Добавляем в историю монитора
        monitor._memory_history.append(memory_stats)

        # Генерируем insights
        await monitor._generate_performance_insights()

        # Проверяем что в сообщениях используется процентный формат (умноженный на 100)
        insights = monitor._insights
        assert len(insights) > 0

        # Находим insight о памяти
        memory_insight = None
        for insight in insights:
            if "memory_usage_percentage" in insight.metric_name:
                memory_insight = insight
                break

        assert memory_insight is not None
        # В сообщении должно быть "75.0%" (0.75 * 100)
        assert "75.0%" in memory_insight.message
        assert memory_insight.current_value == 0.75  # Значение остается дробью

    @pytest.mark.asyncio
    async def test_memory_percentage_alert_threshold_uses_fraction(self, monitor):
        """Проверить что алерты используют дробные значения."""
        mock_memory_info = {
            "used_memory": 900 * 1024 * 1024,  # 900MB
            "maxmemory": 1024 * 1024 * 1024,  # 1GB = 88%
        }
        mock_stats_info = {"keyspace_hits": 80, "keyspace_misses": 20}
        mock_keyspace_info = {"db0": {"keys": 100}}

        mock_redis = AsyncMock()
        mock_redis.info.side_effect = [
            mock_memory_info,
            mock_stats_info,
            mock_keyspace_info,
        ]

        with patch(
            "app.monitoring.performance_monitor.redis_connection_factory.get_admin_connection"
        ) as mock_get_connection:
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            with patch("app.monitoring.performance_monitor.logger") as mock_logger:
                await monitor._analyze_memory_performance()

                # Проверяем что алерт срабатывает при > 0.9 (90%)
                memory_stats = monitor._memory_history[-1]
                assert memory_stats.memory_percentage > 0.9

                # Проверяем что логгер вызывался с правильным значением
                assert mock_logger.warning.called
                warning_call = mock_logger.warning.call_args
                assert warning_call[1]["memory_percentage"] > 0.9


class TestRedisMetricsMemoryPercentageFixes:
    """Тесты исправлений метрик памяти в redis_metrics.py"""

    @pytest.fixture
    def metrics_collector(self):
        """Создать экземпляр коллектора метрик."""
        return RedisMetricsCollector()

    @pytest.mark.asyncio
    async def test_latest_memory_percentage_stores_percentage_value(
        self, metrics_collector
    ):
        """Проверить что _latest_memory_percentage хранит проценты."""
        # Мокаем Redis INFO ответ
        mock_memory_info = {
            "used_memory": 768 * 1024 * 1024,  # 768MB
            "maxmemory": 1024 * 1024 * 1024,  # 1GB = 75%
        }
        mock_stats_info = {
            "keyspace_hits": 160,
            "keyspace_misses": 40,
        }

        mock_redis = AsyncMock()
        mock_redis.info.side_effect = [mock_memory_info, mock_stats_info]

        with patch(
            "app.monitoring.redis_metrics.redis_connection_factory.get_admin_connection"
        ) as mock_get_connection:
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await metrics_collector._collect_memory_metrics()

            # Проверяем что _latest_memory_percentage хранит значение в процентах (0-100)
            assert metrics_collector._latest_memory_percentage == 75.0

    @pytest.mark.asyncio
    async def test_opentelemetry_callback_returns_correct_percentage(
        self, metrics_collector
    ):
        """Проверить что OpenTelemetry callback возвращает корректные значения."""
        # Устанавливаем тестовое значение
        metrics_collector._latest_memory_percentage = 85.5

        # Вызываем callback
        observations = metrics_collector._observe_memory_percentage(None)

        # Проверяем что callback возвращает значение в процентах (0-100)
        assert len(observations) == 1
        assert observations[0].value == 85.5

    @pytest.mark.asyncio
    async def test_memory_metrics_consistency(self, metrics_collector):
        """Проверить консистентность метрик памяти."""
        # Мокаем Redis INFO ответ
        mock_memory_info = {
            "used_memory": 512 * 1024 * 1024,  # 512MB
            "maxmemory": 1024 * 1024 * 1024,  # 1GB
            "used_memory_rss": 600 * 1024 * 1024,  # 600MB
            "used_memory_peak": 550 * 1024 * 1024,
        }
        mock_stats_info = {
            "keyspace_hits": 80,
            "keyspace_misses": 20,
        }

        mock_redis = AsyncMock()
        mock_redis.info.side_effect = [mock_memory_info, mock_stats_info]

        with patch(
            "app.monitoring.redis_metrics.redis_connection_factory.get_admin_connection"
        ) as mock_get_connection:
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await metrics_collector._collect_memory_metrics()

            # Проверяем консистентность метрик
            assert len(metrics_collector._memory_metrics) > 0
            memory_metrics = metrics_collector._memory_metrics[-1]

            # Проверяем корректность расчета процентов
            expected_percentage = 50.0  # 512MB / 1GB * 100
            assert memory_metrics.used_memory_percentage == expected_percentage

            # Проверяем что _latest_memory_percentage обновлен
            assert metrics_collector._latest_memory_percentage == expected_percentage

            # Проверяем что Prometheus метрики обновлены корректно
            assert (
                metrics_collector.prom_redis_memory_percentage._value.get()
                == expected_percentage
            )

    @pytest.mark.asyncio
    async def test_memory_alert_threshold_uses_percentage(self, metrics_collector):
        """Проверить что порог алерта использует проценты."""
        # Устанавливаем высокий процент памяти (> 80%)
        mock_memory_info = {
            "used_memory": 850 * 1024 * 1024,  # 850MB = 83%
            "maxmemory": 1024 * 1024 * 1024,  # 1GB
        }
        mock_stats_info = {"keyspace_hits": 80, "keyspace_misses": 20}

        mock_redis = AsyncMock()
        mock_redis.info.side_effect = [mock_memory_info, mock_stats_info]

        with patch(
            "app.monitoring.redis_metrics.redis_connection_factory.get_admin_connection"
        ) as mock_get_connection:
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            with patch.object(metrics_collector, "_trigger_memory_alert") as mock_alert:
                await metrics_collector._collect_memory_metrics()

                # Проверяем что алерт срабатывает
                memory_metrics = metrics_collector._memory_metrics[-1]
                assert memory_metrics.used_memory_percentage > 80.0

                # Проверяем что алерт был вызван
                mock_alert.assert_called_once()
                alert_call = mock_alert.call_args[0]
                assert alert_call[0] > 80.0  # memory_percentage


class TestCacheManagerRepositoryFixes:
    """Тесты исправлений репозиториев в cache_manager.py"""

    @pytest.fixture
    def cache_manager(self):
        """Создать экземпляр CacheManager с моками."""
        manager = CacheManager()
        # Мокаем все репозитории
        manager.repository.project_cache = AsyncMock()
        manager.repository.user_session = AsyncMock()
        manager.repository.progress = AsyncMock()
        manager.repository.rate_limit = AsyncMock()
        manager.repository.health = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_services_receive_real_repository_instances(self, cache_manager):
        """Проверить что сервисы получают реальные экземпляры репозиториев."""
        # Проверяем что сервисы используют реальные репозитории из cache_manager.repository
        assert (
            cache_manager.invalidation_service.project_cache_repo
            == cache_manager.repository.project_cache
        )
        assert (
            cache_manager.invalidation_service.user_session_repo
            == cache_manager.repository.user_session
        )
        assert (
            cache_manager.invalidation_service.progress_repo
            == cache_manager.repository.progress
        )

        assert (
            cache_manager.session_service.user_session_repo
            == cache_manager.repository.user_session
        )
        assert (
            cache_manager.session_service.project_cache_repo
            == cache_manager.repository.project_cache
        )

        assert (
            cache_manager.rate_limit_service.rate_limit_repo
            == cache_manager.repository.rate_limit
        )

        assert (
            cache_manager.health_service.health_repo == cache_manager.repository.health
        )

    @pytest.mark.asyncio
    async def test_repository_methods_called_correctly(self, cache_manager):
        """Проверить что методы репозиториев вызываются корректно."""
        project_id = uuid4()
        sample_data = {"test": "data"}

        # Тест project cache
        await cache_manager.cache_project_data(project_id, sample_data)
        cache_manager.repository.project_cache.save.assert_called_once()
        saved_cache = cache_manager.repository.project_cache.save.call_args[0][0]
        assert isinstance(saved_cache, ProjectCache)
        assert saved_cache.project_id == project_id
        assert saved_cache.data == sample_data

        # Тест получения project data
        mock_cache = MagicMock()
        mock_cache.data = sample_data
        mock_cache.version.value = 1
        cache_manager.repository.project_cache.find_by_project_id.return_value = (
            mock_cache
        )

        result = await cache_manager.get_project_data(project_id)
        cache_manager.repository.project_cache.find_by_project_id.assert_called_once_with(
            project_id
        )
        assert result == sample_data

        # Тест progress tracking
        correlation_id = uuid4()
        await cache_manager.start_progress_tracking(correlation_id, 5)
        cache_manager.repository.progress.save.assert_called_once()

        # Тест invalidation
        cache_manager.invalidation_service.invalidate_project_caches.return_value = 3
        count = await cache_manager.invalidate_project_cache(project_id, "test")
        cache_manager.invalidation_service.invalidate_project_caches.assert_called_once_with(
            project_id, "test"
        )
        assert count == 3

    @pytest.mark.asyncio
    async def test_domain_services_initialized_with_correct_repositories(
        self, cache_manager
    ):
        """Проверить что domain сервисы инициализированы с правильными репозиториями."""
        # Проверяем типы сервисов
        from app.domain.cache.domain_services import (
            CacheInvalidationService,
            SessionManagementService,
            RateLimitingService,
            CacheHealthService,
        )

        assert isinstance(cache_manager.invalidation_service, CacheInvalidationService)
        assert isinstance(cache_manager.session_service, SessionManagementService)
        assert isinstance(cache_manager.rate_limit_service, RateLimitingService)
        assert isinstance(cache_manager.health_service, CacheHealthService)

        # Проверяем что у сервисов есть доступ к репозиториям
        assert hasattr(cache_manager.invalidation_service, "project_cache_repo")
        assert hasattr(cache_manager.invalidation_service, "user_session_repo")
        assert hasattr(cache_manager.invalidation_service, "progress_repo")

        assert hasattr(cache_manager.session_service, "user_session_repo")
        assert hasattr(cache_manager.session_service, "project_cache_repo")

        assert hasattr(cache_manager.rate_limit_service, "rate_limit_repo")
        assert hasattr(cache_manager.health_service, "health_repo")


class TestCacheManagerProjectIdFixes:
    """Тесты исправлений project_id в cache_manager.py"""

    @pytest.fixture
    def cache_manager(self):
        """Создать экземпляр CacheManager."""
        return CacheManager()

    @pytest.mark.asyncio
    async def test_all_get_connection_calls_have_project_id(self, cache_manager):
        """Проверить что все вызовы get_connection() имеют project_id."""
        project_id = uuid4()

        # Тест cache_project_context
        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection"
        ) as mock_get_connection:
            mock_redis = AsyncMock()
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await cache_manager.cache_project_context(project_id, {"test": "data"})

            # Проверяем что get_connection вызван с project_id
            mock_get_connection.assert_called_once_with(str(project_id))

        # Тест get_project_context
        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection"
        ) as mock_get_connection:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = '{"context": {"test": "data"}}'
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await cache_manager.get_project_context(project_id)

            # Проверяем что get_connection вызван с project_id
            mock_get_connection.assert_called_once_with(str(project_id))

        # Тест cache_agent_config (использует SYSTEM_PROJECT_ID)
        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection"
        ) as mock_get_connection:
            mock_redis = AsyncMock()
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await cache_manager.cache_agent_config("test_agent", {"config": "value"})

            # Проверяем что get_connection вызван с SYSTEM_PROJECT_ID
            from app.constants import SYSTEM_PROJECT_ID

            mock_get_connection.assert_called_once_with(str(SYSTEM_PROJECT_ID))

        # Тест get_agent_config (использует SYSTEM_PROJECT_ID)
        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection"
        ) as mock_get_connection:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = '{"config": {"value": "test"}}'
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            await cache_manager.get_agent_config("test_agent")

            # Проверяем что get_connection вызван с SYSTEM_PROJECT_ID
            from app.constants import SYSTEM_PROJECT_ID

            mock_get_connection.assert_called_once_with(str(SYSTEM_PROJECT_ID))

    @pytest.mark.asyncio
    async def test_project_isolation_in_context_operations(self, cache_manager):
        """Проверить изоляцию проектов в контекстных операциях."""
        project1_id = uuid4()
        project2_id = uuid4()

        context1 = {"step": 1, "data": "project1"}
        context2 = {"step": 2, "data": "project2"}

        # Мокаем Redis сервис
        mock_redis_service = AsyncMock()
        mock_redis1 = AsyncMock()
        mock_redis2 = AsyncMock()

        def get_connection_side_effect(project_id_str):
            if project_id_str == str(project1_id):
                return mock_redis1
            elif project_id_str == str(project2_id):
                return mock_redis2
            else:
                raise ValueError(f"Unexpected project_id: {project_id_str}")

        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection",
            side_effect=get_connection_side_effect,
        ):
            # Сохраняем контекст для project1
            await cache_manager.cache_project_context(project1_id, context1)
            # Сохраняем контекст для project2
            await cache_manager.cache_project_context(project2_id, context2)

            # Проверяем что использовались разные соединения
            assert mock_redis1.setex.called
            assert mock_redis2.setex.called

            # Проверяем что ключи разные
            call1_args = mock_redis1.setex.call_args[0]
            call2_args = mock_redis2.setex.call_args[0]
            assert call1_args[0] != call2_args[0]  # Разные ключи для разных проектов

    @pytest.mark.asyncio
    async def test_project_id_validation(self, cache_manager):
        """Проверить валидацию project_id."""
        # Тест с None project_id должен вызывать ошибку или использовать значение по умолчанию
        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection"
        ) as mock_get_connection:
            mock_redis = AsyncMock()
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            # Должен работать с валидным UUID
            valid_project_id = uuid4()
            await cache_manager.cache_project_context(
                valid_project_id, {"test": "data"}
            )
            mock_get_connection.assert_called_with(str(valid_project_id))

    @pytest.mark.asyncio
    async def test_system_project_id_usage(self, cache_manager):
        """Проверить использование SYSTEM_PROJECT_ID для агентных конфигураций."""
        with patch(
            "app.services.cache.cache_manager.redis_service.get_connection"
        ) as mock_get_connection:
            mock_redis = AsyncMock()
            mock_get_connection.return_value.__aenter__.return_value = mock_redis

            agent_type = "test_agent"
            config = {"model": "gpt-4"}

            await cache_manager.cache_agent_config(agent_type, config)

            from app.constants import SYSTEM_PROJECT_ID

            mock_get_connection.assert_called_once_with(str(SYSTEM_PROJECT_ID))

            # Проверяем что данные содержат agent_type
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            key = call_args[0]  # ключ
            ttl = call_args[1]  # TTL
            data = call_args[2]  # данные

            import json

            parsed_data = json.loads(data)
            assert parsed_data["agent_type"] == agent_type
            assert parsed_data["config"] == config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
