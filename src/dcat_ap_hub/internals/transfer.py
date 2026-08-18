"""Download and extraction utilities."""

import mimetypes
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from dcat_ap_hub.internals.logging import logger
from dcat_ap_hub.internals.models import DatasetMetadata


def _extract_archive(filepath: Path, target_dir: Path) -> None:
    """Recursively extract zip/tar/tgz archives."""

    def is_archive(f: Path) -> bool:
        return f.suffix == ".zip" or f.name.endswith((".tar.gz", ".tgz"))

    # Queue of (archive_path, extract_to_dir)
    queue = [(filepath, target_dir)]

    while queue:
        current_file, current_target = queue.pop(0)

        try:
            extracted = False
            if current_file.suffix == ".zip":
                with zipfile.ZipFile(current_file, "r") as z:
                    z.extractall(current_target)
                extracted = True
            elif current_file.name.endswith((".tar.gz", ".tgz")):
                with tarfile.open(current_file, "r:gz") as t:
                    t.extractall(current_target)
                extracted = True

            if extracted:
                logger.info(f"[extract] Extracted {current_file.name}")
                current_file.unlink()  # Delete archive after extraction

                # Scan for nested archives
                for root, _, files in os.walk(current_target):
                    for name in files:
                        p = Path(root) / name
                        if is_archive(p):
                            queue.append((p, Path(root)))
        except Exception as e:
            logger.error(f"Failed to extract {current_file}: {e}")


def _download_s3_file(
    url: str, dest_path: Path, endpoint: Optional[str] = None, verbose: bool = False
) -> Path:
    """Stream an object from an S3-compatible store to disk and return final path.

    `url` is an `s3://bucket/key/...` URI. `endpoint` is the service URL of the
    S3-compatible store (e.g. https://minio.example.org), typically supplied via
    `dcat:accessURL` so the metadata fully describes how to fetch. When omitted,
    boto3 falls back to the AWS default endpoint, so real AWS S3 works without
    accessURL. Credentials and region resolve via boto3's standard chain
    (env vars, ~/.aws/credentials, IAM role).
    """
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "The 'boto3' library is required to download from s3:// URLs. "
            'Install the S3 variant with: pip install "dcat-ap-hub[s3]".'
        ) from e

    parsed = urlparse(url)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid s3:// URL: {url}")

    client = boto3.client("s3", endpoint_url=endpoint or None)

    # Resolve size + content type ahead of streaming for the progress bar.
    head = client.head_object(Bucket=bucket, Key=key)
    total = int(head.get("ContentLength", 0) or 0)
    content_type = (head.get("ContentType", "") or "").split(";")[0]

    # Extension correction: trust the S3 key suffix first. S3 objects frequently
    # default to `application/octet-stream` (Content-Type unset at upload time),
    # which mimetypes maps to `.bin` and would wrongly rename real files. Only
    # fall back to Content-Type when both the title-derived name and the key
    # lack an extension.
    key_suffix = Path(key).suffix
    if not dest_path.suffix and key_suffix:
        dest_path = dest_path.with_suffix(key_suffix)
    elif not dest_path.suffix:
        ext = mimetypes.guess_extension(content_type)
        if ext:
            dest_path = dest_path.with_suffix(ext)

    pbar = tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        desc=dest_path.name,
        disable=not verbose,
    )

    def _callback(bytes_transferred: int) -> None:
        pbar.update(bytes_transferred)

    try:
        client.download_file(bucket, key, str(dest_path), Callback=_callback)
    finally:
        pbar.close()

    return dest_path


def _download_file(
    url: str,
    dest_path: Path,
    endpoint: Optional[str] = None,
    verbose: bool = False,
) -> Path:
    """Stream download, correct extension via MIME, and return final path.

    For `s3://` URLs, delegates to `_download_s3_file` and uses `endpoint`
    (typically from `dcat:accessURL`) as the S3-compatible service URL.
    For `http(s)://` URLs, `endpoint` is ignored and the existing HTTP
    streaming path is used.
    """
    if url.startswith("s3://"):
        return _download_s3_file(url, dest_path, endpoint=endpoint, verbose=verbose)

    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()

            # Correct extension based on Content-Type, IF no extension present or mismatch
            content_type = r.headers.get("Content-Type", "")
            ext = mimetypes.guess_extension(content_type.split(";")[0])

            # Special case: Prevent overriding valid code extensions with .txt or .conf
            # These extensions are usually correct from source but served as text/plain
            protected_exts = {".py", ".ipynb", ".sh", ".json", ".md", ".yaml", ".yml"}

            should_update = (
                ext
                and dest_path.suffix != ext
                and dest_path.suffix not in protected_exts
            )

            if should_update:
                assert ext is not None  # For type checker
                dest_path = dest_path.with_suffix(ext)

            total = int(r.headers.get("content-length", 0))

            # Write to disk
            with (
                open(dest_path, "wb") as f,
                tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    desc=dest_path.name,
                    disable=not verbose,
                ) as pbar,
            ):
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        return dest_path
    except Exception as e:
        raise RuntimeError(f"Download failed for {url}") from e


def download_dataset_files(
    metadata: DatasetMetadata,
    base_dir: Path,
    force: bool = False,
    verbose: bool = False,
) -> Path:
    """Orchestrate download and extraction for a dataset."""
    dataset_dir = base_dir / metadata.title

    if dataset_dir.exists() and not force:
        if verbose:
            logger.info(f"Dataset directory exists: {dataset_dir}. Skipping download.")
        return dataset_dir

    dataset_dir.mkdir(parents=True, exist_ok=True)

    for distro in metadata.distributions:
        # Initial filename derived from title (extension may change during download)
        temp_path = dataset_dir / distro.get_filename()
        url = distro.best_url

        if not url:
            logger.warning(f"No URL found for distribution '{distro.title}'")
            continue

        if verbose:
            logger.info(f"Downloading: {distro.title}")

        try:
            final_path = _download_file(
                url, temp_path, endpoint=distro.access_url, verbose=verbose
            )

            # Check for archive extraction
            if final_path.suffix in [".zip", ".tgz"] or final_path.name.endswith(
                ".tar.gz"
            ):
                _extract_archive(final_path, dataset_dir)

        except Exception as e:
            logger.error(f"Failed to process distribution '{distro.title}': {e}")

    for resource in metadata.related_resources:
        # Initial filename derived from title (extension may change during download)
        temp_path = dataset_dir / resource.get_filename()
        url = resource.best_url

        if not url:
            logger.warning(f"No URL found for related resource '{resource.title}'")
            continue

        if verbose:
            logger.info(f"Downloading: {resource.title}")

        try:
            final_path = _download_file(
                url, temp_path, endpoint=resource.access_url, verbose=verbose
            )

            # Check for archive extraction
            if final_path.suffix in [".zip", ".tgz"] or final_path.name.endswith(
                ".tar.gz"
            ):
                _extract_archive(final_path, dataset_dir)

        except Exception as e:
            logger.error(f"Failed to process related resource '{resource.title}': {e}")

    return dataset_dir
