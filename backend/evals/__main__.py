from .runner import EvalRunner
import asyncio

if __name__ == "__main__":
    runner = EvalRunner()
    asyncio.run(runner.run())
