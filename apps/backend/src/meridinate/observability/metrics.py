"""
Metrics Collection Module

Tracks operational metrics:
- Job queue depth (queued, processing, completed, failed)
- Job processing times
- WebSocket connections
- API request rates
- Success/failure rates

Exposes metrics in Prometheus format via /metrics endpoint
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional


@dataclass
class JobMetrics:
    """Metrics for a single analysis job"""

    job_id: str
    status: str
    queued_at: float
    started_at: float = 0.0
    completed_at: float = 0.0
    wallets_found: int = 0
    credits_used: int = 0
    error: str = ""

    @property
    def queue_time_seconds(self) -> float:
        """Time spent in queue before processing started"""
        if self.started_at > 0:
            return self.started_at - self.queued_at
        return 0.0

    @property
    def processing_time_seconds(self) -> float:
        """Time spent processing"""
        if self.completed_at > 0 and self.started_at > 0:
            return self.completed_at - self.started_at
        return 0.0

    @property
    def total_time_seconds(self) -> float:
        """Total time from queue to completion"""
        if self.completed_at > 0:
            return self.completed_at - self.queued_at
        return 0.0


class MetricsCollector:
    """Thread-safe metrics collector"""

    def __init__(self):
        self._lock = Lock()
        self._jobs: Dict[str, JobMetrics] = {}
        self._websocket_connections = 0
        self._websocket_messages_sent = 0
        self._websocket_messages_received = 0
        self._http_requests = defaultdict(int)  # endpoint -> count
        self._http_errors = defaultdict(int)  # endpoint -> count
        self._start_time = time.time()

        # API usage tracking
        self._helius_credits_used = 0
        self._dexscreener_requests = 0
        self._coingecko_requests = 0

        # Cache metrics
        self._cache_hits = defaultdict(int)  # cache_name -> hits
        self._cache_misses = defaultdict(int)  # cache_name -> misses

        # Analysis phase timing (for detailed breakdowns)
        self._analysis_phase_times = defaultdict(list)  # phase_name -> [durations]

        # Rate limiting metrics
        self._rate_limit_hits = defaultdict(int)  # endpoint -> count
        self._rate_limit_blocks = defaultdict(int)  # endpoint -> count

    # Job metrics
    def job_queued(self, job_id: str):
        """Record that a job was queued"""
        with self._lock:
            self._jobs[job_id] = JobMetrics(job_id=job_id, status="queued", queued_at=time.time())

    def job_started(self, job_id: str):
        """Record that a job started processing"""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = "processing"
                self._jobs[job_id].started_at = time.time()

    def job_completed(self, job_id: str, wallets_found: int, credits_used: int):
        """Record that a job completed successfully"""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = "completed"
                self._jobs[job_id].completed_at = time.time()
                self._jobs[job_id].wallets_found = wallets_found
                self._jobs[job_id].credits_used = credits_used

    def job_failed(self, job_id: str, error: str):
        """Record that a job failed"""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].completed_at = time.time()
                self._jobs[job_id].error = error

    def get_job_metrics(self, job_id: str) -> Optional[JobMetrics]:
        """Get metrics for a specific job"""
        with self._lock:
            return self._jobs.get(job_id)

    def get_queue_depth(self) -> Dict[str, int]:
        """Get current job queue depth by status"""
        with self._lock:
            counts = defaultdict(int)
            for job in self._jobs.values():
                counts[job.status] += 1
            return dict(counts)

    def get_average_processing_time(self) -> float:
        """Get average processing time for completed jobs"""
        with self._lock:
            completed_jobs = [
                j for j in self._jobs.values() if j.status == "completed" and j.processing_time_seconds > 0
            ]
            if not completed_jobs:
                return 0.0
            return sum(j.processing_time_seconds for j in completed_jobs) / len(completed_jobs)

    def get_average_queue_time(self) -> float:
        """Get average queue time for jobs"""
        with self._lock:
            jobs_with_queue_time = [j for j in self._jobs.values() if j.queue_time_seconds > 0]
            if not jobs_with_queue_time:
                return 0.0
            return sum(j.queue_time_seconds for j in jobs_with_queue_time) / len(jobs_with_queue_time)

    def get_success_rate(self) -> float:
        """Get job success rate (0.0 to 1.0)"""
        with self._lock:
            finished_jobs = [j for j in self._jobs.values() if j.status in ("completed", "failed")]
            if not finished_jobs:
                return 0.0
            completed = sum(1 for j in finished_jobs if j.status == "completed")
            return completed / len(finished_jobs)

    # WebSocket metrics
    def websocket_connected(self):
        """Record WebSocket connection"""
        with self._lock:
            self._websocket_connections += 1

    def websocket_disconnected(self):
        """Record WebSocket disconnection"""
        with self._lock:
            self._websocket_connections = max(0, self._websocket_connections - 1)

    def websocket_message_sent(self):
        """Record WebSocket message sent"""
        with self._lock:
            self._websocket_messages_sent += 1

    def websocket_message_received(self):
        """Record WebSocket message received"""
        with self._lock:
            self._websocket_messages_received += 1

    def get_websocket_stats(self) -> Dict[str, int]:
        """Get WebSocket statistics"""
        with self._lock:
            return {
                "active_connections": self._websocket_connections,
                "messages_sent": self._websocket_messages_sent,
                "messages_received": self._websocket_messages_received,
            }

    # HTTP metrics
    def http_request(self, endpoint: str):
        """Record HTTP request"""
        with self._lock:
            self._http_requests[endpoint] += 1

    def http_error(self, endpoint: str):
        """Record HTTP error"""
        with self._lock:
            self._http_errors[endpoint] += 1

    def get_http_stats(self) -> Dict[str, Dict[str, int]]:
        """Get HTTP request statistics"""
        with self._lock:
            return {"requests": dict(self._http_requests), "errors": dict(self._http_errors)}

    # API usage tracking
    def record_helius_credits(self, credits: int):
        """Record Helius API credits used"""
        with self._lock:
            self._helius_credits_used += credits

    def record_dexscreener_request(self):
        """Record DexScreener API request"""
        with self._lock:
            self._dexscreener_requests += 1

    def record_coingecko_request(self):
        """Record CoinGecko API request"""
        with self._lock:
            self._coingecko_requests += 1

    def get_api_usage(self) -> Dict[str, int]:
        """Get API usage statistics"""
        with self._lock:
            return {
                "helius_credits_used": self._helius_credits_used,
                "dexscreener_requests": self._dexscreener_requests,
                "coingecko_requests": self._coingecko_requests,
            }

    # Cache metrics
    def record_cache_hit(self, cache_name: str):
        """Record cache hit"""
        with self._lock:
            self._cache_hits[cache_name] += 1

    def record_cache_miss(self, cache_name: str):
        """Record cache miss"""
        with self._lock:
            self._cache_misses[cache_name] += 1

    def get_cache_stats(self) -> Dict[str, Dict[str, int]]:
        """Get cache statistics"""
        with self._lock:
            stats = {}
            all_caches = set(self._cache_hits.keys()) | set(self._cache_misses.keys())
            for cache_name in all_caches:
                hits = self._cache_hits.get(cache_name, 0)
                misses = self._cache_misses.get(cache_name, 0)
                total = hits + misses
                hit_rate = hits / total if total > 0 else 0.0
                stats[cache_name] = {
                    "hits": hits,
                    "misses": misses,
                    "total": total,
                    "hit_rate": hit_rate,
                }
            return stats

    # Analysis phase timing
    def record_analysis_phase(self, phase_name: str, duration_seconds: float):
        """Record analysis phase timing"""
        with self._lock:
            self._analysis_phase_times[phase_name].append(duration_seconds)

    def get_analysis_phase_stats(self) -> Dict[str, Dict[str, float]]:
        """Get analysis phase timing statistics"""
        with self._lock:
            stats = {}
            for phase, times in self._analysis_phase_times.items():
                if times:
                    stats[phase] = {
                        "avg": sum(times) / len(times),
                        "min": min(times),
                        "max": max(times),
                        "count": len(times),
                    }
            return stats

    # Rate limiting metrics
    def record_rate_limit_hit(self, endpoint: str):
        """Record successful request that consumed rate limit quota"""
        with self._lock:
            self._rate_limit_hits[endpoint] += 1

    def record_rate_limit_block(self, endpoint: str):
        """Record request that was blocked by rate limit"""
        with self._lock:
            self._rate_limit_blocks[endpoint] += 1

    def get_rate_limit_stats(self) -> Dict[str, Dict[str, int]]:
        """Get rate limiting statistics"""
        with self._lock:
            all_endpoints = set(self._rate_limit_hits.keys()) | set(self._rate_limit_blocks.keys())
            stats = {}
            for endpoint in all_endpoints:
                hits = self._rate_limit_hits.get(endpoint, 0)
                blocks = self._rate_limit_blocks.get(endpoint, 0)
                total = hits + blocks
                block_rate = blocks / total if total > 0 else 0.0
                stats[endpoint] = {
                    "hits": hits,
                    "blocks": blocks,
                    "total": total,
                    "block_rate": block_rate,
                }
            return stats

    # Prometheus metrics format
    def get_prometheus_metrics(self) -> str:
        """Generate Prometheus-format metrics"""
        metrics = []

        # Uptime
        uptime = time.time() - self._start_time
        metrics.append(f"# HELP app_uptime_seconds Application uptime in seconds")
        metrics.append(f"# TYPE app_uptime_seconds gauge")
        metrics.append(f"app_uptime_seconds {uptime:.2f}")

        # Job queue depth by status
        metrics.append(f"\n# HELP job_queue_depth Number of jobs by status")
        metrics.append(f"# TYPE job_queue_depth gauge")
        queue_depth = self.get_queue_depth()
        for status, count in queue_depth.items():
            metrics.append(f'job_queue_depth{{status="{status}"}} {count}')

        # Processing times
        avg_processing = self.get_average_processing_time()
        metrics.append(f"\n# HELP job_processing_seconds_avg Average job processing time")
        metrics.append(f"# TYPE job_processing_seconds_avg gauge")
        metrics.append(f"job_processing_seconds_avg {avg_processing:.2f}")

        avg_queue = self.get_average_queue_time()
        metrics.append(f"\n# HELP job_queue_seconds_avg Average job queue time")
        metrics.append(f"# TYPE job_queue_seconds_avg gauge")
        metrics.append(f"job_queue_seconds_avg {avg_queue:.2f}")

        # Success rate
        success_rate = self.get_success_rate()
        metrics.append(f"\n# HELP job_success_rate Job success rate (0.0 to 1.0)")
        metrics.append(f"# TYPE job_success_rate gauge")
        metrics.append(f"job_success_rate {success_rate:.4f}")

        # WebSocket stats
        ws_stats = self.get_websocket_stats()
        metrics.append(f"\n# HELP websocket_active_connections Current active WebSocket connections")
        metrics.append(f"# TYPE websocket_active_connections gauge")
        metrics.append(f"websocket_active_connections {ws_stats['active_connections']}")

        metrics.append(f"\n# HELP websocket_messages_total Total WebSocket messages")
        metrics.append(f"# TYPE websocket_messages_total counter")
        metrics.append(f'websocket_messages_total{{direction="sent"}} {ws_stats["messages_sent"]}')
        metrics.append(f'websocket_messages_total{{direction="received"}} {ws_stats["messages_received"]}')

        # HTTP stats
        http_stats = self.get_http_stats()
        metrics.append(f"\n# HELP http_requests_total Total HTTP requests by endpoint")
        metrics.append(f"# TYPE http_requests_total counter")
        for endpoint, count in http_stats["requests"].items():
            safe_endpoint = endpoint.replace('"', '\\"')
            metrics.append(f'http_requests_total{{endpoint="{safe_endpoint}"}} {count}')

        metrics.append(f"\n# HELP http_errors_total Total HTTP errors by endpoint")
        metrics.append(f"# TYPE http_errors_total counter")
        for endpoint, count in http_stats["errors"].items():
            safe_endpoint = endpoint.replace('"', '\\"')
            metrics.append(f'http_errors_total{{endpoint="{safe_endpoint}"}} {count}')

        # API usage stats
        api_usage = self.get_api_usage()
        metrics.append(f"\n# HELP helius_credits_used_total Total Helius API credits used")
        metrics.append(f"# TYPE helius_credits_used_total counter")
        metrics.append(f"helius_credits_used_total {api_usage['helius_credits_used']}")

        metrics.append(f"\n# HELP dexscreener_requests_total Total DexScreener API requests")
        metrics.append(f"# TYPE dexscreener_requests_total counter")
        metrics.append(f"dexscreener_requests_total {api_usage['dexscreener_requests']}")

        metrics.append(f"\n# HELP coingecko_requests_total Total CoinGecko API requests")
        metrics.append(f"# TYPE coingecko_requests_total counter")
        metrics.append(f"coingecko_requests_total {api_usage['coingecko_requests']}")

        # Cache stats
        cache_stats = self.get_cache_stats()
        metrics.append(f"\n# HELP cache_hits_total Cache hits by cache name")
        metrics.append(f"# TYPE cache_hits_total counter")
        for cache_name, stats in cache_stats.items():
            safe_name = cache_name.replace('"', '\\"')
            metrics.append(f'cache_hits_total{{cache="{safe_name}"}} {stats["hits"]}')

        metrics.append(f"\n# HELP cache_misses_total Cache misses by cache name")
        metrics.append(f"# TYPE cache_misses_total counter")
        for cache_name, stats in cache_stats.items():
            safe_name = cache_name.replace('"', '\\"')
            metrics.append(f'cache_misses_total{{cache="{safe_name}"}} {stats["misses"]}')

        metrics.append(f"\n# HELP cache_hit_rate Cache hit rate by cache name (0.0 to 1.0)")
        metrics.append(f"# TYPE cache_hit_rate gauge")
        for cache_name, stats in cache_stats.items():
            safe_name = cache_name.replace('"', '\\"')
            metrics.append(f'cache_hit_rate{{cache="{safe_name}"}} {stats["hit_rate"]:.4f}')

        # Analysis phase timing
        phase_stats = self.get_analysis_phase_stats()
        if phase_stats:
            metrics.append(f"\n# HELP analysis_phase_duration_avg Average phase duration in seconds")
            metrics.append(f"# TYPE analysis_phase_duration_avg gauge")
            for phase, stats in phase_stats.items():
                safe_phase = phase.replace('"', '\\"')
                metrics.append(f'analysis_phase_duration_avg{{phase="{safe_phase}"}} {stats["avg"]:.4f}')

            metrics.append(f"\n# HELP analysis_phase_duration_max Maximum phase duration in seconds")
            metrics.append(f"# TYPE analysis_phase_duration_max gauge")
            for phase, stats in phase_stats.items():
                safe_phase = phase.replace('"', '\\"')
                metrics.append(f'analysis_phase_duration_max{{phase="{safe_phase}"}} {stats["max"]:.4f}')

        # Rate limiting stats
        rate_limit_stats = self.get_rate_limit_stats()
        if rate_limit_stats:
            metrics.append(f"\n# HELP rate_limit_hits_total Total requests that consumed rate limit quota")
            metrics.append(f"# TYPE rate_limit_hits_total counter")
            for endpoint, stats in rate_limit_stats.items():
                safe_endpoint = endpoint.replace('"', '\\"')
                metrics.append(f'rate_limit_hits_total{{endpoint="{safe_endpoint}"}} {stats["hits"]}')

            metrics.append(f"\n# HELP rate_limit_blocks_total Total requests blocked by rate limit")
            metrics.append(f"# TYPE rate_limit_blocks_total counter")
            for endpoint, stats in rate_limit_stats.items():
                safe_endpoint = endpoint.replace('"', '\\"')
                metrics.append(f'rate_limit_blocks_total{{endpoint="{safe_endpoint}"}} {stats["blocks"]}')

            metrics.append(f"\n# HELP rate_limit_block_rate Rate of requests blocked (0.0 to 1.0)")
            metrics.append(f"# TYPE rate_limit_block_rate gauge")
            for endpoint, stats in rate_limit_stats.items():
                safe_endpoint = endpoint.replace('"', '\\"')
                metrics.append(f'rate_limit_block_rate{{endpoint="{safe_endpoint}"}} {stats["block_rate"]:.4f}')

        return "\n".join(metrics) + "\n"


# Global metrics collector instance
metrics_collector = MetricsCollector()
