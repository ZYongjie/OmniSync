import argparse
import json
import sys
from typing import Any

import httpx


def _make_headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _print_response(resp: httpx.Response) -> None:
    print(f"STATUS: {resp.status_code}")
    try:
        body: Any = resp.json()
        print(json.dumps(body, ensure_ascii=False, indent=2))
    except ValueError:
        print(resp.text)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OmniSync debug request client",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL, default: http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--token",
        default="test",
        help="APP_TOKEN for Bearer auth; not needed for health",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="request timeout in seconds",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="GET /healthz")

    upsert = sub.add_parser("upsert", help="POST /v1/items/{key}")
    upsert.add_argument("key", help="item key")
    upsert.add_argument("value", help="item value")
    upsert.add_argument(
        "--expected-version",
        type=int,
        default=None,
        help="optional expected_version for optimistic lock",
    )

    get_cmd = sub.add_parser("get", help="GET /v1/items/{key}")
    get_cmd.add_argument("key", help="item key")

    list_cmd = sub.add_parser("list", help="GET /v1/items")
    list_cmd.add_argument("--since", default=None, help="ISO8601 timestamp")
    list_cmd.add_argument("--limit", type=int, default=100, help="1..500")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    headers = _make_headers(args.token)

    try:
        with httpx.Client(timeout=args.timeout, headers=headers) as client:
            if args.command == "health":
                resp = client.get(f"{base_url}/healthz")
            elif args.command == "upsert":
                payload: dict[str, Any] = {"value": args.value}
                if args.expected_version is not None:
                    payload["expected_version"] = args.expected_version
                resp = client.post(f"{base_url}/v1/items/{args.key}", json=payload)
            elif args.command == "get":
                resp = client.get(f"{base_url}/v1/items/{args.key}")
            elif args.command == "list":
                params: dict[str, Any] = {"limit": args.limit}
                if args.since:
                    params["since"] = args.since
                resp = client.get(f"{base_url}/v1/items", params=params)
            else:
                parser.error("unknown command")
                return 2
    except httpx.RequestError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    _print_response(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
