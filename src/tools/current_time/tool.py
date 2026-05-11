from langchain_core.tools import BaseTool


def create_default() -> "GetCurrentTimeTool":
    return GetCurrentTimeTool()


class GetCurrentTimeTool(BaseTool):
    name: str = "get_current_time"
    description: str = "获取当前日期和时间。当用户询问时间、今天是几号、几点等信息时使用。"

    def _run(self) -> str:
        from datetime import datetime
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    async def _arun(self) -> str:
        return self._run()
