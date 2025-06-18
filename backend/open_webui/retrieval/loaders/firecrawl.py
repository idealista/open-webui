import logging
import requests
import time
import asyncio
from typing import Iterator, List, Union, Dict, Any, AsyncGenerator
from urllib.parse import urljoin
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from open_webui.env import SRC_LOG_LEVELS

from open_webui.models.knowledge import ExtractUrlMode

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


class FireCrawlLoader(BaseLoader):
    """Load web pages using FireCrawl API.

    This is a LangChain document loader that uses FireCrawl's API to
    retrieve content from web pages and return it as Document objects.

    In crawl mode, the loader will block until the crawl job completes,
    making it simpler to use but potentially long-running for large sites.
    """

    def __init__(
        self,
        urls: Union[str, List[str]],
        api_key: str,
        api_url: str = "https://api.firecrawl.dev",
        mode: ExtractUrlMode = ExtractUrlMode.SCRAPE,
    ) -> None:
        """Initialize FireCrawl loader.

        Args:
            urls: URL or list of URLs to process.
            api_key: The FireCrawl API key.
            api_url: Base URL for FireCrawl API.
            mode: Operation mode:
                - 'scrape': Direct page scraping (default)
                - 'crawl': Website crawling mode (blocks until completion)
            scrape_options: Additional options for scraping mode.
            crawl_options: Additional options for crawling mode. Can include:
                - poll_interval: Time between status checks (default: 5 seconds)
                - max_wait_time: Maximum time to wait for completion (default: 600 seconds)
        """
        if not urls:
            raise ValueError("At least one URL must be provided.")

        if not api_key:
            raise ValueError("FireCrawl API key must be provided.")

        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.urls = urls if isinstance(urls, list) else [urls]
        self.mode = mode
        self.scrape_options = {
            "formats": ["markdown"],
            "onlyMainContent": True,
            "waitFor": 500,  # Default wait time for page load
            "removeBase64Images": True,
            "excludeTags": ["nav", "footer", "aside"],  # Default tags to exclude
        }
        self.crawl_options = {
            "limit": 1000,  # Maximum number of pages to crawl. Default limit is 10000.
            "maxDepth": 10,  # Maximum depth to crawl relative to the base URL. Basically, the max number of slashes the pathname of a scraped URL may contain.
            "delay": 0.1,  # Delay between requests in seconds
            "scrapeOptions": {
                "formats": ["markdown"],
                "onlyMainContent": True,
                "excludeTags": ["nav", "footer", "aside"],  # Default tags to exclude
                "waitFor": 0,  # Default wait time for page load in ms
            },
        }

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "User-Agent": "Open WebUI (https://github.com/open-webui/open-webui) FireCrawl Loader",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _scrape_url(self, url: str) -> List[Document]:
        """Scrape a single URL using FireCrawl."""
        try:
            scrape_url = urljoin(self.api_url, "/v1/scrape")

            # Build payload with sensible defaults
            payload: Dict[str, Any] = {"url": url, **self.scrape_options}

            log.debug(f"Scraping {url} with options: {payload}")

            response = requests.post(
                scrape_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30,  # Add timeout
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("success", False):
                error_message = result.get("error", "Unknown error during scrape.")
                log.error(f"FireCrawl scrape failed for {url}: {error_message}")
                raise Exception(f"FireCrawl scrape failed: {error_message}")

            data = result.get("data", {})
            content = data.get("markdown", data.get("content", ""))

            if not content or content.strip() == "":
                log.warning(f"No content extracted from URL: {url}")
                return []

            # Build comprehensive metadata
            metadata = {
                "source": url,
                "url": url,
                "firecrawl_mode": "scrape",
                "content_length": len(content),
            }

            # Add title and description if available
            if "metadata" in data and isinstance(data["metadata"], dict):
                firecrawl_metadata = data["metadata"]
                metadata["title"] = firecrawl_metadata.get("title", "")
                metadata["description"] = firecrawl_metadata.get("description", "")

                # Add other metadata with firecrawl_ prefix to avoid conflicts
                for key, value in firecrawl_metadata.items():
                    if key not in ["title", "description"] and value is not None:
                        # Convert complex values to strings for metadata
                        if isinstance(value, (dict, list)):
                            metadata[f"firecrawl_{key}"] = str(value)
                        else:
                            metadata[f"firecrawl_{key}"] = str(value)

            return [Document(page_content=content, metadata=metadata)]

        except requests.HTTPError as e:
            log.error(
                f"HTTP error scraping {url}: {e.response.status_code} - {e.response.text if e.response else str(e)}"
            )
            raise
        except Exception as e:
            log.error(f"Error scraping {url}: {e}")
            raise

    def _poll_crawl_status_sync(
        self, firecrawl_job_id: str, status_url: str, original_url: str
    ) -> List[Document]:
        """Poll FireCrawl job status synchronously until completion."""

        log.info(
            f"Starting sync polling for FireCrawl job {firecrawl_job_id} (URL: {original_url})."
        )

        poll_interval = 5
        max_wait_time = 600
        start_time = time.time()

        try:
            while True:
                current_time = time.time()
                if current_time - start_time > max_wait_time:
                    error_msg = f"Timeout waiting for FireCrawl job {firecrawl_job_id} (URL: {original_url}) to complete after {max_wait_time} seconds."
                    log.error(error_msg)
                    raise Exception(error_msg)

                log.debug(
                    f"Checking status for FireCrawl job {firecrawl_job_id} (URL: {original_url}) via {status_url}"
                )

                response = requests.get(status_url, headers=self._get_headers())
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")
                log.info(
                    f"FireCrawl job {firecrawl_job_id} status: {status} (URL: {original_url})"
                )

                if status == "completed":
                    log.info(
                        f"FireCrawl job {firecrawl_job_id} for {original_url} completed. Collecting results."
                    )
                    return self._collect_results_sync(
                        firecrawl_job_id, status_data.get("data", []), original_url
                    )

                elif status in ("failed", "error"):
                    error_message = status_data.get("message", "Unknown crawl error")
                    log.error(
                        f"FireCrawl job {firecrawl_job_id} for {original_url} failed: {error_message}"
                    )
                    raise Exception(f"FireCrawl job failed: {error_message}")

                # Log progress but continue polling
                count = status_data.get("completed", 0)
                total = status_data.get("total", 0)
                progress = total and count / total * 100 if total > 0 else 0
                log.info(
                    f"FireCrawl job {firecrawl_job_id} progress: {progress:.0f}% ({count}/{total} pages)"
                )

                time.sleep(poll_interval)

        except requests.HTTPError as e:
            log.error(
                f"HTTP error polling status for FireCrawl job {firecrawl_job_id} (URL: {original_url}): {e.response.status_code} - {e.response.text if e.response else str(e)}"
            )
            raise
        except Exception as e:
            log.error(
                f"Unexpected error polling status for FireCrawl job {firecrawl_job_id} (URL: {original_url}): {e}"
            )
            raise

    def _collect_results_sync(
        self,
        firecrawl_job_id: str,
        crawled_pages_data: List[Dict[str, Any]],
        original_url: str,
    ) -> List[Document]:
        """Sync version to process data from a completed FireCrawl job."""
        documents = []
        log.info(
            f"Processing collected data for completed FireCrawl job {firecrawl_job_id} from {original_url}"
        )

        if not crawled_pages_data:
            log.warning(
                f"No data provided to _collect_results_sync for FireCrawl job {firecrawl_job_id} (URL: {original_url})"
            )
            return []

        for item in crawled_pages_data:
            content = item.get("markdown", item.get("content", ""))
            source_url = item.get("sourceURL", original_url)

            if not content:
                log.warning(
                    f"No content found for crawled page from job {firecrawl_job_id}: {source_url}"
                )
                continue

            metadata = {
                "source": source_url,
                "title": item.get("metadata", {}).get("title", ""),
                "description": item.get("metadata", {}).get("description", ""),
                "url": source_url,
                "firecrawl_mode": "crawl",
                "job_id": firecrawl_job_id,
                "original_url": original_url,
            }

            # Add any additional metadata from FireCrawl
            if "metadata" in item:
                firecrawl_metadata = item["metadata"]
                if isinstance(firecrawl_metadata, dict):
                    for key, value in firecrawl_metadata.items():
                        if key not in metadata:
                            metadata[f"firecrawl_{key}"] = value

            documents.append(Document(page_content=content, metadata=metadata))

        log.info(
            f"Successfully processed {len(documents)} pages from crawled job {firecrawl_job_id} for {original_url}"
        )
        return documents

    def _crawl_url(self, url: str) -> List[Document]:
        """Crawl a URL using FireCrawl and wait for completion."""
        try:
            crawl_url_path = "/v1/crawl"
            crawl_submit_url = urljoin(self.api_url, crawl_url_path)

            # Build default payload with sensible defaults
            payload: Dict[str, Any] = {"url": url, **self.crawl_options}

            log.info(f"Submitting FireCrawl crawl job for {url}")
            log.debug(f"Crawl payload: {payload}")

            response = requests.post(
                crawl_submit_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30,  # Add timeout for the submission request
            )
            response.raise_for_status()
            result = response.json()

            # Extract job ID and status URL from the response
            firecrawl_job_id = result.get("id")
            if not firecrawl_job_id:
                error_message = result.get(
                    "message",
                    "FireCrawl crawl submission did not return a job ID.",
                )
                log.error(
                    f"FireCrawl crawl submission failed for {url}: {error_message}"
                )
                raise Exception(f"FireCrawl crawl submission failed: {error_message}")

            # Construct status URL
            status_url = result.get("url")
            if not status_url:
                error_message = result.get(
                    "message", "FireCrawl crawl submission did not return a status URL."
                )
                log.error(
                    f"FireCrawl crawl submission failed for {url}: {error_message}"
                )
                raise Exception(f"FireCrawl crawl submission failed: {error_message}")

            # FireCrawl returns an HTTPS URL even if the original URL is HTTP.
            # Ensure status URL uses http if the original URL is http
            if status_url.startswith("https://") and crawl_submit_url.startswith(
                "http://"
            ):
                status_url = status_url.replace("https://", "http://")

            log.info(
                f"FireCrawl crawl job {firecrawl_job_id} submitted for {url}. Polling for completion..."
            )

            # Poll synchronously until completion
            return self._poll_crawl_status_sync(firecrawl_job_id, status_url, url)

        except requests.HTTPError as e:
            log.error(
                f"HTTP error submitting crawl job for {url}: {e.response.status_code} - {e.response.text if e.response else str(e)}"
            )
            raise
        except Exception as e:
            log.error(f"Error submitting crawl job for {url}: {e}")
            raise

    def lazy_load(self) -> Iterator[Document]:
        """Load documents from the URLs using FireCrawl API."""
        for url_item in self.urls:
            docs_for_url: List[Document] = []
            if self.mode == ExtractUrlMode.SCRAPE:
                log.debug(f"Scraping URL: {url_item}")
                docs_for_url = self._scrape_url(url_item)
            elif self.mode == ExtractUrlMode.CRAWL:
                log.debug(f"Crawling URL: {url_item}")
                docs_for_url = self._crawl_url(url_item)  # Now blocks until completion
            else:
                log.error(f"Unknown FireCrawl mode: {self.mode} for URL: {url_item}")
                docs_for_url = []

            for doc in docs_for_url:
                yield doc

    async def alazy_load(self) -> AsyncGenerator[Document, None]:
        """Async version of lazy_load."""
        for url_item in self.urls:
            docs_for_url: List[Document] = []
            if self.mode == ExtractUrlMode.SCRAPE:
                log.debug(f"Async scraping URL: {url_item}")
                # Run synchronous _scrape_url in a thread to make it non-blocking
                loop = asyncio.get_event_loop()
                docs_for_url = await loop.run_in_executor(
                    None, self._scrape_url, url_item
                )
            elif self.mode == ExtractUrlMode.CRAWL:
                log.debug(f"Async crawling URL: {url_item}")
                # Run synchronous _crawl_url in a thread to make it non-blocking
                loop = asyncio.get_event_loop()
                docs_for_url = await loop.run_in_executor(
                    None, self._crawl_url, url_item
                )
            else:
                log.error(
                    f"Async loading: Unknown FireCrawl mode: {self.mode} for URL: {url_item}"
                )
                docs_for_url = []

            for doc in docs_for_url:
                yield doc
