"""Local catalog workspace operations, using the existing search and image APIs."""

from contextlib import closing

from .artwork_downloads import image_url
from .bulk_install import cancelled


def artwork_faces(payload):
    faces = payload.get("card_faces") or []
    indexes = range(len(faces)) if any(f.get("image_uris") for f in faces) else range(1)
    return [i for i in indexes if image_url(payload, i)]


def missing_artwork(service, row):
    return any(
        not service.get_image_path(row.card_id, "default" if i == 0 else f"face-{i}")
        for i in artwork_faces(row.payload)
    )


class CatalogWorkspace:
    PAGE_SIZE = 60

    def __init__(self, service):
        self.service = service

    def page(
        self,
        query="",
        *,
        offset=0,
        unique=True,
        set_filter="",
        missing=False,
        oracle_ids=None,
        cancel,
    ):
        # A bounded source page keeps even a sparse missing-artwork search responsive.
        rows = self.service.database.search_syntax(
            query,
            limit=self.PAGE_SIZE + 1,
            offset=offset,
            unique=unique,
            set_filter=set_filter,
            oracle_ids=oracle_ids,
            should_cancel=cancel.is_set,
        )
        more = len(rows) > self.PAGE_SIZE
        rows = rows[: self.PAGE_SIZE]
        if missing:
            result = []
            for row in rows:
                cancelled(cancel)
                if missing_artwork(self.service, row):
                    result.append(row)
            rows = result
        return rows, offset + self.PAGE_SIZE, more

    def overview(self, cancel):
        cancelled(cancel)
        with closing(self.service.database.connect()) as db:
            return tuple(
                db.execute(
                    "SELECT (SELECT count(*) FROM cards_oracle), (SELECT count(*) FROM prints)"
                ).fetchone()
            )

    def download(self, rows, *, cancel, report):
        failures = []
        for index, row in enumerate(rows):
            cancelled(cancel)
            for face in artwork_faces(row.payload):
                cancelled(cancel)
                report(
                    dict(
                        operation=f"Artwork: {row.name} · face {face + 1}",
                        current=index,
                        total=len(rows),
                        unit="printings",
                    )
                )
                try:

                    def transfer(progress):
                        report(
                            dict(
                                operation=f"Artwork: {row.name} · face {face + 1}",
                                current=progress.downloaded,
                                total=progress.total,
                                speed=progress.bytes_per_second,
                                remaining=progress.remaining_seconds,
                                unit="bytes",
                            )
                        )

                    self.service.cache_artwork(
                        row.card_id,
                        face,
                        cancel=cancel,
                        refresh=True,
                        progress=transfer,
                    )
                except (OSError, ValueError) as exc:
                    failures.append(
                        f"{row.name} · {row.card_id} · face {face + 1}: {exc}"
                    )
            report(
                dict(
                    operation="Selected artwork",
                    current=index + 1,
                    total=len(rows),
                    unit="printings",
                    failed=len(failures),
                )
            )
        if failures:
            raise ValueError("\n".join(failures))
        return len(rows)

    def download_query(
        self, query, *, unique, set_filter, missing, cancel, report, oracle_ids=None
    ):
        offset = 0
        while True:
            rows, offset, more = self.page(
                query,
                offset=offset,
                unique=unique,
                set_filter=set_filter,
                missing=missing,
                oracle_ids=oracle_ids,
                cancel=cancel,
            )
            self.download(rows, cancel=cancel, report=report)
            if not more:
                break
