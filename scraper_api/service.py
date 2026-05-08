import asyncio
import html
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, unquote

import httpx
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


_NON_ALPHANUM_RE = re.compile(r"[^a-z0-9_]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def url_to_folder_path(raw_url: str) -> Path:
    """Map a URL path to the same sanitized folder shape as the old Go scraper."""
    parsed = urlparse(raw_url)
    path = parsed.path.strip("/")
    if not path:
        return Path("index")

    segments = []
    for segment in path.split("/"):
        if not segment:
            continue
        clean = segment.lower().replace("-", "_")
        clean = _NON_ALPHANUM_RE.sub("_", clean).strip("_")
        if clean:
            segments.append(clean)

    if not segments:
        return Path("index")
    return Path(*segments)


def url_to_abs_folder(raw_url: str, output_dir: str, site_folder: str) -> Path:
    return Path(output_dir) / safe_site_folder(site_folder) / url_to_folder_path(raw_url)


def safe_site_folder(site_folder: str) -> Path:
    """Keep user-provided folder names relative and traversal-free."""
    parts = []
    for part in re.split(r"[\\/]+", site_folder):
        clean = part.strip()
        if not clean or clean in {".", ".."}:
            continue
        parts.append(clean)
    if not parts:
        raise ValueError("folder must contain at least one safe path segment")
    return Path(*parts)


def sanitize_pdf_filename(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    filename = Path(unquote(parsed.path)).name
    if not filename or filename == ".":
        return "document.pdf"

    cleaned = "".join("_" if char.isspace() else char for char in filename)
    return cleaned or "document.pdf"


def is_pdf_url(raw_url: str) -> bool:
    return urlparse(raw_url).path.lower().endswith(".pdf")


def is_allowed_path(raw_url: str, allowed_paths: List[str]) -> bool:
    if not allowed_paths:
        return True
    path = urlparse(raw_url).path
    return any(path.startswith(prefix) for prefix in allowed_paths)


def is_same_domain(raw_url: str, domain: str) -> bool:
    return (urlparse(raw_url).hostname or "").lower() == domain.lower()


def matches_disallowed(raw_url: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        try:
            if re.search(pattern, raw_url):
                return True
        except re.error:
            logger.warning("Ignoring invalid disallowed path regex: %s", pattern)
    return False


def inject_source_url_meta(body: bytes, source_url: str) -> bytes:
    tag = (
        '<meta name="source-url" content="'
        + html.escape(source_url, quote=True)
        + '">'
    )
    text = body.decode("utf-8", errors="replace")
    lower = text.lower()
    if "</head>" in lower:
        index = lower.index("</head>")
        text = text[:index] + "\n" + tag + "\n" + text[index:]
    elif "<head>" in lower:
        index = lower.index("<head>") + len("<head>")
        text = text[:index] + "\n" + tag + text[index:]
    else:
        text = tag + "\n" + text
    return text.encode("utf-8")


@dataclass
class ScrapeConfig:
    domain: str
    folder: str
    seeds: List[str]
    allowed_paths: List[str] = field(default_factory=list)
    disallowed_paths: List[str] = field(default_factory=list)
    max_depth: int = 3
    max_parallelism: int = 2
    rate_limit_ms: int = 1000
    user_agent: str = "UI-RAG-Scraper/1.0"
    skip_existing: bool = False
    dry_run: bool = False
    output_dir: str = "/app/data"

    def normalized(self) -> "ScrapeConfig":
        if not self.domain.strip():
            raise ValueError("domain is required")
        seeds = [seed.strip() for seed in self.seeds if seed.strip()]
        if not seeds:
            raise ValueError("at least one seed URL is required")
        safe_site_folder(self.folder)
        return ScrapeConfig(
            domain=self.domain.strip().lower(),
            folder=self.folder,
            seeds=seeds,
            allowed_paths=list(self.allowed_paths or []),
            disallowed_paths=list(self.disallowed_paths or []),
            max_depth=max(1, self.max_depth),
            max_parallelism=max(1, self.max_parallelism),
            rate_limit_ms=max(0, self.rate_limit_ms),
            user_agent=self.user_agent or "UI-RAG-Scraper/1.0",
            skip_existing=bool(self.skip_existing),
            dry_run=bool(self.dry_run),
            output_dir=self.output_dir or "/app/data",
        )


@dataclass
class ScrapeJob:
    job_id: str
    config: ScrapeConfig
    status: str = "queued"
    pages_visited: int = 0
    pdfs_downloaded: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    current_url: Optional[str] = None
    started_at: str = field(default_factory=_utc_now_iso)
    finished_at: Optional[str] = None
    output_dir: str = ""
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "pages_visited": self.pages_visited,
            "pdfs_downloaded": self.pdfs_downloaded,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "current_url": self.current_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "output_dir": self.output_dir,
            "dry_run": self.dry_run,
            "domain": self.config.domain,
            "folder": self.config.folder,
        }

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]


class _AsyncRateLimiter:
    def __init__(self, delay_ms: int):
        self.delay = delay_ms / 1000
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self) -> None:
        if self.delay <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            if self._next_at > now:
                await asyncio.sleep(self._next_at - now)
            self._next_at = time.monotonic() + self.delay


class ScraperJobManager:
    def __init__(self, logger_: Optional[logging.Logger] = None):
        self.jobs: Dict[str, ScrapeJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._logger = logger_ or logger

    def start_job(self, config: ScrapeConfig) -> Dict[str, Any]:
        normalized = config.normalized()
        active = [
            job
            for job in self.jobs.values()
            if job.status in {"queued", "running"}
        ]
        if active:
            raise RuntimeError(f"scrape job already active: {active[0].job_id}")

        job_id = uuid.uuid4().hex
        job = ScrapeJob(
            job_id=job_id,
            config=normalized,
            output_dir=str(Path(normalized.output_dir) / safe_site_folder(normalized.folder)),
            dry_run=normalized.dry_run,
        )
        self.jobs[job_id] = job
        self._tasks[job_id] = asyncio.create_task(self._run_job(job))
        return job.to_dict()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(job_id)
        return job.to_dict() if job else None

    def cancel_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(job_id)
        if not job:
            return None
        task = self._tasks.get(job_id)
        if task and not task.done():
            job.status = "cancelling"
            task.cancel()
        return job.to_dict()

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_job(self, job: ScrapeJob) -> None:
        job.status = "running"
        try:
            await self._crawl(job)
            job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except Exception as exc:
            job.status = "failed"
            job.add_error(str(exc))
            self._logger.exception("Scrape job failed: %s", job.job_id)
        finally:
            job.finished_at = _utc_now_iso()

    async def _crawl(self, job: ScrapeJob) -> None:
        config = job.config
        queue: asyncio.Queue[Optional[Tuple[str, int, str]]] = asyncio.Queue()
        visited: Set[str] = set()

        for seed in config.seeds:
            if not is_same_domain(seed, config.domain):
                job.add_error(f"seed skipped because it is outside domain: {seed}")
                continue
            if matches_disallowed(seed, config.disallowed_paths):
                job.add_error(f"seed skipped because it matches disallowed_paths: {seed}")
                continue
            await queue.put((seed, 1, seed))

        if queue.empty():
            raise ValueError("no valid seed URLs remain after domain/disallowed checks")

        rate_limiter = _AsyncRateLimiter(config.rate_limit_ms)
        limits = httpx.Limits(max_connections=config.max_parallelism)
        headers = {"User-Agent": config.user_agent}

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=90.0,
            limits=limits,
            headers=headers,
        ) as client:
            workers = [
                asyncio.create_task(
                    self._worker(job, client, queue, visited, rate_limiter)
                )
                for _ in range(config.max_parallelism)
            ]
            await queue.join()
            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers)

    async def _worker(
        self,
        job: ScrapeJob,
        client: httpx.AsyncClient,
        queue: asyncio.Queue,
        visited: Set[str],
        rate_limiter: _AsyncRateLimiter,
    ) -> None:
        config = job.config
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                raw_url, depth, referring_page = item
                if raw_url in visited:
                    job.skipped += 1
                    continue
                visited.add(raw_url)
                job.current_url = raw_url

                await rate_limiter.wait()
                try:
                    response = await client.get(raw_url)
                except Exception as exc:
                    job.add_error(f"fetch failed {raw_url}: {exc}")
                    continue

                content_type = response.headers.get("content-type", "")
                final_url = str(response.url)
                if not is_same_domain(final_url, config.domain):
                    job.skipped += 1
                    continue
                if response.status_code >= 400:
                    job.add_error(
                        f"fetch failed {final_url}: HTTP {response.status_code}"
                    )
                    continue

                if "application/pdf" in content_type.lower() or is_pdf_url(final_url):
                    await self._save_pdf(job, final_url, referring_page, response)
                    continue

                if "text/html" not in content_type.lower():
                    job.skipped += 1
                    continue

                await self._save_page(job, final_url, response)
                if depth < config.max_depth:
                    for link in self._extract_links(response.text, final_url):
                        if not self._should_visit(link, config):
                            continue
                        await queue.put((link, depth + 1, final_url))
            finally:
                queue.task_done()

    def _should_visit(self, raw_url: str, config: ScrapeConfig) -> bool:
        if not is_same_domain(raw_url, config.domain):
            return False
        if matches_disallowed(raw_url, config.disallowed_paths):
            return False
        if is_pdf_url(raw_url):
            return True
        return is_allowed_path(raw_url, config.allowed_paths)

    def _extract_links(self, html_text: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html_text, "html.parser")
        links = []
        for tag in soup.find_all("a", href=True):
            absolute = urljoin(base_url, tag.get("href", ""))
            if absolute.startswith(("http://", "https://")):
                links.append(absolute)
        return links

    async def _save_page(
        self,
        job: ScrapeJob,
        page_url: str,
        response: httpx.Response,
    ) -> None:
        config = job.config
        folder = url_to_abs_folder(page_url, config.output_dir, config.folder)
        html_path = folder / "page.html"
        meta_path = folder / "page.meta.json"

        job.pages_visited += 1
        if config.skip_existing and html_path.exists():
            job.skipped += 1
            return

        meta = {
            "source_url": page_url,
            "domain": config.domain,
            "folder": str(safe_site_folder(config.folder) / url_to_folder_path(page_url)),
            "scraped_at": _utc_now_iso(),
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
        }

        if config.dry_run:
            return

        folder.mkdir(parents=True, exist_ok=True)
        html_path.write_bytes(inject_source_url_meta(response.content, page_url))
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    async def _save_pdf(
        self,
        job: ScrapeJob,
        pdf_url: str,
        page_url: str,
        response: httpx.Response,
    ) -> None:
        config = job.config
        filename = sanitize_pdf_filename(pdf_url)
        folder = url_to_abs_folder(page_url, config.output_dir, config.folder)
        pdf_path = folder / filename
        meta_path = folder / f"{filename}.meta.json"

        if pdf_path.exists():
            job.skipped += 1
            return

        meta = {
            "pdf_url": pdf_url,
            "page_url": page_url,
            "filename": filename,
            "domain": urlparse(pdf_url).hostname or config.domain,
            "scraped_at": _utc_now_iso(),
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
        }

        if config.dry_run:
            job.pdfs_downloaded += 1
            return

        folder.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(response.content)
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        job.pdfs_downloaded += 1
