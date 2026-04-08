# import asyncio

# async def blocking():
#     #import time
#     #time.sleep(2)
#     await asyncio.sleep(2)
#     return "done"

# async def main():
#     #result = await asyncio.to_thread(blocking)
#     result = await blocking()
#     print(result)

# asyncio.run(main())

import asyncio

async def io_task(name: str, delay: float) -> str:
    await asyncio.sleep(delay)
    return f"{name} done"

async def main():
    results = await asyncio.gather(
        io_task("A", 1),
        io_task("B", 1),
    )
    print(results)

asyncio.run(main())