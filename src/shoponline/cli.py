"""Command line entry point: shoponline <command>."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from shoponline.config import ConfigError, Settings, load_settings

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


def _setup_logging(settings: Settings, file_name: str) -> None:
    """Log to the console and to <data>/logs/<file_name>, rotated at 5 MB, ten files kept.
    Every record is scrubbed of the backup password."""
    from shoponline.backup.sevenzip import RedactFilter

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    redact = RedactFilter(settings.backup_password)
    for handler in (
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / file_name, maxBytes=5_000_000, backupCount=10, encoding="utf-8"
        ),
    ):
        handler.setFormatter(formatter)
        # On the handler, not the logger: records propagated from child loggers skip
        # the root logger's own filters.
        handler.addFilter(redact)
        root.addHandler(handler)


def _backup_context(args: argparse.Namespace, settings: Settings):
    from shoponline.backup import pgtools
    from shoponline.backup.runner import Context
    from shoponline.backup.sevenzip import find_exe
    from shoponline.db.session import get_engine, session_factory

    try:
        pg_bin = pgtools.find_bin(getattr(args, "pg_bin", None))
    except pgtools.PgToolError:
        if getattr(args, "pg_bin", None):
            raise
        pg_bin = None  # only an application backup can do without it
    seven = getattr(args, "seven_zip", None)
    return Context(
        settings=settings,
        session_factory=session_factory(settings.database_url),
        engine=get_engine(settings.database_url),
        repo_root=REPO_ROOT,
        pg_bin=pg_bin,
        seven_zip=find_exe(seven) if seven else None,
        drive=_drive_place(settings),
    )


def _drive_place(settings: Settings):
    from shoponline.backup.drive import DriveClient
    from shoponline.db.session import session_factory

    return DriveClient(session_factory(settings.database_url))


def _cmd_drive(args: argparse.Namespace) -> int:
    from shoponline.backup import drive as drive_module
    from shoponline.secrets_store import CredentialStoreUnavailable

    settings = load_settings()
    client = _drive_place(settings)
    actor = getpass.getuser()
    try:
        return _drive_action(args, client, actor, drive_module)
    except CredentialStoreUnavailable as exc:
        print(f"Credential Manager không dùng được: {exc}", file=sys.stderr)
        return 1
    except drive_module.DriveError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1


def _drive_action(args, client, actor: str, drive_module) -> int:
    import time

    if args.action == "set-client":
        secret = getpass.getpass("Client Secret (để trống giữ giá trị đã lưu): ")
        client.set_client(args.client_id, secret, actor)
        print("Đã lưu Client ID và Secret (Secret nằm trong Windows Credential Manager).")
    elif args.action == "status":
        state = client.state()
        if args.check:
            try:
                client.check()
            except drive_module.DriveError as exc:
                print(f"Kiểm tra lỗi: {exc}", file=sys.stderr)
            state = client.state()
        secret_text = "đã lưu" if state["has_secret"] else "chưa có"
        print(f"Trạng thái: {state['status']}")
        print(f"Client ID: {state['client_id'] or '-'} (Secret: {secret_text})")
        print(f"Tài khoản: {state['email'] or '-'}; thư mục: {state['folder_id'] or '-'}")
        if state["error"]:
            print(f"Lỗi gần nhất: {state['error']}")
    elif args.action == "connect":
        device = client.start_device_flow(actor)
        print(f"Mở {device['url']} và nhập mã: {device['user_code']}")
        wait = device["interval"]
        while True:
            time.sleep(wait)
            result = client.poll_device_flow()
            wait = result["interval"]
            if result["status"] in ("pending", "slow_down"):
                continue
            print(result["message"])
            return 0 if result["status"] == "connected" else 1
    elif args.action == "disconnect":
        client.disconnect(actor)
        print("Đã ngắt kết nối Google Drive (file trên Drive vẫn còn).")
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    from shoponline.backup import runner

    settings = load_settings()
    _setup_logging(settings, "backup.log")
    ctx = _backup_context(args, settings)
    if args.action == "process-queue":
        with runner.backup_lock(ctx.engine) as lock:
            if lock is None:
                print("Đang có tiến trình sao lưu khác chạy.", file=sys.stderr)
                return runner.EXIT_LOCKED
            with ctx.session_factory() as db:
                runner.mark_interrupted(db)
            return runner.worst(runner.process_requests(ctx))
    if args.action == "verify":
        from shoponline.backup import verify

        ok, message = verify.verify(ctx, verify.locate(ctx, args.target))
        print(("Hợp lệ: " if ok else "Không hợp lệ: ") + message)
        return 0 if ok else 1
    if args.if_due:
        return runner.if_due(ctx)
    reason = args.reason
    actor = getpass.getuser() if reason == "manual" else runner.SYSTEM
    # Backups before a deploy stay on this machine only (the owner's decision).
    to_drive = reason != "deploy" and not args.no_drive
    outcome = runner.run_now(ctx, args.kind, reason, actor, to_drive)
    print(outcome.message, file=sys.stderr if outcome.exit_code else sys.stdout)
    return outcome.exit_code


def _cmd_web(_args: argparse.Namespace) -> int:
    import uvicorn

    from shoponline.web.app import create_app

    settings = load_settings()
    _setup_logging(settings, "web.log")
    # One line per page load would fill the file; keep only failed requests.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # log_config=None leaves uvicorn's loggers to propagate to the root handlers set up above.
    uvicorn.run(
        create_app(settings), host=settings.web_host, port=settings.web_port, log_config=None
    )
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
    _setup_logging(settings, "robot.log")
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
    """Files are always swept by the keep rules; --apply decides only the customer data."""
    from shoponline.db.session import session_scope
    from shoponline.maintenance import retention
    from shoponline.sapjobs import sap_settings

    settings = load_settings()
    _setup_logging(settings, "retention.log")
    actor = getpass.getuser()
    with session_scope(settings.database_url) as session:
        plan = retention.find_expired(session, settings)
        if args.apply:
            retention.apply(session, plan, actor)
        keep_days = sap_settings.load(session, os.environ).evidence_keep_days
        swept = retention.sweep_files(session, settings, keep_days, actor)
    verb = "Đã xóa" if args.apply else "Sẽ xóa (chế độ liệt kê, thêm --apply để xóa thật)"
    lines = [
        f"Thời hạn {settings.retention_days} ngày, mốc {plan.cutoff:%Y-%m-%d}",
        f"{verb}: tên và địa chỉ của {len(plan.customer_orders)} đơn",
        *(f"  đơn {platform} {order_id}" for platform, order_id in plan.customer_orders),
        f"Giữ lại vì chưa có DO trong sổ gửi kế toán hoặc chưa vào file Shop Online: "
        f"{len(plan.held_orders)} đơn",
        *(f"  đơn {platform} {order_id}" for platform, order_id in plan.held_orders),
        f"Đã xóa {len(swept.files)} file hết dùng và {swept.screenshots} ảnh màn hình robot",
        *(f"  file {path}" for path in swept.files),
    ]
    logging.getLogger("shoponline.retention").info("\n".join(lines))
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
        "retention",
        help="Xóa file hết dùng; liệt kê (hoặc xóa với --apply) dữ liệu khách quá thời hạn lưu",
    )
    keep.add_argument(
        "--apply", action="store_true", help="Xóa thật dữ liệu khách thay vì chỉ liệt kê"
    )
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

    backup = sub.add_parser("backup", help="Sao lưu mã hóa (database, ứng dụng, toàn bộ)")
    backup_actions = backup.add_subparsers(dest="action", required=True)
    backup_run = backup_actions.add_parser("run", help="Tạo một bản sao lưu")
    backup_run.add_argument("--kind", choices=("db", "app", "full"), default="db")
    backup_run.add_argument(
        "--reason", choices=("manual", "deploy", "migration"), default="manual"
    )
    backup_run.add_argument(
        "--if-due",
        action="store_true",
        help="Tác vụ 15 phút: xử lý yêu cầu đang chờ rồi chạy bản theo lịch nếu tới hạn",
    )
    backup_run.add_argument("--no-drive", action="store_true", help="Không tải lên Google Drive")
    backup_verify = backup_actions.add_parser("verify", help="Kiểm tra một bản sao lưu")
    backup_verify.add_argument("target", help="Số bản (#id), tên file hoặc đường dẫn")
    backup_actions.add_parser("process-queue", help="Xử lý các yêu cầu sao lưu đang chờ")
    for action in (backup_run, backup_verify):
        action.add_argument("--pg-bin", default=None, help="Thư mục PostgreSQL bin")
        action.add_argument("--seven-zip", default=None, help="Đường dẫn 7z.exe")
    backup.set_defaults(func=_cmd_backup)

    drive = sub.add_parser("drive", help="Kết nối Google Drive để lưu bản sao lưu")
    drive_actions = drive.add_subparsers(dest="action", required=True)
    set_client = drive_actions.add_parser("set-client", help="Lưu OAuth Client ID và Secret")
    set_client.add_argument("--client-id", required=True)
    drive_actions.add_parser("connect", help="Kết nối bằng mã thiết bị (in mã và link)")
    drive_status = drive_actions.add_parser("status", help="Xem trạng thái kết nối")
    drive_status.add_argument("--check", action="store_true", help="Gọi Google để kiểm tra")
    drive_actions.add_parser("disconnect", help="Thu hồi quyền và xóa token ở máy này")
    drive.set_defaults(func=_cmd_drive)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
