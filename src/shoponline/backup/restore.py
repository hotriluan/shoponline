"""Restore a backup: a drill into a scratch database, or the real system with a way back.

Real restore (production): the backup is unpacked and checked first, then web and robot stop,
a safety backup of the current state is taken, the business schema (public) is replaced, the
schema is migrated forward and everybody has to log in again. Any failure after the safety
backup puts that backup back ("rolled_back"). Schema ops (web accounts, backup log, Drive
connection) is never replaced, so accounts do not roll back with the data.
The caller holds the backup lock for the whole run.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from shoponline.backup import archive, maintenance, pgtools, runner, staging, verify
from shoponline.backup import manifest as mf
from shoponline.backup.runner import Context
from shoponline.backup.sevenzip import SevenZipError
from shoponline.db.models import BackupRequest, BackupRun

log = logging.getLogger(__name__)

# The migrations of the code that is running, wherever the backed-up repo is.
CODE_ROOT = Path(__file__).resolve().parents[3]
STATUS_FILE = "restore-status.json"
RESTORE_REQUEST_MAX_AGE = timedelta(minutes=10)
ACTIVE_USER_WINDOW = timedelta(minutes=5)


class RestoreError(RuntimeError):
    """A failure whose message can be shown to the administrator."""


class RestoreRefused(RestoreError):
    """The restore was refused before anything was touched."""


@dataclass
class Prepared:
    archive: Path
    root: Path
    manifest: mf.Manifest | None
    dump: Path | None
    legacy: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class Result:
    status: str  # done | rolled_back | failed
    message: str
    safety_run_id: int | None = None


# --- finding and unpacking a backup ---------------------------------------------------------


def fetch(ctx: Context, target: str) -> Path:
    """The backup file on this machine; one that is only on Drive is downloaded first."""
    try:
        return verify.locate(ctx, target).path
    except verify.BackupNotFound:
        pass
    with ctx.session_factory() as db:
        run = (
            db.get(BackupRun, int(target))
            if target.isdigit()
            else db.scalar(select(BackupRun).where(BackupRun.file_name == Path(target).name))
        )
        info = (run.file_name, run.drive_file_id) if run else None
    if info is None or not info[1] or ctx.drive is None or not ctx.settings.backup_dirs:
        raise RestoreRefused(f"Không thấy bản sao lưu {target} ở máy chủ hay trên Google Drive")
    name, file_id = info
    folder = ctx.settings.backup_dirs[0]
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / (name + ".partial")
    ctx.drive.download(file_id, partial)  # checks the MD5 and removes the file when it differs
    partial.replace(folder / name)
    return folder / name


def prepare(ctx: Context, archive_path: Path, work: Path) -> Prepared:
    """Unpack into work and check every part against the manifest. A backup from before the
    manifest existed holds one *.dump and is accepted with a warning."""
    root = work / "unpacked"
    try:
        ctx.sevenzip().extract(archive_path, root, allowed=archive.allowed_member)
    except SevenZipError as exc:
        raise RestoreRefused(str(exc)) from exc
    manifest_file = root / mf.NAME
    if manifest_file.is_file():
        manifest = mf.Manifest.read(manifest_file)
        bad = mf.check_parts(root, manifest)
        if bad:
            raise RestoreRefused("Bản sao lưu bị sửa hoặc hỏng ở: " + ", ".join(bad[:5]))
        dump = root / archive.DUMP
        return Prepared(archive_path, root, manifest, dump if dump.is_file() else None, False)
    dumps = [p for p in root.iterdir() if p.is_file() and p.suffix == ".dump"]
    if len(dumps) != 1:
        raise RestoreRefused("Bản sao lưu cũ phải có đúng một file .dump")
    warning = "Bản sao lưu cũ không có manifest: không kiểm được phiên bản và số dòng"
    return Prepared(archive_path, root, None, dumps[0], True, [warning])


def _known_revisions(repo_root: Path) -> set[str]:
    script = ScriptDirectory.from_config(Config(str(repo_root / "alembic.ini")))
    return {rev.revision for rev in script.walk_revisions()}


def known_revisions() -> set[str]:
    """Schema revisions the running code can read (found once, then remembered)."""
    global _KNOWN
    if _KNOWN is None:
        _KNOWN = _known_revisions(CODE_ROOT)
    return _KNOWN


_KNOWN: set[str] | None = None


def check_version(ctx: Context, manifest: mf.Manifest) -> None:
    """A backup of a newer schema than this code knows cannot be read by this code."""
    revision = manifest.alembic_revision
    if revision and revision not in known_revisions():
        raise RestoreRefused(
            f"Bản sao lưu từ phiên bản mới hơn (revision {revision}); cập nhật mã trước"
        )


# --- schema work ------------------------------------------------------------------------------


def _engine(url: str):
    return create_engine(url, poolclass=NullPool)


def compare_counts(url: str, expected: dict[str, int]) -> dict[str, tuple[int | None, int | None]]:
    """Tables of schema public whose row count differs from `expected`: {table: (want, got)}."""
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            actual = mf.count_public_rows(conn)
    finally:
        engine.dispose()
    diff = {}
    for name in sorted(set(expected) | set(actual)):
        if expected.get(name) != actual.get(name):
            diff[name] = (expected.get(name), actual.get(name))
    return diff


def _same_database(a: str, b: str) -> bool:
    x, y = make_url(a), make_url(b)
    return (x.host, x.port or 5432, x.database) == (y.host, y.port or 5432, y.database)


def drill(ctx: Context, prep: Prepared) -> dict:
    """Restore into SHOPONLINE_RESTORE_DATABASE_URL and compare the rows with the manifest."""
    settings = ctx.settings
    if prep.dump is None:
        raise RestoreRefused("Bản này không có database để diễn tập")
    if not settings.restore_database_url:
        raise RestoreRefused("Thiếu SHOPONLINE_RESTORE_DATABASE_URL (database diễn tập)")
    if _same_database(settings.restore_database_url, settings.database_url):
        raise RestoreRefused("Database diễn tập trùng database đang chạy; từ chối")
    url = settings.restore_database_url
    engine = _engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("DROP SCHEMA IF EXISTS ops CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        pgtools.run(
            _pg_bin(ctx),
            "pg_restore",
            url,
            ["--no-owner", "--exit-on-error", "--single-transaction", str(prep.dump)],
        )
        with engine.connect() as conn:
            revision = mf.alembic_revision(conn)
    finally:
        engine.dispose()
    diff = compare_counts(url, prep.manifest.tables) if prep.manifest else {}
    return {
        "ok": not diff,
        "legacy": prep.legacy,
        "revision": revision,
        "diff": {k: list(v) for k, v in diff.items()},
        "warnings": prep.warnings,
    }


def _pg_bin(ctx: Context) -> Path:
    if ctx.pg_bin is None:
        raise RestoreError("Thiếu thư mục PostgreSQL bin (pg_restore)")
    return ctx.pg_bin


def restore_public_schema(ctx: Context, dump: Path, url: str, work: Path) -> None:
    """Replace schema public with the dump's, leaving schema ops alone.

    pg_restore's table of contents is cut down to the entries outside ops, then public is dropped
    and recreated and the rest restored in one transaction."""
    listing = pgtools.run(_pg_bin(ctx), "pg_restore", url, ["-l", str(dump)]).stdout.decode(
        "utf-8", "replace"
    )
    kept = [line for line in listing.splitlines() if not re.search(r"\sops\s", line)]
    toc = work / "restore-toc.txt"
    toc.write_text("\n".join(kept) + "\n", encoding="utf-8")
    engine = _engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT USAGE ON SCHEMA public TO PUBLIC"))
    finally:
        engine.dispose()
    pgtools.run(
        _pg_bin(ctx),
        "pg_restore",
        url,
        ["-L", str(toc), "--no-owner", "--exit-on-error", "--single-transaction", str(dump)],
    )


def run_migrate(database_url: str) -> None:
    from shoponline.cli import run_migrations

    run_migrations(database_url)


def service_control(ctx: Context, action: str) -> None:
    """Stop or start web and robot through scripts\\windows\\service-control.ps1."""
    script = ctx.repo_root / "scripts" / "windows" / "service-control.ps1"
    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Action",
            action,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-2:]
        raise RestoreError(
            f"Không {'dừng' if action == 'stop' else 'bật'} được web/robot: {' | '.join(tail)}"
        )


def swap_data(ctx: Context, new_data: Path, stamp: str) -> Path:
    """Put the data items of a full backup in place; what they replace is moved aside to
    backup-work\\before-restore-<stamp> (kept 7 days). The data folder itself is never renamed:
    this process writes its log in it."""
    settings = ctx.settings
    aside = settings.backup_work_dir / f"{staging.BEFORE_RESTORE_PREFIX}{stamp}"
    for child in sorted(new_data.iterdir()):
        if child.name in archive.DATA_SKIP:
            continue
        target = settings.data_dir / child.name
        if target.exists():
            aside.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(aside / child.name))
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)
    return aside


def bump_session_epoch(ctx: Context) -> None:
    with ctx.engine.begin() as conn:
        conn.execute(text("UPDATE ops.system_state SET session_epoch = session_epoch + 1"))


def _apply(ctx: Context, prep: Prepared, work: Path, stamp: str) -> None:
    """Data, business schema, count check, migrate, new session epoch: the steps both the
    restore and its way back share."""
    url = ctx.settings.database_url
    if prep.manifest is not None and prep.manifest.kind == "full" and (prep.root / "data").is_dir():
        swap_data(ctx, prep.root / "data", stamp)
    restore_public_schema(ctx, prep.dump, url, work)
    # Counts are compared before migrate: they check that the restore was faithful, and a
    # migration may legitimately add rows.
    if prep.manifest is not None:
        diff = compare_counts(url, prep.manifest.tables)
        if diff:
            shown = ", ".join(f"{t} {w}→{g}" for t, (w, g) in list(diff.items())[:5])
            raise RestoreError(f"Số dòng sau phục hồi khác bản sao lưu: {shown}")
    run_migrate(url)
    bump_session_epoch(ctx)


# --- status reporting -------------------------------------------------------------------------


def write_status(ctx: Context, **fields) -> None:
    store_status(ctx.settings, **fields)


def store_status(settings, **fields) -> None:
    path = settings.data_dir / STATUS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            current = {}
    current.update(fields)
    current["updated_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")


def read_status(settings) -> dict | None:
    try:
        return json.loads((settings.data_dir / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def take_banner(settings, username: str) -> tuple[str, str] | None:
    """(kind, message) for the first administrator to see the outcome of a finished restore,
    once. The web restarts during a restore, so the outcome is read from the status file."""
    status = read_status(settings)
    if not status or status.get("state") not in ("done", "rolled_back", "failed"):
        return None
    if status.get("banner_shown_by"):
        return None
    store_status(settings, banner_shown_by=username)
    kind = "info" if status["state"] == "done" else "error"
    prefix = {"done": "Phục hồi xong. ", "rolled_back": "Đã lùi lại. ", "failed": "Phục hồi lỗi. "}
    return kind, prefix[status["state"]] + (status.get("message") or "")


class _Progress:
    def __init__(self, ctx: Context, request_id: int | None):
        self.ctx, self.request_id = ctx, request_id

    def __call__(self, step: str) -> None:
        log.info("Phục hồi: %s", step)
        write_status(self.ctx, state="running", step=step)
        if self.request_id is not None:
            with self.ctx.session_factory() as db:
                db.execute(
                    update(BackupRequest)
                    .where(BackupRequest.id == self.request_id)
                    .values(message=step)
                )
                db.commit()

    def safety(self, run_id: int) -> None:
        write_status(self.ctx, safety_run_id=run_id)
        if self.request_id is not None:
            with self.ctx.session_factory() as db:
                db.execute(
                    update(BackupRequest)
                    .where(BackupRequest.id == self.request_id)
                    .values(safety_run_id=run_id)
                )
                db.commit()


def other_active_users(db, actor: str) -> int:
    """Users other than `actor` seen on the web in the last five minutes."""
    return db.execute(
        text(
            "SELECT count(*) FROM ops.app_user WHERE username <> :actor "
            "AND last_seen_at > now() - make_interval(secs => :secs)"
        ),
        {"actor": actor, "secs": ACTIVE_USER_WINDOW.total_seconds()},
    ).scalar_one()


def _other_active_users(ctx: Context, actor: str) -> int:
    with ctx.session_factory() as db:
        return other_active_users(db, actor)


def _wait_web(ctx: Context) -> None:
    service_control(ctx, "start")


def production(
    ctx: Context,
    target: str,
    actor: str,
    force: bool = False,
    request_id: int | None = None,
) -> Result:
    """Restore the running system from `target`; the caller holds the backup lock."""
    progress = _Progress(ctx, request_id)
    write_status(
        ctx,
        state="running",
        step="Chuẩn bị",
        target=target,
        actor=actor,
        request_id=request_id,
        started_at=datetime.now(UTC).isoformat(),
        finished_at=None,
        result=None,
        message=None,
        safety_run_id=None,
        banner_shown_by=None,
    )
    try:
        return _production(ctx, target, actor, force, progress)
    except RestoreRefused as exc:
        write_status(
            ctx,
            state="failed",
            step=None,
            message=str(exc),
            result="failed",
            finished_at=datetime.now(UTC).isoformat(),
        )
        raise


def _production(ctx, target, actor, force, progress: _Progress) -> Result:
    settings = ctx.settings
    if maintenance.active(settings, "deploy") or maintenance.active(settings, "migration"):
        raise RestoreRefused("Đang có triển khai hoặc chuyển máy chạy; thử lại sau")
    progress("Mở và kiểm tra bản sao lưu")
    archive_path = fetch(ctx, target)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    with staging.staging_dir(settings.backup_work_dir, "restore") as work:
        prep = prepare(ctx, archive_path, work)
        if prep.dump is None:
            raise RestoreRefused("Bản Ứng dụng không có database; chọn bản Database hoặc Toàn bộ")
        if prep.manifest is not None:
            check_version(ctx, prep.manifest)
        elif not force:
            raise RestoreRefused(
                "Bản sao lưu cũ không có manifest nên không kiểm được phiên bản và số dòng "
                "trước khi phục hồi; diễn tập trước, hoặc chạy lại với --force"
            )
        others = _other_active_users(ctx, actor)
        if others and not force:
            raise RestoreRefused(f"Có {others} người dùng khác đang dùng web; cần --force")
        maintenance.write(settings, "restore")
        services_stopped = False
        try:
            progress("Dừng robot và web")
            service_control(ctx, "stop")
            services_stopped = True
            progress("Sao lưu an toàn trạng thái hiện tại")
            safety = runner.run_backup(ctx, "full", "safety", actor, False)
            if (
                safety.exit_code not in (runner.EXIT_OK, runner.EXIT_PARTIAL)
                or not safety.archive_path
            ):
                raise RestoreError("Không tạo được bản sao lưu an toàn nên không phục hồi")
            progress.safety(safety.run_id)
        except Exception as exc:
            if services_stopped:
                try:
                    service_control(ctx, "start")
                except RestoreError:
                    log.exception("Không bật lại được web/robot sau khi phục hồi dừng sớm")
            maintenance.clear(settings, "restore")
            write_status(
                ctx,
                state="failed",
                step=None,
                message=str(exc),
                result="failed",
                finished_at=datetime.now(UTC).isoformat(),
            )
            raise
        try:
            progress("Phục hồi dữ liệu")
            _apply(ctx, prep, work, stamp)
            progress("Bật web và robot")
            _wait_web(ctx)
        except Exception as exc:
            log.exception("Phục hồi lỗi, lùi về bản an toàn")
            return _roll_back(ctx, safety, work, stamp, progress, str(exc))
        maintenance.clear(settings, "restore")
        message = f"Đã phục hồi từ {archive_path.name}"
        write_status(
            ctx,
            state="done",
            step=None,
            result="done",
            message=message,
            finished_at=datetime.now(UTC).isoformat(),
        )
        return Result("done", message, safety.run_id)


def _roll_back(ctx, safety, work: Path, stamp: str, progress: _Progress, reason: str) -> Result:
    settings = ctx.settings
    progress("Lỗi, đang lùi về bản sao lưu an toàn")
    try:
        prep = prepare(ctx, safety.archive_path, work / "safety")
        _apply(ctx, prep, work, stamp + "-undo")
        service_control(ctx, "start")
    except Exception as exc:
        log.exception("Lùi về bản an toàn cũng lỗi")
        command = (
            f"uv run --no-dev --extra robot shoponline backup restore {safety.file_name} "
            "--production --force --yes"
        )
        message = (
            f"Phục hồi lỗi ({reason}) và lùi lại cũng lỗi ({exc}). Bản an toàn: "
            f"{safety.file_name}. Chạy tay: {command}"
        )
        write_status(
            ctx,
            state="failed",
            step=None,
            result="failed",
            message=message,
            finished_at=datetime.now(UTC).isoformat(),
        )
        return Result("failed", message, safety.run_id)
    maintenance.clear(settings, "restore")
    message = f"Phục hồi lỗi nên đã lùi về trạng thái trước đó. Lý do: {reason}"
    write_status(
        ctx,
        state="rolled_back",
        step=None,
        result="rolled_back",
        message=message,
        finished_at=datetime.now(UTC).isoformat(),
    )
    return Result("rolled_back", message, safety.run_id)


# --- queue handlers (registered with the runner) ---------------------------------------------


def _target_of(ctx: Context, req_id: int) -> tuple[str, str, bool]:
    with ctx.session_factory() as db:
        req = db.get(BackupRequest, req_id)
        if req.target_run_id is None:
            raise RestoreRefused("Yêu cầu không chỉ bản sao lưu nào")
        return str(req.target_run_id), req.requested_by, req.to_drive


def _handle_drill(ctx: Context, req_id: int):
    target, _actor, _ = _target_of(ctx, req_id)
    path = fetch(ctx, target)
    with staging.staging_dir(ctx.settings.backup_work_dir, "drill") as work:
        prep = prepare(ctx, path, work)
        result = drill(ctx, prep)
    if result["ok"]:
        return "done", "Diễn tập khớp số dòng", result, runner.EXIT_OK
    return "failed", "Diễn tập: số dòng lệch so với manifest", result, runner.EXIT_NONE


def _handle_verify(ctx: Context, req_id: int):
    target, _actor, _ = _target_of(ctx, req_id)
    ok, message = verify.verify(ctx, verify.locate(ctx, target))
    return (
        ("done" if ok else "failed"),
        message,
        {"ok": ok},
        (runner.EXIT_OK if ok else runner.EXIT_NONE),
    )


def _handle_restore(ctx: Context, req_id: int):
    target, actor, _ = _target_of(ctx, req_id)
    with ctx.session_factory() as db:
        # The web (or whoever enqueued the request) sets result={"force": true} to override
        # the "other users are active" and "backup without manifest" refusals.
        force = bool((db.get(BackupRequest, req_id).result or {}).get("force"))
    try:
        result = production(ctx, target, actor, force=force, request_id=req_id)
    except RestoreRefused as exc:
        return "failed", str(exc), None, runner.EXIT_NONE
    code = runner.EXIT_OK if result.status == "done" else runner.EXIT_NONE
    return result.status, result.message, None, code


def expire_stale_restores(ctx: Context) -> int:
    """A restore asked for long ago must not start when the task finally runs."""
    cutoff = datetime.now(UTC) - RESTORE_REQUEST_MAX_AGE
    with ctx.session_factory() as db:
        count = db.execute(
            update(BackupRequest)
            .where(
                BackupRequest.action == "restore",
                BackupRequest.status == "pending",
                BackupRequest.requested_at < cutoff,
            )
            .values(
                status="expired",
                finished_at=datetime.now(UTC),
                message="Yêu cầu quá cũ, không chạy",
            )
        ).rowcount
        db.commit()
    return count


runner.HANDLERS.update(
    {"drill": _handle_drill, "verify": _handle_verify, "restore": _handle_restore}
)
