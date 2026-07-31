from src.services.diff_parser import parse_unified_diff
from src.services.chunker import chunk_parsed_files
from src.services.sse_manager import sse_manager
from src.services.provider_factory import provider_factory
from src.providers.mock_provider import sort_and_dedup_findings
from src.models.schemas import Finding, JobUsage

async def process_job(job_id: str, queue_manager) -> None:
    """
    Owns the entire review execution pipeline for a job.
    """
    job = queue_manager.get_job(job_id)
    if not job:
        return

    job.status = "running"
    sse_manager.emit_status(job_id, "running")

    try:
        # 1. Parse unified diff
        parsed_files = parse_unified_diff(job.diff_text)

        # 2. Sequential file boundary chunking
        chunks = chunk_parsed_files(parsed_files)
        input_bytes = len(job.diff_text.encode("utf-8"))
        num_chunks = len(chunks)

        # 3. Get provider instance
        provider = provider_factory.get_provider(job.options.provider)
        accumulated_findings: list[Finding] = []

        # 4. Process chunks and stream findings as discovered
        for chunk in chunks:
            chunk_findings = await provider.analyze_chunk(chunk)
            for finding in chunk_findings:
                sse_manager.emit_finding(job_id, finding)
                accumulated_findings.append(finding)

        # 5. Deduplicate and sort findings across all chunks
        final_findings = sort_and_dedup_findings(accumulated_findings)
        total_findings_count = len(final_findings)

        # Truncate for response based on maxFindings
        truncated_findings = final_findings[:job.options.maxFindings]

        usage = JobUsage(
            inputBytes=input_bytes,
            chunks=num_chunks,
            cacheHit=job.cache_hit
        )

        job.findings = truncated_findings
        job.usage = usage
        job.status = "done"

        # 6. Store completed result in cache
        queue_manager.save_cached_result(
            diff_text=job.diff_text,
            options=job.options,
            findings=final_findings,
            usage=usage
        )

        # 7. Emit done SSE event
        sse_manager.emit_done(job_id, total_findings_count, usage)

    except Exception as err:
        job.status = "failed"
        job.error_message = str(err)
        sse_manager.emit_error(job_id, str(err))
