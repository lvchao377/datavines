"""Spark execution engine interface.

The class exists so jobs can select engineType=spark and the platform can
list the engine. execute() always refuses to run. There is no Spark session,
no submit script and no Livy client in this single-node build.
"""


class SparkEngine:
    name = "spark"

    def execute(self, context: dict) -> None:
        raise NotImplementedError(
            "Spark 执行引擎仅保留接口，未实现。请将作业的 engineType 设为 local。"
            " 本实现不提交 Spark/Livy 作业。"
        )


def spark_supported() -> bool:
    return False
