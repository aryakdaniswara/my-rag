from copy import deepcopy
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


UI_DOMAIN_SUFFIX = ".ui.ac.id"
DEFAULT_SITE_CONFIG: Dict[str, Any] = {
    "output_dir": "/app/data",
    "rate_limit_ms": 1000,
    "max_depth": 4,
    "max_parallelism": 2,
    "user_agent": "UI-RAG-Scraper/1.0 (skripsi research; contact: mahasiswa@ui.ac.id)",
    "sites": [
        {
            "domain": "simak.ui.ac.id",
            "folder": "simak",
            "seeds": ["https://simak.ui.ac.id/"],
            "allowed_paths": [
                "/tentang-simak/",
                "/jadwal-seleksi/",
                "/sarjana-2/",
                "/s1-reguler/",
                "/s1-kelas-khusus-internasional-kki/",
                "/s1-rpl/",
                "/vokasi-2/",
                "/s2-magister/",
                "/profesi-2/",
                "/spesialis-2/",
                "/s3-doktor/",
                "/fakultas-2/",
                "/snbp/",
                "/snbt/",
                "/ppkb/",
                "/sjp-ta-2026-2027/",
                "/talent-scouting/",
                "/simak-ui/",
                "/biaya-pendaftaran/",
                "/sk-biaya-pendidikan-ui/",
                "/keketatan-s1-vokasi-ui-2025/",
                "/keketatan-s1-kki-2025/",
                "/info/",
            ],
            "disallowed_paths": [
                "/berita/",
                "/news/",
                "/daftar-berita/",
                "/tender-",
                "/lelang-",
                "/tag/",
                "/category/",
                "/author/",
                "/page/[0-9]+",
                "wa\\.me",
                "whatsapp",
            ],
        },
        {
            "domain": "www.ui.ac.id",
            "folder": "ui_ac_id",
            "seeds": ["https://www.ui.ac.id/"],
            "allowed_paths": [
                "/tentang-ui/",
                "/akademik/",
                "/layanan-akademik/",
                "/direktorat-penjaminan-mutu-akademik/",
                "/skbp2026/",
                "/skbp2025/",
                "/skbp2024/",
                "/penerimaan-universitas-indonesia-old2/",
                "/program-sarjana/",
                "/program-kelas-internasional/",
                "/program-rpl/",
                "/program-magister/",
                "/program-profesi/",
                "/program-spesialis/",
                "/program-doktoral/",
                "/people/",
                "/pusat-administrasi-universitas-20252029/",
                "/alumni/",
                "/kampus/",
                "/fasilitas/",
                "/mitra/",
                "/riset-dan-inovasi/",
            ],
            "disallowed_paths": [
                "/berita/",
                "/news/",
                "/daftar-berita/",
                "/tender-",
                "/lelang-",
                "/tag/",
                "/category/",
                "/author/",
                "/page/[0-9]+",
                "wa\\.me",
                "whatsapp",
            ],
        },
        {
            "domain": "kemahasiswaan.ui.ac.id",
            "folder": "kemahasiswaan",
            "seeds": ["https://kemahasiswaan.ui.ac.id/"],
            "allowed_paths": [
                "/profile/",
                "/foto-direktur-kemahasiswaan-dan-beasiswa/",
                "/pkkmb/",
                "/unit-kegiatan-mahasiswa/",
                "/beasiswa/",
                "/fasilitas-2/",
                "/kompetisi/",
                "/foto-kasubdit-prestasi-mahasiswa/",
                "/foto-kasubdit-organisasi-kemahasiswaan/",
                "/foto-kasubdit-beasiswa/",
                "/tentang-kami/",
            ],
            "disallowed_paths": [
                "/berita/",
                "/news/",
                "/daftar-berita/",
                "/tender-",
                "/lelang-",
                "/tag/",
                "/category/",
                "/author/",
                "/page/[0-9]+",
                "wa\\.me",
                "whatsapp",
            ],
        },
        {
            "domain": "beasiswa.ui.ac.id",
            "folder": "beasiswa",
            "seeds": ["https://beasiswa.ui.ac.id/"],
            "allowed_paths": [],
            "disallowed_paths": [
                "/berita/",
                "/news/",
                "/daftar-berita/",
                "/tender-",
                "/lelang-",
                "/tag/",
                "/category/",
                "/author/",
                "/page/[0-9]+",
                "wa\\.me",
                "whatsapp",
            ],
        },
        {
            "domain": "penerimaan.ui.ac.id",
            "folder": "penerimaan",
            "seeds": ["https://penerimaan.ui.ac.id/"],
            "allowed_paths": [
                "/page/registration",
                "/ppkb",
            ],
            "disallowed_paths": [
                "/berita/",
                "/news/",
                "/daftar-berita/",
                "/tender-",
                "/lelang-",
                "/tag/",
                "/category/",
                "/author/",
                "/page/[0-9]+",
                "wa\\.me",
                "whatsapp",
            ],
        },
        {
            "domain": "international.ui.ac.id",
            "folder": "international",
            "seeds": [
                "https://international.ui.ac.id/prospective-students/",
                "https://international.ui.ac.id/undergraduate-program/",
                "https://international.ui.ac.id/graduate-program/",
                "https://international.ui.ac.id/knb/",
                "https://international.ui.ac.id/psu-graduate-scholarship/",
            ],
            "allowed_paths": [
                "/prospective-students/",
                "/undergraduate-program/",
                "/graduate-program/",
                "/knb/",
                "/psu-graduate-scholarship/",
            ],
            "disallowed_paths": [
                "/category/",
                "/tag/",
                "/author/",
                "/page/[0-9]+",
                "wa\\.me",
                "whatsapp",
            ],
        },
        {
            "domain": "admission.ui.ac.id",
            "folder": "admission",
            "seeds": ["https://admission.ui.ac.id/"],
            "allowed_paths": [
                "/procedure",
                "/register",
            ],
            "disallowed_paths": [
                "/login",
                "/user",
                "/logout",
                "/profile",
                "/payment",
            ],
            "max_depth": 2,
            "max_parallelism": 1,
        },
        {
            "domain": "enrollment.ui.ac.id",
            "folder": "enrollment",
            "seeds": [
                "https://enrollment.ui.ac.id/",
                "https://enrollment.ui.ac.id/en",
            ],
            "allowed_paths": [
                "/",
                "/en",
            ],
            "disallowed_paths": [
                "/login",
                "/auth",
                "/profile",
                "/payment",
            ],
            "max_depth": 1,
            "max_parallelism": 1,
        },
    ],
}


def is_ui_domain(domain: str) -> bool:
    normalized = domain.lower().strip()
    return normalized == "ui.ac.id" or normalized.endswith(UI_DOMAIN_SUFFIX)


def folder_from_domain(domain: str) -> str:
    normalized = domain.lower().strip()
    if normalized == "www.ui.ac.id":
        return "ui_ac_id"
    if normalized.endswith(UI_DOMAIN_SUFFIX):
        return normalized[: -len(UI_DOMAIN_SUFFIX)].replace(".", "_")
    return normalized.replace(".", "_")


def list_configured_sites() -> Dict[str, Any]:
    data = deepcopy(DEFAULT_SITE_CONFIG)
    return {
        "source": "scraper_api.sites.DEFAULT_SITE_CONFIG",
        "output_dir": data.get("output_dir"),
        "rate_limit_ms": data.get("rate_limit_ms"),
        "max_depth": data.get("max_depth"),
        "max_parallelism": data.get("max_parallelism"),
        "user_agent": data.get("user_agent"),
        "sites": data.get("sites", []),
    }


def config_from_configured_site(
    site_url: str,
    *,
    output_dir: str = "/app/data",
    skip_existing: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    parsed = urlparse(site_url.strip())
    domain = (parsed.hostname or "").lower()
    if not domain:
        raise ValueError("site_url must include a hostname")

    data = DEFAULT_SITE_CONFIG
    for site in data.get("sites", []):
        if site.get("domain", "").lower() != domain:
            continue
        return {
            "domain": site["domain"],
            "folder": site["folder"],
            "seeds": site.get("seeds") or [site_url],
            "allowed_paths": site.get("allowed_paths", []),
            "disallowed_paths": site.get("disallowed_paths", []),
            "max_depth": site.get("max_depth", data.get("max_depth", 4)),
            "max_parallelism": site.get(
                "max_parallelism",
                data.get("max_parallelism", 2),
            ),
            "rate_limit_ms": site.get("rate_limit_ms", data.get("rate_limit_ms", 1000)),
            "user_agent": site.get(
                "user_agent",
                data.get("user_agent", "UI-RAG-Scraper/1.0"),
            ),
            "skip_existing": skip_existing,
            "dry_run": dry_run,
            "output_dir": output_dir,
        }

    raise ValueError(f"site_url domain is not configured: {domain}")


def config_from_urls(
    urls: List[str],
    *,
    allow_external: bool = False,
    folder: Optional[str] = None,
    output_dir: str = "/app/data",
    max_depth: int = 2,
    max_parallelism: int = 2,
    rate_limit_ms: int = 1000,
    user_agent: str = "UI-RAG-Scraper/1.0",
    skip_existing: bool = True,
    dry_run: bool = False,
    disallowed_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    cleaned_urls = [url.strip() for url in urls if url.strip()]
    if not cleaned_urls:
        raise ValueError("urls must contain at least one URL")

    parsed_urls = [urlparse(url) for url in cleaned_urls]
    domains = {(parsed.hostname or "").lower() for parsed in parsed_urls}
    if "" in domains:
        raise ValueError("all urls must include a hostname")
    if len(domains) != 1:
        raise ValueError(
            "one scrape job can only target one domain; submit separate jobs per domain"
        )

    domain = next(iter(domains))
    if not allow_external and not is_ui_domain(domain):
        raise ValueError(
            f"refusing non-UI domain {domain}; set allow_external=true to override"
        )

    allowed_paths = []
    for parsed in parsed_urls:
        path = parsed.path or "/"
        if path not in allowed_paths:
            allowed_paths.append(path)

    return {
        "domain": domain,
        "folder": folder or folder_from_domain(domain),
        "seeds": cleaned_urls,
        "allowed_paths": allowed_paths,
        "disallowed_paths": disallowed_paths or [],
        "max_depth": max_depth,
        "max_parallelism": max_parallelism,
        "rate_limit_ms": rate_limit_ms,
        "user_agent": user_agent,
        "skip_existing": skip_existing,
        "dry_run": dry_run,
        "output_dir": output_dir,
    }
