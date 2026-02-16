"""
Core worker logic for processing transcription jobs.
"""

import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import redis as sync_redis

from sqlmodel import Session, create_engine, select

from src.api.models import Job, StageResult
from .transcriber import GroqTranscriber
from .diarizer import SpeakerDiarizer, DiarizationError
from .formatter import DeepSeekFormatter, MultiStageFormatter, FormattingError
from .output import OutputGenerator
from .profile_loader import ProfileLoader
from .types import DegreeProfile
from .email import EmailSender, get_kate_email, get_keira_email, get_keira_cohort_email
from .merge import merge_transcript_with_speakers

logger = logging.getLogger(__name__)

# Database configuration - TODO: Move to config
DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)

class JobProcessor:
    """Orchestrates the transcription and processing pipeline with state tracking."""
    
    def __init__(self, config_dir: Path, processing_dir: Path, output_dir: Path):
        self.config_dir = config_dir
        self.processing_dir = processing_dir
        self.output_dir = output_dir
        
        # Setup directories
        self.quarantine_dir = processing_dir / "quarantine"
        self.error_dir = processing_dir / "errors"
        self.archive_dir = processing_dir / "archive"
        
        for d in [self.quarantine_dir, self.error_dir, self.archive_dir]:
            d.mkdir(parents=True, exist_ok=True)
            
        # Initialize components
        self.profile_loader = ProfileLoader(config_dir)
        self.output_generator = OutputGenerator(output_dir)
        self.email_sender = EmailSender()
        
        self.groq = None
        self.diarizer = None
        self.formatter = None
        self.multi_stage_formatter = None
        
        # Redis for pub/sub status updates
        try:
            self._redis = sync_redis.Redis(host="redis", port=6379, socket_connect_timeout=2)
            self._redis.ping()
            logger.info("Redis connected for job status publishing")
        except Exception as e:
            logger.warning(f"Redis not available for pub/sub: {e}")
            self._redis = None
        
        self._initialize_clients()
        
    def _initialize_clients(self):
        """Initialize API clients."""
        # Groq
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.groq = GroqTranscriber(api_key=groq_key)
            logger.info("Groq client initialized")
        else:
            logger.warning("GROQ_API_KEY not set")
            
        # Pyannote
        hf_token = os.getenv("HUGGINGFACE_TOKEN")
        if hf_token:
            try:
                self.diarizer = SpeakerDiarizer(hf_token=hf_token)
                logger.info("Pyannote diarizer initialized")
            except Exception as e:
                logger.error(f"Failed to init diarizer: {e}")
        else:
            logger.warning("HUGGINGFACE_TOKEN not set")
            
        # DeepSeek (default formatter for standard processing)
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self.formatter = DeepSeekFormatter(
                api_key=deepseek_key,
                prompts_dir=self.config_dir / "prompts"
            )
            logger.info("DeepSeek formatter initialized")
        else:
            logger.warning("DEEPSEEK_API_KEY not set")
        
        # Log available LLM providers
        from .providers import get_configured_providers
        providers = get_configured_providers()
        for name, configured in providers.items():
            if configured:
                logger.info(f"Provider available: {name}")
            else:
                logger.info(f"Provider not configured: {name}")

    def _publish_status(self, job: Job, stage_detail: dict = None):
        """Publish job status update to Redis for WebSocket broadcasting."""
        if not self._redis:
            return
        try:
            payload = {
                "job_id": job.id,
                "status": job.status,
                "current_stage": job.current_stage,
                "error": job.error,
                "cost_estimate": job.cost_estimate,
            }
            if stage_detail:
                payload["stage_detail"] = stage_detail
            self._redis.publish("job_updates", json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to publish status update: {e}")

    def _get_multi_stage_formatter(self, profile_id: str) -> MultiStageFormatter:
        """Get or create multi-stage formatter for a profile."""
        profile = self.profile_loader.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")
        
        # Check that at least one LLM provider is configured
        from .providers import get_configured_providers
        providers = get_configured_providers()
        any_configured = any(providers.values())
        
        if not any_configured:
            raise RuntimeError("No LLM providers configured. Set at least one API key.")
        
        # Use first available key as default (for backward compatibility)
        default_key = (
            os.getenv("DEEPSEEK_API_KEY") or 
            os.getenv("OPENROUTER_API_KEY") or 
            os.getenv("OPENAI_API_KEY") or 
            os.getenv("ZAI_API_KEY") or 
            ""
        )
        
        return MultiStageFormatter(
            api_key=default_key,
            prompts_dir=self.config_dir / "prompts",
            profile=profile
        )

    def process_job(self, job_id: str):
        """
        Process a specific job by ID.
        Resumes from last completed stage if possible.
        """
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            job.status = "PROCESSING"
            session.add(job)
            session.commit()
            self._publish_status(job)
            
            try:
                self._run_job(session, job)
                
                job.status = "COMPLETE"
                job.completed_at = datetime.now()
                job.current_stage = "complete"
                session.add(job)
                session.commit()
                self._publish_status(job)
                logger.info(f"Job {job_id} completed successfully")
                
            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}")
                job.status = "FAILED"
                job.error = str(e)
                session.add(job)
                session.commit()
                self._publish_status(job)
                
                # Move to error dir
                try:
                    src_path = Path(job.filename)
                    if src_path.exists():
                        shutil.move(str(src_path), str(self.error_dir / src_path.name))
                except Exception as move_err:
                    logger.error(f"Failed to move failed file: {move_err}")
                    
                raise

    def _get_stage_result(self, session: Session, job_id: str, stage_id: str) -> Optional[StageResult]:
        """Check if a stage is already completed."""
        statement = select(StageResult).where(
            StageResult.job_id == job_id,
            StageResult.stage_id == stage_id,
            StageResult.status == "COMPLETE"
        )
        return session.exec(statement).first()

    def _record_stage(self, session: Session, job: Job, stage_id: str, status: str, **kwargs):
        """Record stage execution in DB."""
        # Check if exists
        statement = select(StageResult).where(
            StageResult.job_id == job.id, 
            StageResult.stage_id == stage_id
        )
        stage_result = session.exec(statement).first()
        
        if not stage_result:
            stage_result = StageResult(job_id=job.id, stage_id=stage_id)
            
        stage_result.status = status
        if status == "RUNNING":
            stage_result.started_at = datetime.now()
        elif status == "COMPLETE":
            stage_result.completed_at = datetime.now()
            
        # Update other fields
        for k, v in kwargs.items():
            if hasattr(stage_result, k):
                setattr(stage_result, k, v)
                
        session.add(stage_result)
        job.current_stage = stage_id
        session.add(job)
        session.commit()
        self._publish_status(job, stage_detail={
            "stage_id": stage_id,
            "stage_status": status,
            "model_used": kwargs.get("model_used"),
        })
        return stage_result

    def _run_job(self, session: Session, job: Job):
        """Run the actual pipeline steps for a job."""
        file_path = Path(job.filename)
        
        # Check quarantine first
        quarantine_path = self.quarantine_dir / file_path.name
        if quarantine_path.exists():
            file_path = quarantine_path
        elif not file_path.exists():
            # If not in quarantine and not in original, fail
            raise FileNotFoundError(f"File not found: {file_path}")
            
        start_time = time.time()
        
        # 1. Determine Profile
        profile_id = job.profile_id
        
        # 2. Transcription (Stage 1)
        transcript_data = None
        cached_transcription = self._get_stage_result(session, job.id, "transcription")
        
        # Check if we have a valid cached transcription
        if cached_transcription and cached_transcription.status == "COMPLETE":
             if cached_transcription.output_path and Path(cached_transcription.output_path).exists():
                 logger.info(f"Resuming: Found cached transcription at {cached_transcription.output_path}")
                 import json
                 try:
                     with open(cached_transcription.output_path, 'r') as f:
                         transcript_data = json.load(f)
                 except Exception as e:
                     logger.warning(f"Failed to load cached transcription: {e}")
             else:
                 logger.warning("Cached transcription record found but file missing. Re-running.")
             
        if not transcript_data:
            self._record_stage(session, job, "transcription", "RUNNING")
            
            if not self.groq:
                raise RuntimeError("Groq client not initialized")
            
            logger.info(f"Transcribing {file_path.name}")
            transcription = self.groq.transcribe(file_path)
            
            transcript_data = {
                "segments": transcription.get("segments", []),
                "text": transcription.get("text", ""),
                "duration": transcription.get("duration", 0)
            }
            
            # Save transcription to disk for resumability
            job_data_dir = self.processing_dir / "job_data" / job.id
            job_data_dir.mkdir(parents=True, exist_ok=True)
            transcription_file = job_data_dir / "transcription.json"
            
            import json
            with open(transcription_file, 'w') as f:
                json.dump(transcript_data, f)
            
            self._record_stage(session, job, "transcription", "COMPLETE", 
                             output_path=str(transcription_file))

        # Dispatch based on profile
        result_monitor = {
            "outputs": {},
            "success": False,
            "duration": 0
        }
        
        if profile_id and self.profile_loader.get_profile(profile_id):
            self._process_with_profile(
                session=session,
                job=job,
                audio_path=file_path,
                transcript_data=transcript_data,
                profile_id=profile_id,
                result=result_monitor
            )
        else:
            self._process_standard(
                session=session,
                job=job,
                audio_path=file_path,
                transcript_data=transcript_data,
                note_type=profile_id or "meeting", # Fallback note type
                result=result_monitor
            )
            
        # Cleanup
        result_monitor["duration"] = time.time() - start_time
        if result_monitor["success"]:
             self._safe_archive(file_path, result_monitor)

    def _process_with_profile(
        self,
        session: Session,
        job: Job,
        audio_path: Path,
        transcript_data: Dict,
        profile_id: str,
        result: Dict
    ):
        """Process using multi-stage formatter with per-stage tracking and resume."""
        logger.info(f"Processing with profile: {profile_id}")
        
        whisper_segments = transcript_data["segments"]
        full_text = transcript_data["text"]
        duration = transcript_data["duration"]
        
        # Build raw transcript
        raw_transcript = self._build_raw_transcript(whisper_segments)
        
        # Get the profile and its stages
        profile = self.profile_loader.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")
        
        from .providers import resolve_provider
        from .pricing import estimate_cost
        
        current_input = raw_transcript
        previous_outputs = {}
        stage_results_data = {}
        total_cost = 0.0
        
        # Process each stage individually with resume support
        for i, stage in enumerate(profile.stages):
            stage_id = stage.name
            
            # Check if this stage was already completed (resume support)
            cached = self._get_stage_result(session, job.id, stage_id)
            if cached and cached.output_path:
                cached_path = Path(cached.output_path)
                if cached_path.exists():
                    logger.info(f"Resuming: Stage '{stage_id}' already complete, loading cached output")
                    try:
                        current_input = cached_path.read_text(encoding="utf-8")
                        previous_outputs[stage_id] = current_input
                        stage_results_data[stage_id] = current_input
                        total_cost += cached.cost_estimate or 0.0
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load cached stage output: {e}. Re-running stage.")
            
            # Record stage as RUNNING
            self._record_stage(session, job, stage_id, "RUNNING", model_used=stage.model)
            
            try:
                # Resolve provider
                provider_config = resolve_provider(stage.model, stage.provider or None)
                
                # Build prompt
                prompt_kwargs = {"transcript": current_input}
                if "{cleaned_transcript}" in stage.prompt_template and "clean" in previous_outputs:
                    prompt_kwargs["cleaned_transcript"] = previous_outputs.get("clean", current_input)
                elif "{cleaned_transcript}" in stage.prompt_template:
                    prompt_kwargs["cleaned_transcript"] = current_input
                
                prompt = stage.prompt_template.format(**prompt_kwargs)
                
                # Call LLM using the formatter's _call_api
                multi_formatter = self._get_multi_stage_formatter(profile_id)
                output, usage_info = multi_formatter._call_api(
                    prompt=prompt,
                    system_message=stage.system_message,
                    model=stage.model,
                    temperature=stage.temperature,
                    max_tokens=stage.max_tokens,
                    timeout=stage.timeout,
                    provider_config=provider_config,
                )
                
                # Calculate per-stage cost
                input_tokens = usage_info.get("input_tokens", 0)
                output_tokens = usage_info.get("output_tokens", 0)
                stage_cost = estimate_cost(stage.model, input_tokens, output_tokens)
                total_cost += stage_cost
                
                # Save intermediate output for resume
                job_data_dir = self.processing_dir / "job_data" / job.id
                job_data_dir.mkdir(parents=True, exist_ok=True)
                stage_output_path = job_data_dir / f"stage_{stage_id}.txt"
                stage_output_path.write_text(output, encoding="utf-8")
                
                # Record stage as COMPLETE with full metrics
                self._record_stage(
                    session, job, stage_id, "COMPLETE",
                    model_used=stage.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate=stage_cost,
                    output_path=str(stage_output_path),
                )
                
                # Update for next stage
                current_input = output
                previous_outputs[stage_id] = output
                stage_results_data[stage_id] = output
                
                logger.info(f"  Stage '{stage_id}' complete ({len(output)} chars, ${stage_cost:.6f})")
                
            except Exception as e:
                logger.error(f"  Stage '{stage_id}' failed: {e}")
                self._record_stage(session, job, stage_id, "FAILED", error=str(e), model_used=stage.model)
                raise  # Fail the job — on next run it will resume from this stage
        
        # Update total cost
        job.cost_estimate = total_cost
        session.add(job)
        session.commit()
        
        # Output Generation
        self._record_stage(session, job, "output", "RUNNING")
        
        # Build stage outputs for file generation
        stage_outputs = []
        for stage in profile.stages:
            if stage.name in stage_results_data and stage.save_intermediate:
                stage_outputs.append({
                    "stage": stage.name,
                    "suffix": stage.filename_suffix,
                    "content": stage_results_data[stage.name],
                })
        
        metadata = {
            "duration": duration,
            "processed_at": datetime.now().isoformat(),
            "profile": profile_id,
        }
        
        syncthing = getattr(profile, 'syncthing', None)
        user_subdir = syncthing.subfolder if syncthing else None
        docs_dir = self.output_generator.get_user_docs_dir(user_subdir)
        
        all_outputs = []
        for stage_output in stage_outputs:
            outputs = self.output_generator.generate_multi_stage_output(
                content=stage_output["content"],
                filename_base=audio_path.stem,
                suffix=stage_output["suffix"],
                stage_name=stage_output["stage"],
                metadata=metadata,
                docs_dir=docs_dir
            )
            all_outputs.extend(outputs)
            
        result["outputs"] = {"stage_files": all_outputs}
        result["success"] = True
        
        self._record_stage(session, job, "output", "COMPLETE")
        
        # Notifications
        self._send_notifications(profile_id, profile, audio_path.stem, all_outputs, total_cost)

    def _process_standard(
        self,
        session: Session,
        job: Job,
        audio_path: Path,
        transcript_data: Dict,
        note_type: str,
        result: Dict
    ):
        """Standard processing."""
        whisper_segments = transcript_data["segments"]
        duration = transcript_data["duration"]
        
        # Diarization
        diarization_segments = []
        if self.diarizer:
            self._record_stage(session, job, "diarization", "RUNNING")
            try:
                diarization_segments = self.diarizer.diarize(audio_path)
                self._record_stage(session, job, "diarization", "COMPLETE")
            except Exception as e:
                logger.warning(f"Diarization failed: {e}")
                diarization_segments = [{"speaker": "SPEAKER_00", "start": 0, "end": duration}]
                self._record_stage(session, job, "diarization", "FAILED", error=str(e))
        else:
             diarization_segments = [{"speaker": "SPEAKER_00", "start": 0, "end": duration}]
             
        # Merge
        merged_segments = merge_transcript_with_speakers(whisper_segments, diarization_segments)
        speaker_transcript = self._build_speaker_transcript(merged_segments)
        
        # Format
        self._record_stage(session, job, "formatting", "RUNNING")
        formatted_text = speaker_transcript
        
        if self.formatter:
            try:
                metadata = {
                    "duration": duration,
                    "num_speakers": len(set(s["speaker"] for s in merged_segments)),
                    "note_type": note_type,
                }
                formatted_text = self.formatter.format_transcript(
                    speaker_transcript, note_type, metadata
                )
                self._record_stage(session, job, "formatting", "COMPLETE")
            except Exception as e:
                 logger.error(f"Formatting failed: {e}")
                 self._record_stage(session, job, "formatting", "FAILED", error=str(e))
        
        # Output
        self._record_stage(session, job, "output", "RUNNING")
        outputs = self.output_generator.generate_outputs(
            formatted_text, note_type, audio_path.stem, 
            {"duration": duration, "processed_at": datetime.now().isoformat()}
        )
        result["outputs"] = outputs
        result["success"] = True
        self._record_stage(session, job, "output", "COMPLETE")

    def _send_email(self, profile_id: str, lecture_name: str, outputs: List[Dict]):
        """Send email notification."""
        if not self.email_sender.is_configured():
            return
            
        recipient_email = None
        user_name = None
        cc_email = None
        
        if profile_id == "social_work_lecture":
            recipient_email = get_kate_email()
            user_name = "Kate"
        elif profile_id == "business_lecture":
            recipient_email = get_keira_email()
            user_name = "Keira"
            cc_email = get_keira_cohort_email()
            
        if recipient_email:
            output_paths = [Path(o["path"]) for o in outputs if o.get("type") == "docx"]
            self.email_sender.send_lecture_complete(
                to_email=recipient_email,
                lecture_name=lecture_name,
                output_files=output_paths,
                profile_name=profile_id,
                user_name=user_name,
                cc_email=cc_email
            )

    def _send_notifications(self, profile_id: str, profile, lecture_name: str, outputs: list, total_cost: float = 0.0):
        """Send all configured notifications for a completed job."""
        # Email (existing)
        self._send_email(profile_id, lecture_name, outputs)
        
        # Webhook notifications (Ntfy, Discord, Pushover)
        notification_config = getattr(profile, 'notifications', None)
        if not notification_config:
            return
        
        output_names = [Path(o.get("path", "")).name for o in outputs if o.get("type") == "docx"]
        summary = f"Pipeline complete: {lecture_name} ({len(output_names)} files, ${total_cost:.4f})"
        
        # Ntfy
        ntfy_topic = getattr(notification_config, 'ntfy_topic', None)
        ntfy_url = getattr(notification_config, 'ntfy_url', None) or os.getenv("NTFY_URL", "https://ntfy.sh")
        if ntfy_topic:
            try:
                import requests as req
                req.post(
                    f"{ntfy_url}/{ntfy_topic}",
                    data=summary,
                    headers={
                        "Title": f"Transcription: {lecture_name}",
                        "Priority": "default",
                        "Tags": "white_check_mark",
                    },
                    timeout=10,
                )
                logger.info(f"Ntfy notification sent to topic: {ntfy_topic}")
            except Exception as e:
                logger.warning(f"Ntfy notification failed: {e}")
        
        # Discord
        discord_webhook = getattr(notification_config, 'discord_webhook', None) or os.getenv("DISCORD_WEBHOOK_URL")
        if discord_webhook:
            try:
                import requests as req
                req.post(
                    discord_webhook,
                    json={
                        "content": summary,
                        "embeds": [{
                            "title": f"Transcription Complete",
                            "description": f"**{lecture_name}**\nProfile: {profile_id}\nCost: ${total_cost:.4f}\nFiles: {', '.join(output_names)}",
                            "color": 3066993,  # Green
                        }]
                    },
                    timeout=10,
                )
                logger.info("Discord notification sent")
            except Exception as e:
                logger.warning(f"Discord notification failed: {e}")
        
        # Pushover
        pushover_user = getattr(notification_config, 'pushover_user', None) or os.getenv("PUSHOVER_USER_KEY")
        pushover_token = getattr(notification_config, 'pushover_token', None) or os.getenv("PUSHOVER_APP_TOKEN")
        if pushover_user and pushover_token:
            try:
                import requests as req
                req.post(
                    "https://api.pushover.net/1/messages.json",
                    data={
                        "token": pushover_token,
                        "user": pushover_user,
                        "title": f"Transcription: {lecture_name}",
                        "message": summary,
                    },
                    timeout=10,
                )
                logger.info("Pushover notification sent")
            except Exception as e:
                logger.warning(f"Pushover notification failed: {e}")

    def _safe_archive(self, audio_path: Path, result: Dict) -> None:
        """Safely archive or delete."""
        # Simple verification for now: if success, delete or archive
        if result.get("success"):
            # Check if we should delete or archive
            # For now, let's always archive
            try:
                shutil.move(str(audio_path), str(self.archive_dir / audio_path.name))
                logger.info(f"Archived {audio_path.name}")
            except Exception as e:
                logger.error(f"Failed to archive: {e}")

    def _build_speaker_transcript(self, segments: list) -> str:
        """Build a transcript string with speaker labels."""
        lines = []
        current_speaker = None
        current_text = []
        
        for seg in segments:
            speaker = seg.get("speaker", "UNKNOWN")
            text = seg.get("text", "").strip()
            
            if not text:
                continue
            
            if speaker != current_speaker:
                if current_text:
                    lines.append(f"{' '.join(current_text)}")
                    lines.append("")
                lines.append(f"**{speaker}:**")
                current_speaker = speaker
                current_text = []
            
            current_text.append(text)
        
        if current_text:
            lines.append(f"{' '.join(current_text)}")
        
        return "\n".join(lines)
    
    def _build_raw_transcript(self, segments: list) -> str:
        """Build a simple transcript from Whisper segments."""
        lines = []
        for seg in segments:
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            if text:
                hours = int(start // 3600)
                minutes = int((start % 3600) // 60)
                secs = int(start % 60)
                timestamp = f"{hours:02d}:{minutes:02d}:{secs:02d}"
                lines.append(f"[{timestamp}] {text}")
        return "\n".join(lines)

    def _format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
