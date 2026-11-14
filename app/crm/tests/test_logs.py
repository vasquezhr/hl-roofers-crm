"""The error log and the change log, and the health check (free disk space and memory)."""
import logging
import shutil
import tempfile
from collections import namedtuple
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from crm import automations, health, importer, logs, pricebook
from crm.models import Activity, Attachment, Company, HealthReading, Lead, Note, User, log

from .base import Base
from .test_files import photo
from .test_import import EVERYTHING, FENWICK, WYCKOFF, export
from .test_prices import NOVEMBER, sheet

GB = 1024 ** 3
Usage = namedtuple("Usage", "total used free")
Memory = namedtuple("Memory", "total available")


def disk(free_gb, total_gb=100):
    return Usage(total_gb * GB, (total_gb - free_gb) * GB, free_gb * GB)


class ChangeLog(Base):
    """Every history line is also one line in changes.log."""

    def test_a_history_line_is_written_with_who_the_record_and_what(self):
        job = self.job(self.crew1, "scheduled")
        with self.assertLogs("crm.changes", "INFO") as seen:
            log(job, "started", self.login1)
            log(self.account, "edited", self.office, detail='{"model": "account", "name": "", "fields": [["name", "Denise Wyckoff", "Denise W. Wyckoff"]]}')
        self.assertEqual(seen.records[0].getMessage(), f"who=Crew 1 record=job {job.number} kind=started | Job started")
        self.assertEqual(seen.records[1].getMessage(), f"who=office record=account {self.account.pk} kind=edited | Changed: Name: Denise Wyckoff → Denise W. Wyckoff")

    def test_a_change_to_the_setup_has_no_record(self):
        with self.assertLogs("crm.changes", "INFO") as seen:
            log(None, "type_added", self.admin, detail="Solar panels")
        self.assertEqual(seen.records[0].getMessage(), "who=admin record=setup kind=type_added | Type of work added: Solar panels")

    def test_a_password_is_never_in_the_log(self):
        self.sign_in(self.admin)
        with self.assertLogs("crm.changes", "INFO") as seen:
            self.client.post(reverse("user_edit", args=[self.office.pk]), {
                "username": "office", "first_name": "", "email": "", "profile": "office", "crew": "", "is_active": "on", "new_password": "a-secret-never-logged-9"})
        text = "\n".join(record.getMessage() for record in seen.records)
        self.assertIn("Password changed for office", text)
        self.assertNotIn("a-secret-never-logged-9", text)

    def test_what_a_note_says_is_not_copied(self):
        job = self.job(self.crew1, "scheduled")
        with self.assertLogs("crm.changes", "INFO") as seen:
            log(job, "note", self.login1, detail="the gate code is 4471")
        self.assertNotIn("4471", seen.records[0].getMessage())
        self.assertIn("kind=note", seen.records[0].getMessage())
        self.assertEqual(Activity.objects.get(kind="note").detail, "the gate code is 4471")        # the history itself is whole


class LogFiles(Base):
    def test_the_two_files_and_their_size(self):
        handlers = settings.LOGGING["handlers"]
        self.assertTrue(handlers["errors"]["filename"].endswith("errors.log"))
        self.assertTrue(handlers["changes"]["filename"].endswith("changes.log"))
        self.assertEqual((handlers["errors"]["level"], handlers["changes"]["level"]), ("WARNING", "INFO"))
        handler = logs.QuietRotatingFileHandler("unused.log")
        self.assertEqual((handler.maxBytes, handler.backupCount), (5 * 1024 * 1024, 10))
        self.assertIn("errors", settings.LOGGING["root"]["handlers"])
        self.assertIn("console", settings.LOGGING["root"]["handlers"])                      # still printed on the PC

    def test_a_line_has_the_date_the_time_the_level_the_logger_and_the_message(self):
        folder = Path(tempfile.mkdtemp(prefix="crm-log-test-"))
        self.addCleanup(shutil.rmtree, folder, True)
        handler = logs.QuietRotatingFileHandler(str(folder / "errors.log"))
        handler.setFormatter(logging.Formatter(settings.LOGGING["formatters"]["line"]["format"], settings.LOGGING["formatters"]["line"]["datefmt"]))
        handler.setLevel(logging.WARNING)
        try:
            self.assertFalse((folder / "errors.log").exists())                               # nothing is created until a line is written
            logger = logging.getLogger("crm.somewhere")
            logger.addHandler(handler)
            try:
                logger.info("not written")
                logger.warning("something went wrong: %s", "a reason")
                try:
                    1 / 0
                except ZeroDivisionError:
                    logger.exception("with a traceback")
            finally:
                logger.removeHandler(handler)
        finally:
            handler.close()
        lines = (folder / "errors.log").read_text(encoding="utf-8").splitlines()
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d WARNING crm\.somewhere something went wrong: a reason$")
        self.assertIn("ERROR crm.somewhere with a traceback", lines[1])
        self.assertTrue(any("ZeroDivisionError" in line for line in lines))
        self.assertEqual(len([line for line in lines if "not written" in line]), 0)

    def test_a_rollover_that_windows_refuses_does_not_stop_the_log(self):
        folder = Path(tempfile.mkdtemp(prefix="crm-log-test-"))
        self.addCleanup(shutil.rmtree, folder, True)
        handler = logs.QuietRotatingFileHandler(str(folder / "errors.log"), maxBytes=50)
        try:
            with mock.patch("logging.handlers.RotatingFileHandler.rotate", side_effect=PermissionError("in use by another program")):
                for n in range(4):
                    handler.emit(logging.LogRecord("crm", logging.WARNING, "x", 1, "a line that is longer than fifty bytes, number %s", (n,), None))
        finally:
            handler.close()
        self.assertEqual(len((folder / "errors.log").read_text(encoding="utf-8").splitlines()), 4)

    def test_tail_reads_the_end_of_a_big_file(self):
        folder = Path(tempfile.mkdtemp(prefix="crm-log-test-"))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "errors.log").write_text("".join(f"line {n}\n" for n in range(1, 30001)), encoding="utf-8")
        found = logs.tail(folder / "errors.log", 50)
        self.assertEqual((len(found), found[0], found[-1]), (50, "line 29951", "line 30000"))
        self.assertEqual(logs.tail(folder / "missing.log"), [])


class Failures(Base):
    """What went wrong is written to errors.log: what, who, which file or row, and why."""

    def setUp(self):
        self.sign_in(self.admin)

    def test_a_notes_file_that_cannot_be_read(self):
        with self.assertLogs("crm", "WARNING") as seen:
            page = self.client.post(f"{reverse('data_import')}?kind=notes", {"file": SimpleUploadedFile("broken.json", b"not json at all"), "skip_folders": ""})
        self.assertContains(page, "This file could not be read")
        line = seen.records[0].getMessage()
        self.assertIn("'broken.json'", line)
        self.assertIn("by admin", line)
        self.assertIn("JSONDecodeError", line)

    def test_one_note_that_fails_leaves_the_others_and_the_log_says_which(self):
        real = importer.read_note
        calls = []

        def read_note(text):
            calls.append(text)
            if len(calls) == 2:
                raise ValueError("a note the reader could not understand")
            return real(text)
        with mock.patch.object(importer, "read_note", side_effect=read_note):
            with self.assertLogs("crm", "WARNING") as seen:
                batch = importer.import_file(export(FENWICK, WYCKOFF, EVERYTHING[3]), self.admin)
        self.assertEqual(batch.unreadable, 1)
        self.assertEqual(batch.notes.count(), 2)
        first, last = seen.records[0], seen.records[-1]
        self.assertEqual(first.levelname, "ERROR")
        self.assertIn("note number 2 of 'notes.json'", first.getMessage())
        self.assertIsNotNone(first.exc_info)                                                  # with the traceback
        self.assertIn("1 of 3 notes", last.getMessage())
        for record in seen.records:
            self.assertNotIn("Denise", record.getMessage())                                   # a note's words are never in the log

    def test_the_view_tells_the_administrator_when_notes_were_left_out(self):
        with mock.patch.object(importer, "read_note", side_effect=ValueError("bad")):
            with self.assertLogs("crm", "WARNING"):
                page = self.client.post(f"{reverse('data_import')}?kind=notes", {"file": export(FENWICK), "skip_folders": ""}, follow=True)
        self.assertContains(page, "1 notes could not be read and were left out")

    def test_an_unexpected_failure_of_the_whole_import(self):
        with mock.patch.object(importer, "import_file", side_effect=RuntimeError("the database went away")):
            with self.assertLogs("crm", "ERROR") as seen:
                page = self.client.post(f"{reverse('data_import')}?kind=notes", {"file": export(FENWICK), "skip_folders": ""})
        self.assertContains(page, "The import failed and nothing was added")
        self.assertIn("RuntimeError: the database went away", "\n".join(seen.output))

    def test_a_note_that_cannot_be_accepted_stays_in_the_queue(self):
        batch = importer.import_file(export(FENWICK), self.admin)
        note = batch.notes.get()
        with mock.patch.object(importer, "accept", side_effect=RuntimeError("disk full")):
            with self.assertLogs("crm", "ERROR") as seen:
                page = self.client.post(reverse("import_queue"), {"do": "accept", "which": "ticked", "note": [note.pk]}, follow=True)
        self.assertContains(page, "1 notes could not be changed and are still in the list")
        self.assertIn(f"note {note.pk} could not be added to a customer, by admin", seen.records[0].getMessage())
        note.refresh_from_db()
        self.assertEqual(note.status, "pending")

    def test_a_price_file_that_cannot_be_read_and_rows_that_are_left_out(self):
        with self.assertLogs("crm", "WARNING") as seen:
            self.client.post(reverse("price_upload"), {"file": SimpleUploadedFile("notes.xlsx", b"nope"), "supplier": "ABC Supply", "line": "GAF HDZ"})
        self.assertIn("'notes.xlsx' could not be read as an Excel file", seen.records[0].getMessage())
        self.assertIn("uploaded by admin", seen.records[0].getMessage())
        rows = [["Code", "Item", "Unit", "Cost", "Price"], ["A-1", "Shingles", "bundle", 38, 46], ["A-1", "Shingles again", "bundle", 39, 47],
                ["B-2", "Ridge cap", "bundle", "ask", 75], ["", "Subtotal", "", "", ""]]
        with self.assertLogs("crm", "WARNING") as seen:
            found = pricebook.read_price_file(sheet(*rows, name="abc.xlsx"), "admin")
        self.assertEqual([row["code"] for row in found], ["A-1"])
        lines = [record.getMessage() for record in seen.records]
        self.assertEqual(len(lines), 2)                                                       # the subtotal is not a problem
        self.assertIn("'abc.xlsx', row 3 left out: the code A-1 is already used", lines[0])
        self.assertIn("'abc.xlsx', row 4 left out: the cost or the price is missing", lines[1])

    def test_prices_that_cannot_be_saved(self):
        self.client.post(reverse("price_upload"), {"file": sheet(*NOVEMBER), "supplier": "ABC Supply", "line": "GAF HDZ"})
        with mock.patch.object(pricebook, "apply", side_effect=RuntimeError("disk full")):
            with self.assertLogs("crm", "ERROR") as seen:
                page = self.client.post(reverse("price_review"), follow=True)
        self.assertContains(page, "The prices could not be saved and nothing was changed")
        self.assertIn("'prices.xlsx' (ABC Supply, GAF HDZ) could not be applied, by admin", seen.records[0].getMessage())

    def test_a_refused_photo_and_a_photo_that_cannot_be_saved(self):
        job = self.job(self.crew1, "scheduled")
        add = reverse("job_files", args=[job.number])
        with self.assertLogs("crm", "WARNING") as seen:
            self.client.post(add, {"files": [SimpleUploadedFile("run.exe", b"MZ not a photo")], "category": "before"})
        self.assertIn(f"File refused: 'run.exe' is not a photo or a PDF (job {job.number}, by admin)", seen.records[0].getMessage())
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            with mock.patch("django.core.files.storage.FileSystemStorage._save", side_effect=OSError("There is not enough space on the disk")):
                with self.assertLogs("crm", "ERROR") as seen:
                    page = self.client.post(add, {"files": [photo()], "category": "before"}, follow=True)
        self.assertContains(page, "could not be saved. The reason is in the error log")
        self.assertIn(f"File could not be saved: 'IMG_1234.jpg'", seen.records[0].getMessage())
        self.assertIn(f"job {job.number}, by admin", seen.records[0].getMessage())
        self.assertIn("not enough space", seen.output[0])
        self.assertEqual(Attachment.objects.count(), 0)

    def test_the_data_editor_logs_a_change_it_left_out_and_a_save_that_failed(self):
        from crm import admin_views
        found = [{"account": self.account.pk, "name": "Denise Wyckoff", "field": "phone", "old": "(804) 555-0000", "new": "(804) 555-0199"}]
        with self.assertLogs("crm", "WARNING") as seen:
            self.assertEqual(admin_views.write_changes(found, self.admin), [])                # the phone is not what the editor saw
        self.assertIn(f"the change of phone on account {self.account.pk} left out", seen.records[0].getMessage())
        self.assertNotIn("555", seen.records[0].getMessage())                                 # never the values
        from django.core import signing
        packed = signing.dumps(found)
        with mock.patch.object(admin_views, "write_changes", side_effect=RuntimeError("deadlock")):
            with self.assertLogs("crm", "ERROR") as seen:
                page = self.client.post(reverse("editor"), {"step": "confirm", "packed": packed}, follow=True)
        self.assertContains(page, "The changes could not be saved and nothing was changed")
        self.assertIn("saving 1 changes failed, nothing was saved (by admin)", seen.records[0].getMessage())

    def test_email_that_cannot_be_sent_and_email_that_is_not_set_up(self):
        from crm.mail import send
        with override_settings(EMAIL_READY=True), mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("connection refused")):
            with self.assertLogs("crm", "ERROR") as seen:
                self.assertFalse(send("dwyckoff@example.com", "Your proposal", "text", ("proposal.pdf", b"%PDF")))
        self.assertIn("to=dwyckoff@example.com subject='Your proposal' attachment=proposal.pdf", seen.records[0].getMessage())
        self.assertIn("connection refused", "\n".join(seen.output))
        with override_settings(EMAIL_READY=False):
            with self.assertLogs("crm", "WARNING") as seen:
                self.assertFalse(send("dwyckoff@example.com", "Your proposal", "text"))
        self.assertIn("email is not set up", seen.records[0].getMessage())

    @override_settings(LEAD_FORM_KEY="form-key")
    def test_the_website_form_logs_what_it_refused_and_why(self):
        self.client.logout()
        with self.assertLogs("crm", "WARNING") as seen:
            self.client.post(reverse("lead_in"), {"key": "the-wrong-key", "name": "Mina Seo"})
            self.client.post(reverse("lead_in"), {"key": "form-key", "name": "", "phone": "(804) 555-0178"})
        wrong_key, wrong_fields = [record.getMessage() for record in seen.records]
        self.assertIn("the key is wrong or missing; from 127.0.0.1", wrong_key)
        self.assertNotIn("the-wrong-key", wrong_key)
        self.assertIn("wrong fields: name (required)", wrong_fields)
        self.assertNotIn("555", wrong_fields)                                                 # what a visitor typed is not copied
        with mock.patch.object(Lead, "save", side_effect=RuntimeError("database is locked")):
            with self.assertLogs("crm", "ERROR") as seen:
                answer = self.client.post(reverse("lead_in"), {"key": "form-key", "name": "Mina Seo", "phone": "(804) 555-0178", "message": "Shingles blew off."})
        self.assertEqual(answer.status_code, 500)
        self.assertEqual(answer.json()["ok"], False)
        self.assertIn("a request could not be saved", seen.records[0].getMessage())

    def test_one_part_of_tick_that_fails_does_not_stop_the_others(self):
        with mock.patch.object(automations, "mark_overdue", side_effect=RuntimeError("bad invoice")):
            with self.assertLogs("crm", "ERROR") as seen:
                done = automations.tick()
        self.assertEqual(done["overdue"], 0)
        self.assertIn("tick: overdue invoices failed", seen.records[0].getMessage())
        self.assertIn("RuntimeError: bad invoice", seen.output[0])
        self.assertIn("low", done)                                                            # the health check still ran
        self.assertIsNotNone(Company.load().last_tick_at)


@override_settings(EMAIL_READY=True, SITE_URL="https://app.example", DISK_MIN_GB=10, DISK_MIN_PERCENT=10, RAM_MIN_MB=500)
class Health(Base):
    def setUp(self):
        self.admin.email = "admin@example.com"
        self.admin.save()
        self.office.email = "office@example.com"
        self.office.save()
        self.now = timezone.now()

    def check(self, free_gb=50, ram_mb=4000, when=None, total_gb=100):
        with mock.patch.object(health.shutil, "disk_usage", return_value=disk(free_gb, total_gb)), \
                mock.patch.object(health.psutil, "virtual_memory", return_value=Memory(8000 * 1024 ** 2, ram_mb * 1024 ** 2)), \
                mock.patch.object(health, "folders", return_value=[("database", "/data/db"), ("photos and files", "/data/media"), ("logs", "/data/logs")]), \
                mock.patch.object(health, "existing", side_effect=lambda folder: folder), \
                mock.patch.object(health, "drive_of", side_effect=lambda folder: folder.rsplit("/", 1)[0]):
            return health.check(when or self.now)

    def test_a_healthy_machine_is_stored_and_not_reported(self):
        with self.assertNoLogs("crm", "WARNING"):
            self.assertEqual(self.check(), 0)
        disk_row, ram_row = HealthReading.objects.order_by("kind")
        self.assertEqual((disk_row.kind, disk_row.free_mb, disk_row.total_mb, disk_row.low), ("disk", 50 * 1024, 100 * 1024, False))
        self.assertEqual((ram_row.kind, ram_row.free_mb, ram_row.low), ("ram", 4000, False))
        self.assertEqual(disk_row.names, "database, photos and files, logs")                   # one drive, one reading
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(Activity.objects.filter(kind__in=["low_disk", "low_ram"]).exists())

    def test_low_disk_space_goes_to_the_log_the_setup_history_and_the_administrators(self):
        with self.assertLogs("crm", "WARNING") as seen:
            self.assertEqual(self.check(free_gb=4), 1)
        self.assertIn("Low disk space: /data", seen.records[0].getMessage())
        self.assertIn("4.0 GB free of 100.0 GB (4%)", seen.records[0].getMessage())
        line = Activity.objects.get(kind="low_disk")
        self.assertEqual((line.actor, line.job_id, line.account_id), ("Automation", None, None))
        self.assertIn("4.0 GB free", line.text)
        self.assertTrue(HealthReading.objects.get(kind="disk").low)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["admin@example.com"])                                    # the administrator, not the office
        self.assertIn("Low disk space", message.subject)
        self.assertIn("Poco espacio en disco", message.subject)                                # in English and in Spanish
        self.assertIn("/data", message.body)
        self.sign_in(self.admin)
        self.assertContains(self.client.get(reverse("admin_history")), "Low disk space: /data")   # on Admin > Setup history

    def test_the_percent_limit_counts_too(self):
        with self.assertLogs("crm", "WARNING"):
            self.assertEqual(self.check(free_gb=20, total_gb=500), 1)                          # 20 GB is enough, but it is 4% of the drive

    def test_low_memory(self):
        with self.assertLogs("crm", "WARNING") as seen:
            self.assertEqual(self.check(ram_mb=300), 1)
        self.assertIn("Low memory (RAM): ", seen.records[0].getMessage())
        self.assertIn("300 MB free of 7.8 GB", seen.records[0].getMessage())
        self.assertEqual(Activity.objects.get(kind="low_ram").actor, "Automation")
        self.assertIn("low on memory", mail.outbox[0].body)

    @override_settings(RAM_MIN_MB=5000)
    def test_the_limits_come_from_the_settings(self):
        with self.assertLogs("crm", "WARNING"):
            self.assertEqual(self.check(ram_mb=4000), 1)

    def test_a_problem_is_reported_once_a_day(self):
        with self.assertLogs("crm", "WARNING"):
            self.check(free_gb=4)
        with self.assertNoLogs("crm", "WARNING"):
            self.assertEqual(self.check(free_gb=4, when=self.now + timedelta(minutes=15)), 1)     # still low: counted, not reported again
            self.check(free_gb=4, when=self.now + timedelta(hours=23))
        self.assertEqual((Activity.objects.filter(kind="low_disk").count(), len(mail.outbox)), (1, 1))
        self.assertEqual(HealthReading.objects.filter(kind="disk").count(), 3)                 # but every reading is kept
        with self.assertLogs("crm", "WARNING"):
            self.check(free_gb=4, when=self.now + timedelta(hours=25))
        self.assertEqual((Activity.objects.filter(kind="low_disk").count(), len(mail.outbox)), (2, 2))

    def test_disk_and_memory_are_separate_problems(self):
        with self.assertLogs("crm", "WARNING"):
            self.assertEqual(self.check(free_gb=4, ram_mb=300), 2)
        self.assertEqual(len(mail.outbox), 2)
        with self.assertNoLogs("crm", "WARNING"):
            self.check(free_gb=4, ram_mb=300, when=self.now + timedelta(hours=1))               # nothing new
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(EMAIL_READY=False)
    def test_without_email_the_line_and_the_log_still_happen(self):
        with self.assertLogs("crm", "WARNING"):
            self.check(free_gb=4)
        self.assertEqual((Activity.objects.filter(kind="low_disk").count(), len(mail.outbox)), (1, 0))

    def test_old_readings_are_deleted(self):
        self.check(when=self.now - timedelta(days=20))
        self.check()
        self.assertEqual(HealthReading.objects.filter(taken_at__lt=self.now - timedelta(days=14)).count(), 0)
        self.assertEqual(HealthReading.objects.count(), 2)

    def test_a_drive_that_cannot_be_read_is_logged(self):
        with mock.patch.object(health.shutil, "disk_usage", side_effect=OSError("the drive is not ready")):
            with self.assertLogs("crm", "ERROR") as seen:
                readings = health.disk_readings()
        self.assertEqual(readings, [])
        self.assertIn("could not be read", seen.records[0].getMessage())

    def test_tick_runs_the_check_and_the_command_prints_it(self):
        out = StringIO()
        call_command("tick", stdout=out)
        self.assertIn("low 0", out.getvalue())
        self.assertTrue(HealthReading.objects.filter(kind="ram").exists())

    def test_the_real_machine_can_be_read(self):
        self.assertTrue(health.disk_readings())
        self.assertGreater(health.ram_reading()["total_mb"], 0)


class StatusPage(Base):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="crm-log-test-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.override = override_settings(LOG_DIR=Path(self.folder))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.sign_in(self.admin)

    def test_the_latest_readings_when_they_were_taken_and_a_problem_in_red(self):
        page = self.client.get(reverse("status"))
        self.assertContains(page, "No reading yet.")
        old = timezone.now() - timedelta(hours=2)
        HealthReading.objects.create(kind="disk", place="C:\\crm", names="database, logs", free_mb=80 * 1024, total_mb=100 * 1024, taken_at=old)
        HealthReading.objects.create(kind="disk", place="C:\\crm", names="database, logs", free_mb=4 * 1024, total_mb=100 * 1024, low=True)
        HealthReading.objects.create(kind="ram", place="memory", free_mb=4000, total_mb=8000)
        page = self.client.get(reverse("status"))
        self.assertEqual([reading.free_mb for reading in page.context["readings"]], [4 * 1024, 4000])        # the newest of each
        self.assertContains(page, "Disk space: C:\\crm (database, logs)")
        self.assertContains(page, "4.0 GB free of 100.0 GB (4%)")
        self.assertContains(page, "Memory (RAM)")
        self.assertContains(page, "list-group-item d-flex gap-2 align-items-start px-0 text-danger")     # the problem is red
        self.assertContains(page, "Low")
        self.assertContains(self.client.get(reverse("dashboard")), "Disk space and memory")

    def test_the_error_log_shows_its_last_50_lines_and_the_downloads(self):
        page = self.client.get(reverse("status"))
        self.assertContains(page, "Nothing has been written to the error log yet.")
        self.assertNotContains(page, "Download errors.log")                                  # no file yet
        Path(self.folder, "errors.log").write_text("".join(f"2026-11-13 10:00:{n % 60:02d} WARNING crm.test line number {n}\n" for n in range(1, 71)), encoding="utf-8")
        Path(self.folder, "changes.log").write_text("2026-11-13 10:00:00 INFO crm.changes who=admin record=setup kind=type_added | x\n", encoding="utf-8")
        page = self.client.get(reverse("status"))
        self.assertContains(page, "line number 70")
        self.assertContains(page, "line number 21")
        self.assertNotContains(page, "line number 20\n")
        self.assertContains(page, reverse("log_download", args=["errors"]))
        self.assertContains(page, reverse("log_download", args=["changes"]))
        errors = self.client.get(reverse("log_download", args=["errors"]))
        self.assertEqual(errors["Content-Disposition"], 'attachment; filename="errors.log"')
        self.assertIn(b"line number 1\n", b"".join(errors.streaming_content))
        self.assertIn(b"kind=type_added", b"".join(self.client.get(reverse("log_download", args=["changes"])).streaming_content))

    def test_a_log_line_is_shown_as_text_never_as_html(self):
        Path(self.folder, "errors.log").write_text("2026-11-13 10:00:00 WARNING crm.test <script>alert(1)</script>\n", encoding="utf-8")
        page = self.client.get(reverse("status"))
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;")

    def test_only_the_administrator_and_only_the_two_files(self):
        Path(self.folder, "errors.log").write_text("a line\n", encoding="utf-8")
        Path(self.folder, "secret.log").write_text("not for download\n", encoding="utf-8")
        self.assertEqual(self.client.get(reverse("log_download", args=["secret"])).status_code, 404)
        self.assertEqual(self.client.get("/manage/logs/..%2Ferrors.log").status_code, 404)
        self.assertEqual(self.client.get(reverse("log_download", args=["changes"])).status_code, 404)    # there is no such file yet
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertEqual(self.client.get(reverse("log_download", args=["errors"])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("log_download", args=["errors"])).status_code, 302)      # to the sign-in page
