"""Command line entry point: shoponline <command>."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from shoponline.config import ConfigError, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_migrations(database_url: str, revision: str = "head") -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    command.upgrade(cfg, revision)


def _cmd_migrate(_args: argparse.Namespace) -> int:
    settings = load_settings()
    run_migrations(settings.database_url)
    print("Database đã ở bản schema mới nhất.")
    return 0


def _cmd_create_user(args: argparse.Namespace) -> int:
    from shoponline.db.session import session_scope
    from shoponline.web.auth import set_user

    settings = load_settings()
    password = getpass.getpass(f"Mật khẩu cho {args.username}: ")
    if password != getpass.getpass("Nhập lại mật khẩu: "):
        print("Hai lần nhập không khớp.", file=sys.stderr)
        return 1
    with session_scope(settings.database_url) as session:
        set_user(session, args.username, password, args.role)
    print(f"Đã lưu người dùng {args.username} ({args.role}).")
    return 0


def _cmd_web(_args: argparse.Namespace) -> int:
    import uvicorn

    from shoponline.web.app import create_app

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.web_host, port=settings.web_port)
    return 0


def _cmd_robot(_args: argparse.Namespace) -> int:
    import shoponline.saprobot.transactions  # noqa: F401 - registers the SAP steps
    from shoponline.db.session import get_engine, session_factory
    from shoponline.sapjobs import sap_settings
    from shoponline.saprobot.errors import SessionUnavailable
    from shoponline.saprobot.popups import load_rules
    from shoponline.saprobot.screen import Screens
    from shoponline.saprobot.session import logoff_sessions_of, scripting_engine
    from shoponline.saprobot.worker import RobotAlreadyRunning, Worker, run_forever

    settings = load_settings()
    env = dict(os.environ)
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                log_dir / "robot.log", maxBytes=5_000_000, backupCount=10, encoding="utf-8"
            ),
        ],
    )
    factory = session_factory(settings.database_url)
    worker = Worker(
        settings,
        factory,
        scripting_engine,
        Screens.load(REPO_ROOT / "config" / "sap_screens.yaml"),
        load_rules(REPO_ROOT / "config" / "sap_popups.yaml"),
        env=env,
    )

    def log_off_leftovers() -> None:
        """A robot stopped mid-job may have left its SAP logon open; close it, start clean."""
        with factory() as db:
            config = sap_settings.load(db, env)
            db.commit()
        if config.target is None or not config.sap_user:
            return
        try:
            engine = scripting_engine(start=False)
        except SessionUnavailable:
            return  # SAP Logon is not running, so nothing is logged on
        closed = logoff_sessions_of(engine, config.target, config.sap_user)
        if closed:
            logging.getLogger(__name__).info("Đã đăng xuất %d phiên SAP còn sót của robot", closed)

    try:
        run_forever(worker, get_engine(settings.database_url), on_start=log_off_leftovers)
    except RobotAlreadyRunning as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("Robot dừng.")
    return 0


def _cmd_sap_secret(args: argparse.Namespace) -> int:
    """Store, or report on, the robot user's SAP secret kept on this machine."""
    from shoponline.db.session import session_scope
    from shoponline.sapjobs import sap_settings
    from shoponline.saprobot import credentials

    settings = load_settings()
    env = dict(os.environ)
    user = (args.user or "").strip()
    if not user:
        with session_scope(settings.database_url) as session:
            user = sap_settings.load(session, env).sap_user
    if not user:
        print("Chưa có user SAP: điền ở trang Kết nối SAP hoặc dùng --user.", file=sys.stderr)
        return 1
    if args.action == "status":
        present = credentials.read_password(user, env) is not None
        print(f"User {user.upper()}: {'đã có' if present else 'chưa có'} mật khẩu trên máy này.")
        return 0
    secret = getpass.getpass(f"Mật khẩu SAP của {user.upper()}: ")
    if not secret:
        print("Mật khẩu trống, không lưu.", file=sys.stderr)
        return 1
    if secret != getpass.getpass("Nhập lại mật khẩu: "):
        print("Hai lần nhập không khớp.", file=sys.stderr)
        return 1
    credentials.store_password(user, secret)
    print(f"Đã lưu mật khẩu của {user.upper()} vào Windows Credential Manager của tài khoản này.")
    return 0


def _cmd_robot_switch(args: argparse.Namespace) -> int:
    from shoponline.db.session import session_scope
    from shoponline.sapjobs import queue

    settings = load_settings()
    actor = getpass.getuser()
    with session_scope(settings.database_url) as session:
        if args.command == "robot-pause":
            queue.pause(session, actor, args.reason or f"{actor} tạm dừng từ dòng lệnh")
        else:
            queue.resume(session, actor)
    print("Robot đã tạm dừng." if args.command == "robot-pause" else "Robot đã bật lại.")
    return 0


def _cmd_retention(args: argparse.Namespace) -> int:
    from datetime import datetime

    from shoponline.db.session import session_scope
    from shoponline.maintenance import retention

    settings = load_settings()
    with session_scope(settings.database_url) as session:
        plan = retention.find_expired(session, settings)
        if args.apply:
            retention.apply(session, plan, getpass.getuser())
    if args.apply:
        retention.delete_files(settings, plan)
    verb = "Đã xóa" if args.apply else "Sẽ xóa (chế độ liệt kê, thêm --apply để xóa thật)"
    lines = [
        f"{datetime.now():%Y-%m-%d %H:%M} thời hạn {settings.retention_days} ngày, "
        f"mốc {plan.cutoff:%Y-%m-%d}",
        f"{verb}: tên và địa chỉ của {len(plan.customer_orders)} đơn, {len(plan.files)} file",
        *(f"  đơn {platform} {order_id}" for platform, order_id in plan.customer_orders),
        *(f"  file {path}" for path in plan.files),
        f"Giữ lại vì chưa có DO trong sổ gửi kế toán: {len(plan.held_orders)} đơn",
        *(f"  đơn {platform} {order_id}" for platform, order_id in plan.held_orders),
    ]
    text = "\n".join(lines)
    print(text)
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "retention.log").open("a", encoding="utf-8") as log:
        log.write(text + "\n\n")
    return 0


def _cmd_accounting_ledger(args: argparse.Namespace) -> int:
    from datetime import date

    from shoponline.accounting import ledger
    from shoponline.db.session import session_scope

    settings = load_settings()
    actor = getpass.getuser()
    with session_scope(settings.database_url) as session:
        if args.action == "list":
            cutoff = ledger.get_cutoff(session)
            entries = ledger.list_baseline(session)
            print(f"Mốc ngày: {cutoff.isoformat() if cutoff else 'chưa đặt'}")
            print(f"{len(entries)} DO trong sổ nền:")
            for entry in entries:
                owner = f"{entry.platform} {entry.platform_order_id}" if entry.platform else "-"
                print(f"  {entry.delivery}  {owner}")
        elif args.action == "add":
            added = ledger.add_baseline(session, args.deliveries, actor)
            print(f"Đã thêm {len(added)} DO vào sổ nền.")
        elif args.action == "remove":
            removed = ledger.remove_baseline(session, args.deliveries, actor)
            print(f"Đã gỡ {len(removed)} DO khỏi sổ nền.")
        elif args.set:
            try:
                day = date.fromisoformat(args.set)
            except ValueError as exc:
                raise ValueError(f"Ngày sai dạng (cần YYYY-MM-DD): {args.set}") from exc
            ledger.set_cutoff(session, day, actor)
            print(f"Đã đặt mốc ngày {day.isoformat()}.")
        else:
            cutoff = ledger.get_cutoff(session)
            print(f"Mốc ngày: {cutoff.isoformat() if cutoff else 'chưa đặt'}")
    return 0


def _cmd_accounting_run(args: argparse.Namespace) -> int:
    from shoponline.accounting import ledger
    from shoponline.db.session import session_scope

    settings = load_settings()
    with session_scope(settings.database_url) as session:
        count = ledger.revoke_run(session, args.run_id, getpass.getuser(), apply=args.yes)
    if args.yes:
        print(f"Đã gỡ đợt #{args.run_id}: {count} DO ra khỏi sổ. Báo kế toán không dùng file đó.")
    else:
        print(
            f"Đợt #{args.run_id} có {count} DO sẽ được gỡ khỏi sổ "
            "(chế độ xem, thêm --yes để gỡ thật)."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="shoponline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Nâng schema database lên bản mới nhất").set_defaults(
        func=_cmd_migrate
    )
    user = sub.add_parser("create-user", help="Tạo người dùng hoặc đặt lại mật khẩu")
    user.add_argument("username")
    user.add_argument("--role", choices=("admin", "viewer"), default="viewer")
    user.set_defaults(func=_cmd_create_user)
    sub.add_parser("web", help="Chạy web").set_defaults(func=_cmd_web)
    sub.add_parser("robot", help="Chạy robot SAP (trên máy robot)").set_defaults(func=_cmd_robot)
    pause = sub.add_parser("robot-pause", help="Tạm dừng robot SAP")
    pause.add_argument("--reason", default="")
    pause.set_defaults(func=_cmd_robot_switch)
    sub.add_parser("robot-resume", help="Bật lại robot SAP").set_defaults(func=_cmd_robot_switch)
    sap_secret = sub.add_parser(
        "sap-password", help="Đặt hoặc xem mật khẩu SAP của robot (chạy dưới tài khoản chạy robot)"
    )
    sap_secret.add_argument("action", choices=("set", "status"))
    sap_secret.add_argument("--user", default="", help="Mặc định: user SAP trong cấu hình")
    sap_secret.set_defaults(func=_cmd_sap_secret)
    keep = sub.add_parser(
        "retention", help="Liệt kê (hoặc xóa với --apply) dữ liệu khách quá thời hạn lưu"
    )
    keep.add_argument("--apply", action="store_true", help="Xóa thật thay vì chỉ liệt kê")
    keep.set_defaults(func=_cmd_retention)
    book = sub.add_parser("accounting-ledger", help="Sổ DO đã gửi kế toán (sổ nền và mốc ngày)")
    book_actions = book.add_subparsers(dest="action", required=True)
    book_actions.add_parser("list", help="In các DO nền và mốc ngày")
    for name, text in (("add", "Thêm DO vào sổ nền"), ("remove", "Gỡ DO khỏi sổ nền")):
        action = book_actions.add_parser(name, help=text)
        action.add_argument("deliveries", nargs="+")
    cutoff = book_actions.add_parser("cutoff", help="Xem hoặc đổi mốc ngày")
    cutoff.add_argument("--set", default="", help="Mốc mới, dạng YYYY-MM-DD")
    book.set_defaults(func=_cmd_accounting_ledger)
    run = sub.add_parser("accounting-run", help="Quản lý đợt gửi kế toán")
    run_actions = run.add_subparsers(dest="action", required=True)
    revoke = run_actions.add_parser("revoke", help="Gỡ cả một đợt đã chốt khỏi sổ")
    revoke.add_argument("run_id", type=int)
    revoke.add_argument("--yes", action="store_true", help="Gỡ thật thay vì chỉ xem")
    run.set_defaults(func=_cmd_accounting_run)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
