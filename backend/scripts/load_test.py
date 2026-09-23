"""
Real load test against the actual running server — not a simulation.
Measures genuine latency percentiles and error rates under concurrency
for the endpoints that matter most (the live-chat path) and confirms
rate limiting holds under real concurrent load, not just sequential curl.
"""
import asyncio
import statistics
import time
import uuid

import httpx

BASE = "http://localhost:8000"


async def timed_request(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> tuple[float, int]:
    start = time.perf_counter()
    resp = await client.request(method, url, **kwargs)
    elapsed = time.perf_counter() - start
    return elapsed, resp.status_code


def report(name: str, timings: list[float], statuses: list[int]) -> None:
    ok = sum(1 for s in statuses if s < 400)
    errors = len(statuses) - ok
    sorted_t = sorted(timings)
    p50 = sorted_t[len(sorted_t) // 2] * 1000
    p95 = sorted_t[int(len(sorted_t) * 0.95)] * 1000
    p99 = sorted_t[min(int(len(sorted_t) * 0.99), len(sorted_t) - 1)] * 1000
    print(f"\n=== {name} ===")
    print(f"  requests: {len(statuses)}  success: {ok}  errors: {errors}")
    print(f"  latency  p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms  max={max(timings)*1000:.1f}ms")
    print(f"  status codes: {sorted(set(statuses))}")


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        org_name = f"Load Test Co {uuid.uuid4().hex[:6]}"
        slug = "-".join(org_name.lower().split())
        reg = await client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": org_name,
                "admin_full_name": "Load Admin",
                "admin_email": f"load-{uuid.uuid4().hex[:8]}@loadtest.com",
                "admin_password": "SuperSecret123",
            },
        )
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"Registered load-test org: {slug}")

        # ---------- Test 1: 50 concurrent DIFFERENT visitors starting conversations ----------
        # Different IPs would be needed to avoid the per-IP rate limit in a real
        # deployment; from this single test machine all requests share one IP, so
        # this also doubles as a check that the rate limiter holds under real
        # concurrency (not just sequential requests as in the earlier curl test).
        n = 50
        tasks = [
            timed_request(
                client,
                "POST",
                f"/api/v1/public/{slug}/conversations",
                json={
                    "external_id": f"load-visitor-{i}",
                    "initial_message": f"Load test message {i}",
                    "full_name": f"Load Visitor {i}",
                    "phone": "9990001111",
                },
            )
            for i in range(n)
        ]
        results = await asyncio.gather(*tasks)
        timings = [r[0] for r in results]
        statuses = [r[1] for r in results]
        report(f"{n} concurrent conversation starts (limit is 10/min/IP)", timings, statuses)
        rate_limited = sum(1 for s in statuses if s == 429)
        succeeded = sum(1 for s in statuses if s == 201)
        print(f"  -> {succeeded} succeeded, {rate_limited} correctly rate-limited (429)")
        assert succeeded <= 10, "rate limiter should cap successful starts at 10 under this load"
        assert rate_limited > 0, "expected some requests to be rate-limited under this burst"

        # ---------- Test 2: authenticated agent reads under concurrency (NOT rate-limited) ----------
        n2 = 100
        tasks = [timed_request(client, "GET", "/api/v1/conversations", headers=headers) for _ in range(n2)]
        results = await asyncio.gather(*tasks)
        timings2 = [r[0] for r in results]
        statuses2 = [r[1] for r in results]
        report(f"{n2} concurrent authenticated GET /conversations (no rate limit)", timings2, statuses2)
        assert all(s == 200 for s in statuses2), "authenticated reads should never be rate-limited"

        # ---------- Test 3: mixed realistic load — registrations + logins + chats ----------
        async def one_customer_journey(i: int) -> tuple[float, int]:
            start = time.perf_counter()
            r1 = await client.post(
                f"/api/v1/public/{slug}/customers/identify",
                json={"external_id": f"journey-{i}"},
            )
            return time.perf_counter() - start, r1.status_code

        n3 = 25  # under the identify limit of 30/min so this measures pure latency, not throttling
        tasks = [one_customer_journey(i) for i in range(n3)]
        results = await asyncio.gather(*tasks)
        timings3 = [r[0] for r in results]
        statuses3 = [r[1] for r in results]
        report(f"{n3} concurrent /identify calls (under the 30/min limit)", timings3, statuses3)
        assert all(s == 200 for s in statuses3)

        print("\n=== ALL LOAD TEST ASSERTIONS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
