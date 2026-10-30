import pytest

from app.engine.spark import SparkEngine, spark_supported


def test_spark_engine_is_stub():
    assert spark_supported() is False
    with pytest.raises(NotImplementedError, match="local"):
        SparkEngine().execute({"executionId": 1})
