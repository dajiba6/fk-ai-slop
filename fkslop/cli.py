import argparse
import json


def main():
    parser = argparse.ArgumentParser(prog="fk")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="启动网站（含后台任务和 /mcp）")
    sub.add_parser("poll", help="为所有来源排队一次轮询（systemd 定时器调用）")
    sub.add_parser("mcp", help="以 stdio 方式运行 MCP")
    sub.add_parser("rebuild", help="从文件重建索引并重新排队未完成的任务")
    sub.add_parser("status", help="查看任务队列")
    sub.add_parser("favorites", help="按收藏重新生成 favorites/ 下的 Markdown")
    add = sub.add_parser("add-source", help="添加来源")
    add.add_argument("url")
    submit = sub.add_parser("submit", help="投递单条链接")
    submit.add_argument("url")
    args = parser.parse_args()

    if args.command == "serve":
        from fkslop.web.app import main as serve
        serve()
    elif args.command == "mcp":
        from fkslop.mcp_server import main as mcp
        mcp()
    elif args.command == "poll":
        from fkslop import pipeline
        print(f"queued {pipeline.poll_all()} sources")
    elif args.command == "rebuild":
        from fkslop import indexer
        print(f"indexed {indexer.rebuild()} items")
    elif args.command == "favorites":
        from fkslop import favorites
        print(f"exported {favorites.sync_all()} favorites to {favorites.DIR}")
    elif args.command == "status":
        from fkslop import db
        for row in db.job_stats():
            print(f"{row['kind']:<11} {row['status']:<8} {row['n']}")
    elif args.command == "add-source":
        from fkslop import pipeline
        print(json.dumps(pipeline.add_source(args.url), ensure_ascii=False, indent=2))
    elif args.command == "submit":
        from fkslop import pipeline
        print(json.dumps(pipeline.submit_url(args.url), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
